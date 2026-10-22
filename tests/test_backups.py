"""Recovery copies preserve committed records and never turn a save into failure."""

from contextlib import closing
from datetime import datetime, timedelta, timezone
from http.client import HTTPConnection
import json
from pathlib import Path
import sqlite3
import sys
import threading
import uuid

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import serve
from backups import AUTOMATIC_WARNING, BackupManager
from waste_log import LogStore


def finished(**changes):
    return {"record_date": "2026-10-22", "store": "Fictional bakery", "product": "Bread",
            "kind": "finished_product", "produced": 10, "sold": 8, "discarded": 2,
            "reason": "overproduction"} | changes


@pytest.fixture
def service(tmp_path):
    server = serve.make_server(tmp_path / "personal.sqlite3", port=0)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=3)


def request(server, path, payload=None, method=None, headers=None):
    connection = HTTPConnection("127.0.0.1", server.server_port, timeout=10)
    request_headers = {} if headers is None else dict(headers)
    body = None if payload is None else json.dumps(payload)
    if body is not None:
        request_headers["Content-Type"] = "application/json"
    connection.request(method or ("POST" if payload is not None else "GET"), path, body=body, headers=request_headers)
    response = connection.getresponse()
    data = response.read()
    result = response.status, dict(response.getheaders()), data
    connection.close()
    return result


def response_json(server, path, payload=None, method=None):
    status, _, body = request(server, path, payload, method)
    return status, json.loads(body)


def rows(path):
    with closing(sqlite3.connect(path)) as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        return connection.execute("SELECT id, revision, deleted, payload FROM entries ORDER BY id").fetchall()


def test_empty_log_has_no_misleading_automatic_copy_but_download_is_valid(service, tmp_path):
    _, config = response_json(service, "/api/config")
    assert config["backup"] == {"automatic": True, "latest_date": None, "last_error": None,
                                "has_records": False, "download_url": "/api/backup.sqlite3",
                                "revision": 1, "instance_id": config["backup"]["instance_id"]}
    assert str(uuid.UUID(config["backup"]["instance_id"])) == config["backup"]["instance_id"]
    assert not service.backup_manager.directory.exists()
    status, headers, content = request(service, "/api/backup.sqlite3")
    assert status == 200
    assert headers["Content-Type"] == "application/vnd.sqlite3"
    assert 'attachment; filename="bakery-backup-' in headers["Content-Disposition"]
    downloaded = tmp_path / "empty-download.sqlite3"
    downloaded.write_bytes(content)
    assert rows(downloaded) == []
    assert not service.backup_manager.directory.exists()


def test_full_download_includes_all_weeks_stores_archived_records_and_revisions(service, tmp_path):
    _, created = response_json(service, "/api/entries", finished())
    entry = created["entry"]
    _, edited = response_json(service, "/api/entries/" + entry["id"],
                              finished(notes="Corrected fictional record", revision=entry["revision"]), "PUT")
    _, archived = response_json(service, "/api/entries/" + entry["id"],
                                {"revision": edited["entry"]["revision"]}, "DELETE")
    response_json(service, "/api/entries", finished(record_date="2026-09-01", store="Another fictional store"))
    before = rows(service.log_store.path)
    status, _, content = request(service, "/api/backup.sqlite3?week=2026-10-22&store=Fictional%20bakery")
    assert status == 200
    destination = tmp_path / "download.sqlite3"
    destination.write_bytes(content)
    assert rows(destination) == before
    assert len(before) == 2
    assert any(row[1:3] == (3, 1) for row in before)
    assert archived["entry"]["deleted"] is True
    assert rows(service.log_store.path) == before


