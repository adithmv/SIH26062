"""Local file storage. Prepared copies are not PMCE transmission receipts."""
import gzip
import hashlib
import shutil
import os
import re
import zlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid4
from urllib.parse import quote

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from fastapi.routing import APIRoute
from pydantic import BaseModel, SecretStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import get_session
from .models import ManagedFile, PreparedFile
from .security import enabled

class FileRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def handle(request):
            try:
                return await handler(request)
            except OSError:
                raise HTTPException(503, "Cannot access file storage. Check folder permissions and available disk space.") from None

        return handle


router = APIRouter(prefix="/api/files", tags=["Data management"], route_class=FileRoute)
LIMIT = 20 * 1024 * 1024
MAGIC = b"PEM1"


def root():
    path = Path(os.getenv("FILE_STORAGE_ROOT", str(Path(__file__).resolve().parents[1] / "data" / "files"))).resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def location(identifier, prepared=False):
    folder = root() / ("prepared" if prepared else "originals")
    folder.mkdir(exist_ok=True)
    return folder / str(identifier)


def reserve_space():
    if shutil.disk_usage(root()).free < LIMIT + 256 * 1024 * 1024:
        raise HTTPException(507, "Storage is nearly full. Free space before uploading or preparing files.")


def publish(data, path):
    reserve_space()
    temporary = path.with_name(str(uuid4()) + ".partial")
    try:
        with temporary.open("xb") as target:
            target.write(data)
            target.flush()
            os.fsync(target.fileno())
        os.replace(temporary, path)
        sync_directory(path.parent)
    finally:
        temporary.unlink(missing_ok=True)


