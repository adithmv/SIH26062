"""Exercise maintenance cleanup without connecting to any live Docker project."""
import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


def load_backup():
    path = Path(__file__).resolve().parents[2] / "deploy" / "backup.py"
    spec = importlib.util.spec_from_file_location("base_backup_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("fail_dump", [False, True])
def test_backup_manifest_and_restart_on_failure(tmp_path, monkeypatch, fail_dump):
    backup = load_backup()
    destination = tmp_path / "backup"
    calls = []
    def run(*args, **kwargs):
        calls.append(args)
        if args[0] == "ps":
            return SimpleNamespace(stdout="db\napi\nweb\n")
        if args[0] == "exec" and fail_dump:
            raise RuntimeError("simulated dump failure")
        if "stdout" in kwargs:
            kwargs["stdout"].write(b"isolated backup content")
        return SimpleNamespace()
    monkeypatch.setattr(backup, "run", run)
    monkeypatch.setattr(backup.sys, "argv", ["backup.py", str(destination)])
    if fail_dump:
        with pytest.raises(RuntimeError, match="dump failure"):
            backup.main()
        assert not (destination / "manifest.json").exists()
    else:
        backup.main()
        manifest = json.loads((destination / "manifest.json").read_text())
        for name, expected in manifest["sha256"].items():
            assert hashlib.sha256((destination / name).read_bytes()).hexdigest() == expected
    assert ("stop", "web", "api") in calls
    assert calls[-1] == ("start", "api", "web")
