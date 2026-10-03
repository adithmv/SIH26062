"""Local file storage. Prepared copies are not PMCE transmission receipts."""
import gzip
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid4

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, SecretStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import get_session
from .models import ManagedFile, PreparedFile

router = APIRouter(prefix="/api/files", tags=["Data management"])
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


def require(session, model, identifier):
    row = session.get(model, identifier)
    if row is None:
        raise HTTPException(404, "File not found")
    return row


def describe(row, session):
    return {"id": str(row.id), "name": row.name, "size": row.size,
            "importance": row.importance, "confidentiality": row.confidentiality,
            "storage_path": str(location(row.id)), "status": "Stored locally — not sent to base",
            "copies": [{"id": str(p.id), "size": p.size, "compressed": p.compressed,
                        "encrypted": p.encrypted, "storage_path": str(location(p.id, True))}
                       for p in session.scalars(select(PreparedFile).where(PreparedFile.file_id == row.id).order_by(PreparedFile.created_at))]}


@router.get("")
def listing(session: Session = Depends(get_session)):
    return {"storage_root": str(root()), "max_bytes": LIMIT,
            "files": [describe(row, session) for row in session.scalars(select(ManagedFile).order_by(ManagedFile.created_at.desc()))]}


@router.post("", status_code=201)
async def upload(request: Request, name: str, session: Session = Depends(get_session)):
    if not name or len(name) > 180 or re.search(r'[<>:"/\\|?*\x00-\x1f\x7f]', name) or name in {".", ".."} or name.endswith((".", " ")):
        raise HTTPException(400, "Use a filename of 1–180 characters without path separators or special characters.")
    identifier = uuid4()
    path = location(identifier)
    size = 0
    try:
        with path.open("xb") as target:
            async for chunk in request.stream():
                size += len(chunk)
                if size > LIMIT:
                    raise HTTPException(413, "Maximum file size is 20 MiB.")
                target.write(chunk)
        if not size:
            raise HTTPException(400, "Empty files cannot be uploaded.")
        row = ManagedFile(id=identifier, name=name, size=size, created_at=datetime.now(timezone.utc))
        session.add(row)
        session.commit()
    except BaseException:
        session.rollback()
        path.unlink(missing_ok=True)
        raise
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


def read(path):
    if not path.is_file():
        raise HTTPException(404, "Stored file is missing. Check the storage folder.")
    return path.read_bytes()


@router.post("/{identifier}/prepare", status_code=201)
def prepare(identifier: UUID, body: Prepare, session: Session = Depends(get_session)):
    row = require(session, ManagedFile, identifier)
    password = body.password.get_secret_value()
    if body.encrypt and not 12 <= len(password) <= 256:
        raise HTTPException(400, "Use an encryption password of 12–256 characters.")
    data = read(location(row.id))
    if body.compress:
        data = gzip.compress(data, mtime=0)
    if body.encrypt:
        salt, nonce = os.urandom(16), os.urandom(12)
        header = MAGIC + bytes([int(body.compress)]) + salt + nonce
        data = header + AESGCM(key(password, salt)).encrypt(nonce, data, header)
    copy = PreparedFile(id=uuid4(), file_id=row.id, size=len(data), compressed=body.compress,
                        encrypted=body.encrypt, created_at=datetime.now(timezone.utc))
    path = location(copy.id, True)
    try:
        path.write_bytes(data)
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
    return FileResponse(path, filename=row.name, media_type="application/octet-stream", headers={"Cache-Control": "no-store"})


@router.get("/copies/{identifier}/download")
def download_copy(identifier: UUID, session: Session = Depends(get_session)):
    copy = require(session, PreparedFile, identifier)
    row = require(session, ManagedFile, copy.file_id)
    path = location(copy.id, True)
    if not path.is_file():
        raise HTTPException(404, "Stored copy is missing.")
    suffix = (".gz" if copy.compressed else "") + (".pemenc" if copy.encrypted else "")
    return FileResponse(path, filename=row.name + suffix, media_type="application/octet-stream", headers={"Cache-Control": "no-store"})


class Unlock(BaseModel):
    password: SecretStr = SecretStr("")


@router.post("/copies/{identifier}/restore")
def restore(identifier: UUID, body: Unlock, session: Session = Depends(get_session)):
    copy = require(session, PreparedFile, identifier)
    data = read(location(copy.id, True))
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
        except (OSError, EOFError, ValueError):
            raise HTTPException(400, "Invalid compressed file.") from None
    return Response(data, media_type="application/octet-stream", headers={"Cache-Control": "no-store", "Content-Disposition": "attachment"})
