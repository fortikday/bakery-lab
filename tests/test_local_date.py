"""Dates follow the running computer's calendar, including at UTC week boundaries."""

import csv
from datetime import datetime, timedelta, timezone
from http.client import HTTPConnection
import io
import json
from pathlib import Path
import sys
import threading

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import serve


def get(service, path):
    connection = HTTPConnection("127.0.0.1", service.server_port, timeout=5)
    connection.request("GET", path)
    response = connection.getresponse()
    body = response.read().decode("utf-8-sig")
    connection.close()
    assert response.status == 200, body
    return body


@pytest.mark.parametrize("offset, local_date, week_start, latest_example_date", [
    (-8, "2026-10-18", "2026-10-12", "2026-10-09"),
    (14, "2026-10-19", "2026-10-19", "2026-10-16"),
])
def test_config_default_filters_and_example_use_same_local_calendar(
        tmp_path, monkeypatch, offset, local_date, week_start, latest_example_date):
    instant = datetime(2026, 10, 19, 0, 30, tzinfo=timezone.utc)
    local_now = instant.astimezone(timezone(timedelta(hours=offset)))
    monkeypatch.setattr(serve, "_local_now", lambda: local_now)
    service = serve.make_server(tmp_path / "calendar.sqlite3", port=0)
    for day in ("2026-10-18", "2026-10-19"):
        service.log_store.create({"record_date": day, "store": "Fictional test bakery",
                                  "product": "Bread", "kind": "finished_product",
                                  "produced": 1, "sold": 1})
    worker = threading.Thread(target=service.serve_forever, daemon=True)
    worker.start()
    try:
        config = json.loads(get(service, "/api/config"))
        assert config["today"] == local_date
        assert config["timezone"] == local_now.tzname()
        assert config["version"] == 3
        report = json.loads(get(service, "/api/report"))
        assert report["week_start"] == week_start
        entries = json.loads(get(service, "/api/entries"))["entries"]
        assert [entry["record_date"] for entry in entries] == [local_date]
        exported = list(csv.DictReader(io.StringIO(get(service, "/api/export.csv"))))
        assert [entry["record_date"] for entry in exported] == [local_date]
        example = list(csv.DictReader(io.StringIO(get(service, "/api/import-example.csv"))))
        assert len(example) == 20
        assert max(entry["record_date"] for entry in example) == latest_example_date
    finally:
        service.shutdown()
        service.server_close()
        worker.join(timeout=3)


def test_local_clock_is_read_again_when_computer_time_changes(monkeypatch):
    times = iter([
        datetime(2026, 10, 25, 2, 59, tzinfo=timezone(timedelta(hours=2), "Summer")),
        datetime(2026, 10, 25, 2, 0, tzinfo=timezone(timedelta(hours=1), "Winter")),
    ])

    # astimezone() normally reads the machine zone. Supply an aware stand-in
    # whose local conversion preserves the simulated zone for this isolated test.
    class LocalMoment:
        def __init__(self, value):
            self.value = value

        def astimezone(self):
            return self.value

    class LocalClock:
        @staticmethod
        def now():
            return LocalMoment(next(times))

    monkeypatch.setattr(serve, "datetime", LocalClock)
    assert serve._local_now().utcoffset() == timedelta(hours=2)
    assert serve._local_now().utcoffset() == timedelta(hours=1)
