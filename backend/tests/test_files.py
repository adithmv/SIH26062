import gzip
from pathlib import Path

import pytest

from app import files

pytestmark = pytest.mark.empty_database


@pytest.fixture(autouse=True)
def storage(tmp_path, monkeypatch):
    monkeypatch.setenv("FILE_STORAGE_ROOT", str(tmp_path / "files"))


def upload(client):
    response = client.post("/api/files?name=observations.txt", content=b"field observation\n" * 100)
    assert response.status_code == 201
    return response.json()


def test_empty_upload_levels_and_original(client):
    assert client.get("/api/files").json()["files"] == []
    row = upload(client)
    assert Path(row["storage_path"]).read_bytes() == b"field observation\n" * 100
    response = client.patch(f'/api/files/{row["id"]}', json={"importance": "critical", "confidentiality": "confidential"})
    assert response.json()["confidentiality"] == "confidential"
    assert "not sent to base" in response.json()["status"]
    assert client.get(f'/api/files/{row["id"]}/download').content == b"field observation\n" * 100
    assert client.patch(f'/api/files/{row["id"]}', json={"importance": "bad", "confidentiality": "normal"}).status_code == 422


@pytest.mark.parametrize("compress,encrypt", [(False, False), (True, False), (False, True), (True, True)])
def test_prepare_restore_preserves_original(client, compress, encrypt):
    row = upload(client)
    original = Path(row["storage_path"]).read_bytes()
    password = "a long test password"
    response = client.post(f'/api/files/{row["id"]}/prepare', json={"compress": compress, "encrypt": encrypt, "password": password})
    assert response.status_code == 201
    copy = response.json()["copies"][0]
    stored = client.get(f'/api/files/copies/{copy["id"]}/download').content
    assert len(stored) == copy["size"]
    assert Path(row["storage_path"]).read_bytes() == original
    restored = client.post(f'/api/files/copies/{copy["id"]}/restore', json={"password": password})
    assert restored.status_code == 200
    assert restored.content == original
    assert restored.headers["cache-control"] == "no-store"
    if encrypt:
        assert original not in stored
        assert client.post(f'/api/files/copies/{copy["id"]}/restore', json={"password": "wrong long password"}).status_code == 400
        altered = bytearray(stored)
        altered[-1] ^= 1
        Path(copy["storage_path"]).write_bytes(altered)
        assert client.post(f'/api/files/copies/{copy["id"]}/restore', json={"password": password}).status_code == 400
    elif compress:
        assert gzip.decompress(stored) == original


def test_upload_constraints_and_cleanup(client, monkeypatch):
    for name in ["../escape", "..", "bad\\file", "bad:file", "a" * 181]:
        assert client.post("/api/files", params={"name": name}, content=b"x").status_code == 400
    assert client.post("/api/files?name=empty", content=b"").status_code == 400
    monkeypatch.setattr(files, "LIMIT", 5)
    assert client.post("/api/files?name=large", content=b"123456").status_code == 413
    assert client.get("/api/files").json()["files"] == []
    assert list((files.root() / "originals").iterdir()) == []


def test_missing_file_and_short_password(client):
    row = upload(client)
    assert client.post(f'/api/files/{row["id"]}/prepare', json={"encrypt": True, "password": "short"}).status_code == 400
    assert client.get("/api/files").json()["files"][0]["copies"] == []
    Path(row["storage_path"]).unlink()
    assert client.get(f'/api/files/{row["id"]}/download').status_code == 404
    assert client.post(f'/api/files/{row["id"]}/prepare', json={}).status_code == 404


def test_listing_reports_missing_files_and_real_folders(client):
    row = upload(client)
    response = client.post(f'/api/files/{row["id"]}/prepare', json={"compress": True})
    copy = response.json()["copies"][0]
    Path(row["storage_path"]).unlink()
    result = client.get("/api/files")
    assert result.headers["cache-control"] == "no-store"
    listing = result.json()
    assert Path(listing["folders"]["originals"]) == Path(row["storage_path"]).parent
    assert not listing["files"][0]["available"]
    assert listing["files"][0]["copies"][0]["available"]
    assert listing["files"][0]["created_at"]
    assert client.post(f'/api/files/copies/{copy["id"]}/restore', json={}).content == b"field observation\n" * 100
    Path(copy["storage_path"]).unlink()
    assert not client.get("/api/files").json()["files"][0]["copies"][0]["available"]


def test_damaged_compression_and_oversized_storage(client, monkeypatch):
    row = upload(client)
    copy = client.post(f'/api/files/{row["id"]}/prepare', json={"compress": True}).json()["copies"][0]
    # A gzip header followed by an invalid DEFLATE block must return a helpful 400.
    Path(copy["storage_path"]).write_bytes(b"\x1f\x8b\x08\x00\x00\x00\x00\x00\x00\xff\x07")
    assert client.post(f'/api/files/copies/{copy["id"]}/restore', json={}).status_code == 400
    monkeypatch.setattr(files, "LIMIT", 5)
    assert client.post(f'/api/files/{row["id"]}/prepare', json={}).status_code == 400


