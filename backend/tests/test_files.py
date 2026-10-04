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
