import sys

from fastapi import HTTPException

from app import pmce_worker


def test_worker_runs_requested_profile_and_stops(monkeypatch, database):
    monkeypatch.setattr(pmce_worker, "engine", database)
    monkeypatch.setattr(sys, "argv", ["pmce_worker", "--mode", "limited", "--byte-budget", "1024"])
    calls = []

    def run(options, session):
        calls.append(options)
        return []

    def stop(seconds):
        assert seconds == 5
        raise KeyboardInterrupt

    monkeypatch.setattr(pmce_worker, "sync", run)
    monkeypatch.setattr(pmce_worker.time, "sleep", stop)
    pmce_worker.main()
    assert len(calls) == 1
    assert calls[0].mode == "limited"
    assert calls[0].byte_budget == 1024


def test_worker_waits_when_another_sync_owns_lease(monkeypatch, database):
    monkeypatch.setattr(pmce_worker, "engine", database)
    monkeypatch.setattr(sys, "argv", ["pmce_worker"])
    waits = []

    def busy(options, session):
        assert options.mode == "offline"
        raise HTTPException(409, "Already running")

    def stop(seconds):
        waits.append(seconds)
        raise KeyboardInterrupt

    monkeypatch.setattr(pmce_worker, "sync", busy)
    monkeypatch.setattr(pmce_worker.time, "sleep", stop)
    pmce_worker.main()
    assert waits == [5]