def test_sqlite_snapshot_includes_committed_wal_contents(tmp_path):
    store = LogStore(tmp_path / "wal.sqlite3")
    with closing(sqlite3.connect(store.path)) as keeper:
        assert keeper.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal"
        keeper.execute("PRAGMA wal_autocheckpoint=0")
        keeper.execute("BEGIN")
        keeper.execute("SELECT COUNT(*) FROM entries").fetchone()
        entry = store.create(finished())
        store.update(entry["id"], finished(notes="Lives in WAL", revision=entry["revision"]))
        wal_path = Path(str(store.path) + "-wal")
        assert wal_path.is_file() and wal_path.stat().st_size > 0
        manager = BackupManager(store.path, lambda: datetime(2026, 10, 22, tzinfo=timezone.utc))
        destination = tmp_path / "wal-download.sqlite3"
        destination.write_bytes(manager.download())
        assert rows(destination) == rows(store.path)
        assert json.loads(rows(destination)[0][3])["notes"] == "Lives in WAL"


def test_automatic_copy_refreshed_after_every_entry_mutation(service):
    _, result = response_json(service, "/api/entries", finished())
    assert result["backup"]["has_records"] is True
    assert result["backup"]["latest_date"] is not None
    copied = service.backup_manager.directory / (result["backup"]["latest_date"] + ".sqlite3")
    entry = result["entry"]
    assert rows(copied) == rows(service.log_store.path)
    for method, payload in [
        ("PUT", finished(notes="Edited", revision=1)),
        ("DELETE", {"revision": 2}),
        ("POST", {"revision": 3}),
    ]:
        path = "/api/entries/" + entry["id"] + ("/restore" if method == "POST" else "")
        status, saved = response_json(service, path, payload, method)
        assert status == 200
        assert "backup_warning" not in saved
        assert rows(copied) == rows(service.log_store.path)
    assert rows(copied)[0][1:3] == (4, 0)


def test_import_preview_does_not_backup_and_commit_copies_entire_import(service):
    csv_text = "record_date,store,product,kind,produced,sold\n2026-10-22,Fictional bakery,Cake,finished_product,5,5\n"
    _, preview = response_json(service, "/api/import/preview", {"csv_text": csv_text})
    assert preview["valid"]
    assert not service.backup_manager.directory.exists()
    status, result = response_json(service, "/api/import/commit", {
        "csv_text": csv_text, "preview_token": preview["preview_token"]})
    assert status == 201 and result["imported_count"] == 1
    copied = service.backup_manager.directory / (result["backup"]["latest_date"] + ".sqlite3")
    assert rows(copied) == rows(service.log_store.path)


def test_daily_copies_keep_previous_date_and_use_computer_local_day(service, monkeypatch):
    local_now = [datetime(2026, 10, 22, 0, 30, tzinfo=timezone(timedelta(hours=14)))]
    monkeypatch.setattr(serve, "_local_now", lambda: local_now[0])
    response_json(service, "/api/entries", finished())
    previous = service.backup_manager.directory / "2026-10-22.sqlite3"
    original = previous.read_bytes()
    local_now[0] += timedelta(days=1)
    response_json(service, "/api/entries", finished(product="Cake"))
    assert previous.read_bytes() == original
    latest = service.backup_manager.directory / "2026-10-23.sqlite3"
    assert len(rows(previous)) == 1
    assert len(rows(latest)) == 2
    assert service.backup_manager.status()["latest_date"] == "2026-10-23"


def test_backup_failure_still_reports_successful_save_and_can_recover(service, monkeypatch):
    original = service.backup_manager._write_snapshot
    def fail(_):
        raise PermissionError("Private machine path must never enter the response")
    monkeypatch.setattr(service.backup_manager, "_write_snapshot", fail)
    status, result = response_json(service, "/api/entries", finished())
    assert status == 201
    assert len(rows(service.log_store.path)) == 1
    assert result["backup"]["last_error"] == AUTOMATIC_WARNING
    assert "records were saved" in result["backup_warning"]
    assert "Private machine" not in json.dumps(result)
    assert service.backup_manager.status()["latest_date"] is None
    assert {item.name for item in service.backup_manager.directory.iterdir()} == {".snapshot-lock.sqlite3"}
    monkeypatch.setattr(service.backup_manager, "_write_snapshot", original)
    _, result = response_json(service, "/api/entries", finished(product="Cake"))
    assert result["backup"]["last_error"] is None
    assert "backup_warning" not in result
    assert len(rows(service.log_store.path)) == 2


