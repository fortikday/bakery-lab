"""Exercise imports through the same HTTP routes used by the browser."""

import csv
from datetime import date
from http.client import HTTPConnection
import io
import json
from pathlib import Path
import sys
import threading

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from csv_records import example_csv
from serve import make_server
from waste_log import LogStore


@pytest.fixture
def service(tmp_path):
    server = make_server(tmp_path / "http-import.sqlite3", port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()
    server.server_close()
    thread.join(timeout=3)


def call(service, path, payload=None):
    connection = HTTPConnection("127.0.0.1", service.server_port, timeout=10)
    connection.request("POST" if payload is not None else "GET", path,
                       body=json.dumps(payload) if payload is not None else None,
                       headers={"Content-Type": "application/json"} if payload is not None else {})
    response = connection.getresponse()
    result = response.status, dict(response.getheaders()), response.read().decode("utf-8-sig")
    connection.close()
    return result


def test_template_and_explicit_two_step_example_import(service):
    status, headers, text = call(service, "/api/import-template.csv")
    assert status == 200 and "attachment" in headers["Content-Disposition"]
    assert list(csv.DictReader(io.StringIO(text))) == []
    status, _, downloaded = call(service, "/api/import-example.csv")
    assert status == 200 and "fictional" in downloaded.lower()
    text = example_csv(date(2026, 10, 22))
    preview = json.loads(call(service, "/api/import/preview", {"csv_text": text})[2])
    assert preview["valid"] and preview["row_count"] == 20
    assert service.log_store.list_entries() == []
    status, _, body = call(service, "/api/import/commit", {"csv_text": text, "preview_token": preview["preview_token"]})
    assert status == 201 and json.loads(body)["imported_count"] == 20
    report = json.loads(call(service, "/api/report?week=2026-10-12")[2])
    assert report["comparison"]["current_days"] == report["comparison"]["previous_days"] == 5
    assert report["comparison"]["current_entry_count"] == report["comparison"]["previous_entry_count"] == 10
    assert report["comparison"]["metrics"]["finished_discarded"]["change"] == -12
    assert call(service, "/api/import/commit", {"csv_text": text, "preview_token": preview["preview_token"]})[0] == 409
    assert len(service.log_store.list_entries()) == 20


def test_csv_export_import_preserves_protected_names_and_literal_quotes(service, tmp_path):
    entry = {"kind": "finished_product", "record_date": "2026-10-19", "store": "=Example store",
             "product": "'@Literal name", "produced": 5, "sold": 5, "notes": "@A plain-text note"}
    assert call(service, "/api/entries", entry)[0] == 201
    status, _, exported = call(service, "/api/export.csv?week=2026-10-19")
    assert status == 200
    row = next(csv.DictReader(io.StringIO(exported)))
    assert row["store"].startswith("'") and row["product"].startswith("''")
    fresh = LogStore(tmp_path / "fresh.sqlite3")
    preview = fresh.preview_import(exported)
    assert preview["valid"]
    imported = fresh.commit_import(exported, preview["preview_token"])["entries"][0]
    for name in ("store", "product", "notes"):
        assert imported[name] == entry[name]
    # Downloading and reimporting into the original store never duplicates it.
    assert json.loads(call(service, "/api/import/preview", {"csv_text": exported})[2])["valid"] is False


def test_http_stale_preview_requires_another_review_and_saves_nothing(service):
    text = example_csv(date(2026, 10, 22))
    preview = json.loads(call(service, "/api/import/preview", {"csv_text": text})[2])
    service.log_store.create({"kind": "finished_product", "record_date": "2026-10-22", "store": "Other",
                             "product": "Bread", "produced": 1, "sold": 1})
    status, _, body = call(service, "/api/import/commit", {"csv_text": text, "preview_token": preview["preview_token"]})
    assert status == 409 and "preview" in json.loads(body)["error"].lower()
    assert len(service.log_store.list_entries()) == 1


def test_import_http_limit_and_invalid_unicode_return_errors(service):
    for text in ("x" * (2 * 1024 * 1024 + 1), "\ud800"):
        status, _, body = call(service, "/api/import/preview", {"csv_text": text})
        assert status == 400 and json.loads(body)["error"]
    assert service.log_store.list_entries() == []
