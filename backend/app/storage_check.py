"""Read-only file integrity audit; never deletes or rewrites stored files."""
import hashlib
import json
from sqlalchemy import select
from sqlalchemy.orm import Session
from .db import engine
from .files import location, root
from .models import ManagedFile, PreparedFile


def inspect(session):
    results = []
    known = set()
    for model, prepared in ((ManagedFile, False), (PreparedFile, True)):
        for row in session.scalars(select(model)):
            path = location(row.id, prepared)
            known.add(path)
            state = "verified"
            if not path.is_file():
                state = "missing"
            else:
                with path.open("rb") as stream:
                    checksum = hashlib.file_digest(stream, "sha256").hexdigest()
                if path.stat().st_size != row.size or (row.sha256 and checksum != row.sha256):
                    state = "damaged"
                elif not row.sha256:
                    state = "legacy-no-checksum"
            results.append({"id": str(row.id), "path": str(path), "status": state})
    for folder in (root() / "originals", root() / "prepared"):
        if folder.exists():
            for path in folder.iterdir():
                if path.is_file() and path not in known:
                    results.append({"path": str(path), "status": "unreferenced"})
    return results


def main():
    with Session(engine) as session:
        results = inspect(session)
    print(json.dumps(results, indent=2))
    if any(row["status"] != "verified" for row in results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