def test_failed_atomic_replacement_preserves_earlier_copy(service, monkeypatch):
    _, first = response_json(service, "/api/entries", finished())
    copied = service.backup_manager.directory / (first["backup"]["latest_date"] + ".sqlite3")
    previous = copied.read_bytes()
    def fail_replace(self, _):
        raise OSError("Simulated failure while replacing a recovery copy")
    monkeypatch.setattr(Path, "replace", fail_replace)
    status, second = response_json(service, "/api/entries", finished(product="Cake"))
    assert status == 201
    assert second["backup_warning"]
    assert copied.read_bytes() == previous
    assert len(rows(copied)) == 1 and len(rows(service.log_store.path)) == 2
    assert {item.name for item in service.backup_manager.directory.iterdir()} == {copied.name, ".snapshot-lock.sqlite3"}


def test_unexpected_backup_error_cannot_turn_committed_save_into_failure(service, monkeypatch):
    def fail():
        raise RuntimeError("Unexpected failure after the entry was committed")
    monkeypatch.setattr(service.backup_manager, "refresh", fail)
    status, result = response_json(service, "/api/entries", finished())
    assert status == 201 and result["entry"]["product"] == "Bread"
    assert len(rows(service.log_store.path)) == 1
    assert result["backup_warning"]
    assert result["backup"]["revision"] > 1
    assert str(uuid.UUID(result["backup"]["instance_id"])) == result["backup"]["instance_id"]
    _, config = response_json(service, "/api/config")
    assert config["backup"]["last_error"] == AUTOMATIC_WARNING
    assert config["backup"]["revision"] == result["backup"]["revision"]


def test_status_versions_order_success_failure_and_recovery_without_get_advancing_them(service, monkeypatch):
    _, saved = response_json(service, "/api/entries", finished())
    earlier_success = saved["backup"]
    original_write = service.backup_manager._write_snapshot

    def fail(_):
        raise PermissionError("Simulated automatic backup failure")

    monkeypatch.setattr(service.backup_manager, "_write_snapshot", fail)
    _, failed = response_json(service, "/api/entries", finished(product="Cake"))
    newer_failure = failed["backup"]
    _, config = response_json(service, "/api/config")
    assert config["backup"]["revision"] == newer_failure["revision"]
    assert config["backup"]["instance_id"] == earlier_success["instance_id"]
    assert earlier_success["last_error"] is None
    assert newer_failure["last_error"] == AUTOMATIC_WARNING

    monkeypatch.setattr(service.backup_manager, "_write_snapshot", original_write)
    _, recovered = response_json(service, "/api/entries", finished(product="Croissant"))
    recovery = recovered["backup"]
    assert earlier_success["revision"] < newer_failure["revision"] < recovery["revision"]
    assert earlier_success["instance_id"] == newer_failure["instance_id"] == recovery["instance_id"]
    assert recovery["last_error"] is None
    _, config = response_json(service, "/api/config")
    assert config["backup"]["revision"] == recovery["revision"]


def test_download_failure_leaves_records_unchanged(service, monkeypatch):
    response_json(service, "/api/entries", finished())
    before = rows(service.log_store.path)
    monkeypatch.setattr(service.backup_manager, "download", lambda: (_ for _ in ()).throw(OSError("Private path")))
    status, _, body = request(service, "/api/backup.sqlite3")
    assert status == 500
    assert "records have not changed" in json.loads(body)["error"]
    assert "Private path" not in body.decode()
    assert rows(service.log_store.path) == before


