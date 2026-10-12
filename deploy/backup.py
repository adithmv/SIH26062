"""Create a consistent base backup during a short maintenance window.

Run from the repository root: python deploy/backup.py PATH_OUTSIDE_THE_REPOSITORY
Requires Docker Compose and a running base stack using .env.base.
"""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone

compose = ["docker", "compose", "--env-file", ".env.base", "-f", "compose.base.yaml"]


def run(*args, **kwargs):
    return subprocess.run([*compose, *args], check=True, **kwargs)


def main():
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python deploy/backup.py BACKUP_DIRECTORY")
    destination = Path(sys.argv[1]).resolve()
    destination.mkdir(parents=True, exist_ok=False)
    running = run("ps", "--status", "running", "--services", capture_output=True, text=True).stdout.splitlines()
    if not {"api", "db", "web"}.issubset(running):
        raise SystemExit("Start the complete base stack before creating a maintenance backup.")
    try:
        run("stop", "web", "api")
        with (destination / "database.dump").open("xb") as target:
            run("exec", "-T", "db", "pg_dump", "-U", "polar", "-Fc", "polar", stdout=target)
        with (destination / "files.tar.gz").open("xb") as target:
            run("run", "--rm", "--no-deps", "-T", "api", "tar", "-czf", "-", "-C", "/app/data/files", ".", stdout=target)
        checksums = {}
        for name in ("database.dump", "files.tar.gz"):
            with (destination / name).open("rb") as source:
                checksums[name] = hashlib.file_digest(source, "sha256").hexdigest()
        (destination / "manifest.json").write_text(json.dumps({"created_at": datetime.now(timezone.utc).isoformat(), "sha256": checksums}, indent=2))
        print("Backup completed. Keep this directory encrypted and copy it to separate storage.")
    finally:
        run("start", "api", "web")


if __name__ == "__main__":
    main()
