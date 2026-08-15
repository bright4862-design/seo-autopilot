from app import main


def test_health_and_revision_expose_worker_source_sha(monkeypatch):
    monkeypatch.setattr(main, "WORKER_SOURCE_SHA", "a" * 40)
    assert main.health_payload()["source_sha"] == "a" * 40
    assert main.revision()["source_sha"] == "a" * 40


def test_unstamped_local_worker_is_explicitly_blank(monkeypatch):
    monkeypatch.setattr(main, "WORKER_SOURCE_SHA", "")
    assert main.health_payload()["source_sha"] == ""