def test_download_local_guards_and_private_paths(service):
    response_json(service, "/api/entries", finished())
    assert request(service, "/api/backup.sqlite3", headers={"Host": "untrusted.example"})[0] == 403
    assert request(service, "/api/backup.sqlite3", headers={"Origin": "https://untrusted.example"})[0] == 403
    assert request(service, "/local/waste-log.sqlite3")[0] == 404
    assert request(service, "/personal.sqlite3-backups/2026-10-22.sqlite3")[0] == 404


def test_windowed_desktop_without_stderr_can_load_save_and_download(service, monkeypatch):
    with monkeypatch.context() as patch:
        patch.setattr(serve.sys, "stderr", None)
        config_status, config = response_json(service, "/api/config")
        save_status, result = response_json(service, "/api/entries", finished())
        backup_status, _, content = request(service, "/api/backup.sqlite3")
    assert config_status == 200 and config["storage"] == "local"
    assert save_status == 201 and result["entry"]["product"] == "Bread"
    assert backup_status == 200 and content.startswith(b"SQLite format 3\x00")


def test_existing_nonempty_log_gets_recovery_copy_on_startup(tmp_path, monkeypatch):
    database = tmp_path / "existing.sqlite3"
    store = LogStore(database)
    store.create(finished())
    monkeypatch.setattr(serve, "_local_now", lambda: datetime(2026, 10, 22, tzinfo=timezone.utc))
    server = serve.make_server(database, port=0)
    try:
        copied = server.backup_manager.directory / "2026-10-22.sqlite3"
        assert rows(copied) == rows(database)
    finally:
        server.server_close()


def test_two_app_instances_cannot_replace_a_newer_copy_with_a_stale_snapshot(tmp_path, monkeypatch):
    store = LogStore(tmp_path / "shared.sqlite3")
    store.create(finished())
    now = lambda: datetime(2026, 10, 22, tzinfo=timezone.utc)
    first, second = BackupManager(store.path, now), BackupManager(store.path, now)
    snapshot_ready, release_first, second_started = threading.Event(), threading.Event(), threading.Event()
    original_write = first._write_snapshot
    results = {}

    def pause_after_snapshot(destination):
        original_write(destination)
        snapshot_ready.set()
        assert release_first.wait(timeout=5), "The test did not release the first snapshot"

    def refresh_second():
        second_started.set()
        results["second"] = second.refresh()

    monkeypatch.setattr(first, "_write_snapshot", pause_after_snapshot)
    first_worker = threading.Thread(target=lambda: results.update(first=first.refresh()), daemon=True)
    second_worker = threading.Thread(target=refresh_second, daemon=True)
    first_worker.start()
    try:
        assert snapshot_ready.wait(timeout=5)
        # Another SQLite connection (and therefore another process) must be
        # excluded until first publishes its already-taken snapshot.
        with closing(sqlite3.connect(first.directory / ".snapshot-lock.sqlite3", timeout=0)) as contender:
            with pytest.raises(sqlite3.OperationalError, match="locked"):
                contender.execute("BEGIN IMMEDIATE")
        # The sidecar lock must leave the actual log writable. A manual download
        # is independent and can also include this new committed record now.
        store.create(finished(product="Cake"))
        independent = tmp_path / "independent-download.sqlite3"
        independent.write_bytes(second.download())
        assert len(rows(independent)) == 2
        second_worker.start()
        assert second_started.wait(timeout=5)
    finally:
        release_first.set()
        first_worker.join(timeout=5)
        if second_worker.ident is not None:
            second_worker.join(timeout=5)
    assert not first_worker.is_alive() and not second_worker.is_alive()
    assert results["first"]["last_error"] is None
    assert results["second"]["last_error"] is None
    copied = first.directory / "2026-10-22.sqlite3"
    assert rows(copied) == rows(store.path)
    assert len(rows(copied)) == 2
    assert first.status()["latest_date"] == "2026-10-22"
