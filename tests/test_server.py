"""Verify the real local HTTP interface, not just its Python implementation."""

import csv
from http.client import HTTPConnection
import io
import json
from pathlib import Path
import sys
import threading

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from serve import make_server


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    service = make_server(tmp_path_factory.mktemp("http-log") / "test.sqlite3", port=0)
    worker = threading.Thread(target=service.serve_forever, daemon=True)
    worker.start()
    yield service
    service.shutdown()
    service.server_close()
    worker.join(timeout=3)


def request(server, method, path, payload=None, headers=None, raw=None):
    body = json.dumps(payload) if payload is not None else raw
    supplied = {"Content-Type": "application/json"} if body is not None else {}
    supplied.update(headers or {})
    connection = HTTPConnection("127.0.0.1", server.server_port, timeout=5)
    connection.request(method, path, body=body, headers=supplied)
    response = connection.getresponse()
    result = response.status, dict(response.getheaders()), response.read().decode("utf-8-sig")
    connection.close()
    return result


def test_create_report_export_edit_archive_and_restore_over_http(server):
    payload = {"kind": "finished_product", "record_date": "2026-10-21", "store": "Test store",
               "product": "Bread", "produced": 12, "sold": 9, "donated": 1, "discarded": 2,
               "reason": "overproduction", "unit_cost": "0.60", "currency": "GBP"}
    status, _, body = request(server, "POST", "/api/entries", payload)
    assert status == 201
    entry = json.loads(body)["entry"]
    status, headers, body = request(server, "GET", "/api/report?week=2026-10-21")
    report = json.loads(body)
    assert status == 200
    assert report["totals"]["finished_discarded"] == 2
    assert report["costs"] == [{"currency": "GBP", "estimated_cost": "1.20"}]
    assert headers["Cache-Control"] == "no-store"
    status, headers, body = request(server, "GET", "/api/export.csv?week=2026-10-21")
    assert status == 200 and "attachment" in headers["Content-Disposition"]
    assert list(csv.DictReader(io.StringIO(body)))[0]["product"] == "Bread"
    payload.update(revision=entry["revision"], notes="Reviewed counts")
    status, _, body = request(server, "PUT", f"/api/entries/{entry['id']}", payload)
    assert status == 200
    edited = json.loads(body)["entry"]
    assert edited["revision"] == 2
    assert request(server, "PUT", f"/api/entries/{entry['id']}", payload)[0] == 409
    status, _, body = request(server, "DELETE", f"/api/entries/{entry['id']}", {"revision": 2})
    assert status == 200
    archived = json.loads(body)["entry"]
    assert archived["deleted"] is True
    assert json.loads(request(server, "GET", "/api/entries?week=2026-10-21")[2])["entries"] == []
    recoverable = json.loads(request(server, "GET", "/api/entries?week=2026-10-21&include_archived=1")[2])["entries"]
    assert len(recoverable) == 1 and recoverable[0]["deleted"] is True
    assert request(server, "POST", f"/api/entries/{entry['id']}/restore", {"revision": archived["revision"]})[0] == 200


@pytest.mark.parametrize("path", ["/local/waste-log.sqlite3", "/../waste_log.py", "/data/train.csv"])
def test_only_explicit_public_pages_are_served(server, path):
    assert request(server, "GET", path)[0] == 404


def test_unrelated_origins_and_hosts_cannot_use_the_log(server):
    assert request(server, "GET", "/api/config", headers={"Origin": "https://unrelated.example"})[0] == 403
    assert request(server, "GET", "/api/config", headers={"Host": "unrelated.example"})[0] == 403


@pytest.mark.parametrize("raw", ['{"kind":[]}', '{"kind":"production_waste","waste_kg":NaN}', '[]'])
def test_invalid_inputs_return_readable_validation_errors(server, raw):
    status, _, body = request(server, "POST", "/api/entries", raw=raw)
    assert status == 400
    assert isinstance(json.loads(body)["error"], str)