def sync_directory(folder):
    if os.name != "nt":
        descriptor = os.open(folder, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def require(session, model, identifier):
    row = session.get(model, identifier)
    if row is None:
        raise HTTPException(404, "File not found")
    return row


def describe(row, session, copies=None):
    if copies is None:
        copies = session.scalars(select(PreparedFile).where(PreparedFile.file_id == row.id).order_by(PreparedFile.created_at)).all()
    available = location(row.id).is_file()
    return {"id": str(row.id), "name": row.name, "size": row.size,
            "created_at": row.created_at, "available": location(row.id).is_file(),
            "importance": row.importance, "confidentiality": row.confidentiality,
            "sha256": row.sha256,
            "storage_path": str(location(row.id)), "status": ("Stored at base" if enabled() else "Stored locally — not sent to base") if available else "Original missing from storage",
            "copies": [{"id": str(p.id), "size": p.size, "compressed": p.compressed,
                        "encrypted": p.encrypted, "storage_path": str(location(p.id, True)),
                        "created_at": p.created_at, "available": location(p.id, True).is_file()}
                       for p in copies]}


@router.get("")
def listing(response: Response, session: Session = Depends(get_session)):
    response.headers["Cache-Control"] = "no-store"
    copies = {}
    for copy in session.scalars(select(PreparedFile).order_by(PreparedFile.created_at)):
        copies.setdefault(copy.file_id, []).append(copy)
    return {"storage_root": str(root()), "max_bytes": LIMIT,
            "folders": {"originals": str(root() / "originals"), "prepared": str(root() / "prepared")},
            "files": [describe(row, session, copies.get(row.id, [])) for row in session.scalars(select(ManagedFile).order_by(ManagedFile.created_at.desc()))]}


@router.post("", status_code=201)
async def upload(request: Request, name: str, session: Session = Depends(get_session)):
    if not name or len(name) > 180 or re.search(r'[<>:"/\\|?*\x00-\x1f\x7f]', name) or name in {".", ".."} or name.endswith((".", " ")):
        raise HTTPException(400, "Use a filename of 1–180 characters without path separators or special characters.")
    reserve_space()
    try:
        identifier = UUID(request.headers["x-transfer-id"]) if "x-transfer-id" in request.headers else uuid4()
    except ValueError:
        raise HTTPException(400, "X-Transfer-ID must be a UUID.") from None
    expected_hash = request.headers.get("x-content-sha256")
    if expected_hash is not None and not re.fullmatch(r"[0-9a-f]{64}", expected_hash):
        raise HTTPException(400, "X-Content-SHA256 must be a lowercase SHA-256 digest.")
    path = location(identifier)
    temporary = path.with_name(str(uuid4()) + ".partial")
    size = 0
    checksum = hashlib.sha256()
    published = False
    try:
        with temporary.open("xb") as target:
            async for chunk in request.stream():
                size += len(chunk)
                if size > LIMIT:
                    raise HTTPException(413, "Maximum file size is 20 MiB.")
                target.write(chunk)
                checksum.update(chunk)
            target.flush()
            os.fsync(target.fileno())
        if not size:
            raise HTTPException(400, "Empty files cannot be uploaded.")
        actual_hash = checksum.hexdigest()
        if expected_hash and expected_hash != actual_hash:
            raise HTTPException(422, "File checksum does not match. Nothing was stored.")
        existing = session.get(ManagedFile, identifier)
        if existing:
            if existing.sha256 == actual_hash and existing.name == name and existing.size == size:
                # Verify the stored bytes before acknowledging a retry.
                verify_data(read(path), existing, 409)
                return describe(existing, session)
            raise HTTPException(409, "This transfer ID belongs to a different file. Use a new ID.")
        # Exclusive destination creation prevents simultaneous retries from replacing bytes.
        try:
            with path.open("xb"):
                pass
        except FileExistsError:
            raise HTTPException(409, "Transfer is already being stored or needs recovery. Retry shortly with the same transfer ID.") from None
        published = True
        os.replace(temporary, path)
        sync_directory(path.parent)
        row = ManagedFile(id=identifier, name=name, size=size, sha256=actual_hash, created_at=datetime.now(timezone.utc))
        session.add(row)
        session.commit()
    except BaseException:
        session.rollback()
        if published:
            path.unlink(missing_ok=True)
        raise
    finally:
        temporary.unlink(missing_ok=True)
    return describe(row, session)


class Levels(BaseModel):
    importance: Literal["normal", "important", "critical"]
    confidentiality: Literal["normal", "confidential"]


@router.patch("/{identifier}")
def levels(identifier: UUID, body: Levels, session: Session = Depends(get_session)):
    row = require(session, ManagedFile, identifier)
    row.importance = body.importance
    row.confidentiality = body.confidentiality
    session.commit()
    return describe(row, session)


class Prepare(BaseModel):
    compress: bool = True
    encrypt: bool = False
    password: SecretStr = SecretStr("")


def key(password, salt):
    return Scrypt(salt=salt, length=32, n=2**15, r=8, p=1).derive(password.encode("utf-8"))


def read(path, max_bytes=LIMIT + 65536):
    if not path.is_file():
        raise HTTPException(404, "Stored file is missing. Check the storage folder.")
    with path.open("rb") as source:
        data = source.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise HTTPException(400, "Stored file exceeds the allowed size. Check the storage folder.")
    return data


def verify_data(data, row, status=400):
    if len(data) != row.size or (row.sha256 and hashlib.sha256(data).hexdigest() != row.sha256):
        raise HTTPException(status, "Stored file is incomplete or has changed outside the app.")


def attachment(data, name):
    return Response(data, media_type="application/octet-stream", headers={"Cache-Control": "no-store", "Content-Disposition": "attachment; filename*=UTF-8''" + quote(name, safe="")})


@router.post("/{identifier}/prepare", status_code=201)
def prepare(identifier: UUID, body: Prepare, session: Session = Depends(get_session)):
    row = require(session, ManagedFile, identifier)
    password = body.password.get_secret_value()
    if body.encrypt and not 12 <= len(password) <= 256:
        raise HTTPException(400, "Use an encryption password of 12–256 characters.")
    data = read(location(row.id), LIMIT)
    if len(data) != row.size:
        raise HTTPException(409, "Original file size has changed outside the app. Upload the file again before preparing it.")
    verify_data(data, row, 409)
    if body.compress:
        data = gzip.compress(data, mtime=0)
    if body.encrypt:
        salt, nonce = os.urandom(16), os.urandom(12)
        header = MAGIC + bytes([int(body.compress)]) + salt + nonce
        data = header + AESGCM(key(password, salt)).encrypt(nonce, data, header)
    copy = PreparedFile(id=uuid4(), file_id=row.id, size=len(data), compressed=body.compress,
                        encrypted=body.encrypt, sha256=hashlib.sha256(data).hexdigest(), created_at=datetime.now(timezone.utc))
    path = location(copy.id, True)
    try:
        publish(data, path)
        session.add(copy)
        session.commit()
    except BaseException:
        session.rollback()
        path.unlink(missing_ok=True)
        raise
    return describe(row, session)


@router.get("/{identifier}/download")
def original(identifier: UUID, session: Session = Depends(get_session)):
    row = require(session, ManagedFile, identifier)
    path = location(row.id)
    if not path.is_file():
        raise HTTPException(404, "Stored file is missing.")
    data = read(path)
    verify_data(data, row, 409)
    return attachment(data, row.name)


@router.get("/copies/{identifier}/download")
def download_copy(identifier: UUID, session: Session = Depends(get_session)):
    copy = require(session, PreparedFile, identifier)
    row = require(session, ManagedFile, copy.file_id)
    path = location(copy.id, True)
    if not path.is_file():
        raise HTTPException(404, "Stored copy is missing.")
    suffix = (".gz" if copy.compressed else "") + (".pemenc" if copy.encrypted else "")
    data = read(path)
    verify_data(data, copy, 409)
    return attachment(data, row.name + suffix)


class Unlock(BaseModel):
    password: SecretStr = SecretStr("")


@router.post("/copies/{identifier}/restore")
def restore(identifier: UUID, body: Unlock, session: Session = Depends(get_session)):
    copy = require(session, PreparedFile, identifier)
    row = require(session, ManagedFile, copy.file_id)
    data = read(location(copy.id, True))
    verify_data(data, copy)
    if len(data) != copy.size:
        raise HTTPException(400, "Stored copy is incomplete or has changed outside the app.")
    if copy.encrypted:
        password = body.password.get_secret_value()
        if not 12 <= len(password) <= 256:
            raise HTTPException(400, "Enter the encryption password (12–256 characters).")
        if len(data) < 49 or data[:4] != MAGIC or data[4] != int(copy.compressed):
            raise HTTPException(400, "Invalid encrypted file.")
        try:
            data = AESGCM(key(password, data[5:21])).decrypt(data[21:33], data[33:], data[:33])
        except InvalidTag:
            raise HTTPException(400, "Incorrect password or damaged encrypted file.") from None
    if copy.compressed:
        import io
        try:
            with gzip.GzipFile(fileobj=io.BytesIO(data)) as source:
                data = source.read(LIMIT + 1)
            if len(data) > LIMIT:
                raise ValueError("Too large")
        except (OSError, EOFError, ValueError, zlib.error):
            raise HTTPException(400, "Invalid compressed file.") from None
    if len(data) != row.size:
        raise HTTPException(400, "Restored file size does not match the original.")
    verify_data(data, row)
    return Response(data, media_type="application/octet-stream", headers={"Cache-Control": "no-store", "Content-Disposition": "attachment; filename*=UTF-8''" + quote(row.name, safe="")})