def test_same_name_uploads_preserve_both_files(client):
    first = upload(client)
    second = upload(client)
    assert first["id"] != second["id"]
    assert Path(first["storage_path"]).exists()
    assert len(client.get("/api/files").json()["files"]) == 2


def test_changed_original_and_truncated_copy_are_rejected(client):
    row = upload(client)
    copy = client.post(f'/api/files/{row["id"]}/prepare', json={"compress": False}).json()["copies"][0]
    restored = client.post(f'/api/files/copies/{copy["id"]}/restore', json={})
    assert "observations.txt" in restored.headers["content-disposition"]
    Path(copy["storage_path"]).write_bytes(b"truncated")
    assert client.post(f'/api/files/copies/{copy["id"]}/restore', json={}).status_code == 400
    Path(row["storage_path"]).write_bytes(b"changed")
    assert client.post(f'/api/files/{row["id"]}/prepare', json={}).status_code == 409


def test_storage_permission_error_is_readable(client, monkeypatch):
    def denied():
        raise PermissionError("internal path must not be exposed")
    monkeypatch.setattr(files, "root", denied)
    response = client.get("/api/files")
    assert response.status_code == 503
    assert "folder permissions" in response.json()["detail"]
    assert "internal path" not in response.text


def test_transfer_retry_checksum_and_same_size_corruption(client):
    import hashlib
    from uuid import uuid4
    payload = b"real-test-payload"
    headers = {"X-Transfer-ID": str(uuid4()), "X-Content-SHA256": hashlib.sha256(payload).hexdigest()}
    first = client.post("/api/files?name=delivery.txt", content=payload, headers=headers)
    assert first.status_code == 201
    retry = client.post("/api/files?name=delivery.txt", content=payload, headers=headers)
    assert retry.status_code == 201
    assert retry.json()["id"] == first.json()["id"]
    assert len(client.get("/api/files").json()["files"]) == 1
    assert client.post("/api/files?name=delivery.txt", content=b"different", headers=headers).status_code == 422
    headers.pop("X-Content-SHA256")
    assert client.post("/api/files?name=delivery.txt", content=b"different", headers=headers).status_code == 409
    row = first.json()
    Path(row["storage_path"]).write_bytes(b"x" * len(payload))
    assert client.get(f'/api/files/{row["id"]}/download').status_code == 409
    assert client.post(f'/api/files/{row["id"]}/prepare', json={}).status_code == 409
    assert not list(files.root().rglob("*.partial"))


def test_disk_reserve_rejects_before_writing(client, monkeypatch):
    from collections import namedtuple
    usage = namedtuple("usage", "total used free")
    monkeypatch.setattr(files.shutil, "disk_usage", lambda path: usage(100, 99, 1))
    assert client.post("/api/files?name=full.txt", content=b"data").status_code == 507
    assert client.get("/api/files").json()["files"] == []


def test_upload_publishes_complete_bytes_without_empty_placeholder(client, monkeypatch):
    link = files.os.link
    observed = []

    def publish_complete(source, destination):
        assert not destination.exists()
        assert source.read_bytes() == b"complete upload"
        link(source, destination)
        observed.append(destination.read_bytes())

    monkeypatch.setattr(files.os, "link", publish_complete)
    response = client.post("/api/files?name=complete.txt", content=b"complete upload")
    assert response.status_code == 201
    assert observed == [b"complete upload"]
    assert not list(files.root().rglob("*.partial"))


def test_upload_collision_never_replaces_or_removes_existing_bytes(client):
    from uuid import uuid4
    identifier = uuid4()
    path = files.location(identifier)
    path.write_bytes(b"previous interrupted transfer")
    response = client.post("/api/files?name=retry.txt", content=b"new upload",
                           headers={"X-Transfer-ID": str(identifier)})
    assert response.status_code == 409
    assert path.read_bytes() == b"previous interrupted transfer"
    assert not list(files.root().rglob("*.partial"))


def test_failed_publication_cleans_up_owned_files(client, monkeypatch):
    def fail_sync(folder):
        raise OSError("disk failure")

    monkeypatch.setattr(files, "sync_directory", fail_sync)
    assert client.post("/api/files?name=failed.txt", content=b"payload").status_code == 503
    assert list((files.root() / "originals").iterdir()) == []
    assert client.get("/api/files").json()["files"] == []


def test_storage_audit_does_not_create_missing_directories(database):
    from sqlalchemy.orm import Session
    from app.storage_check import inspect
    base = files.storage_root()
    assert not base.exists()
    with Session(database) as session:
        assert inspect(session) == []
    assert not base.exists()


def test_storage_audit_continues_after_unreadable_file(client, database, monkeypatch):
    from sqlalchemy.orm import Session
    from app.storage_check import inspect
    first = upload(client)
    second = upload(client)
    original_open = Path.open

    def open_checked(path, *args, **kwargs):
        if str(path) == first["storage_path"]:
            raise PermissionError("access denied")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", open_checked)
    with Session(database) as session:
        statuses = {item["id"]: item["status"] for item in inspect(session)}
    assert statuses[first["id"]] == "unreadable"
    assert statuses[second["id"]] == "verified"
