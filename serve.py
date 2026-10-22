"""Run Bakery Lab locally: a daily log, weekly report and sales experiment.

Uses only the Python standard library. New records are saved in SQLite on this
computer. Only the two public HTML pages and explicit API routes are served.
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
from pathlib import Path
import re
from urllib.parse import parse_qs, urlsplit
import webbrowser

from waste_log import ConflictError, LogStore, NotFoundError
from csv_records import CSV_FIELDS, EXPORT_FORMAT, example_csv, template_csv

ROOT = Path(__file__).resolve().parent
EXPORT_FIELDS = CSV_FIELDS


def _local_now():
    """Read the computer's current local time, including its current DST offset."""
    return datetime.now().astimezone()


def _csv_value(value):
    # Names and notes remain plain text if the CSV is opened in a spreadsheet.
    if isinstance(value, str) and (value.startswith("'") or value.lstrip().startswith(("=", "+", "-", "@", "\t", "\r"))):
        return "'" + value
    return value


def _reject_nonfinite(value):
    raise ValueError("Use finite numbers in the daily log.")


def make_server(db_path=None, port=8765):
    """Create a loopback-only server; port=0 is useful for isolated tests."""
    store = LogStore(db_path or ROOT / "local" / "waste-log.sqlite3")

    class Handler(BaseHTTPRequestHandler):
        def _respond(self, status, body, content_type="application/json; charset=utf-8", **headers):
            if content_type.startswith("application/json"):
                body = json.dumps(body, ensure_ascii=False, allow_nan=False).encode("utf-8")
            elif isinstance(body, str):
                body = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "same-origin")
            for key, value in headers.items():
                self.send_header(key.replace("_", "-"), value)
            self.end_headers()
            self.wfile.write(body)

        def _check_local(self):
            port_number = self.server.server_port
            allowed_hosts = {f"127.0.0.1:{port_number}", f"localhost:{port_number}"}
            if self.headers.get("Host") not in allowed_hosts:
                self._respond(403, {"error": "Open Bakery Lab using its local address."})
                return False
            origin = self.headers.get("Origin")
            if origin is not None and origin not in {f"http://{host}" for host in allowed_hosts}:
                self._respond(403, {"error": "Open the daily log on the same local Bakery Lab address."})
                return False
            return True

        def _body(self, maximum=65536):
            if self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower() != "application/json":
                raise ValueError("Send entries as JSON from the daily log form.")
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError as exc:
                raise ValueError("Invalid request size.") from exc
            if not 0 < length <= maximum:
                raise ValueError("The entry is empty or too large.")
            try:
                payload = json.loads(self.rfile.read(length).decode("utf-8"), parse_constant=_reject_nonfinite)
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ValueError("The entry must contain valid JSON.") from exc
            if not isinstance(payload, dict):
                raise ValueError("The entry must be a JSON object.")
            return payload

        def _filters(self):
            query = parse_qs(urlsplit(self.path).query)
            today = _local_now().date().isoformat()
            return {"week": query.get("week", [today])[0], "store": query.get("store", [None])[0]}

        def _dispatch(self):
            if not self._check_local():
                return
            path = urlsplit(self.path).path
            method = self.command
            if method == "GET":
                if path in {"/", "/log.html", "/index.html"}:
                    name = "log.html" if path == "/" else path.lstrip("/")
                    file_path = ROOT / name
                    if not file_path.is_file():
                        self._respond(404, {"error": "This page has not been generated yet."})
                    else:
                        self._respond(200, file_path.read_bytes(), "text/html; charset=utf-8")
                elif path == "/favicon.ico":
                    self._respond(204, b"", "image/x-icon")
                elif path == "/api/config":
                    local_now = _local_now()
                    self._respond(200, {"today": local_now.date().isoformat(),
                                        "timezone": local_now.tzname() or str(local_now.tzinfo),
                                        "storage": "local", "version": 3})
                elif path == "/api/entries":
                    query = parse_qs(urlsplit(self.path).query)
                    self._respond(200, {"entries": store.list_entries(
                        **self._filters(), include_archived=query.get("include_archived", ["0"])[0] == "1"
                    )})
                elif path == "/api/report":
                    self._respond(200, store.weekly_report(**self._filters()))
                elif path == "/api/export.csv":
                    filters = self._filters()
                    stream = io.StringIO(newline="")
                    writer = csv.DictWriter(stream, fieldnames=EXPORT_FIELDS, extrasaction="ignore")
                    writer.writeheader()
                    for entry in store.list_entries(**filters):
                        entry = entry | {"csv_format": EXPORT_FORMAT}
                        writer.writerow({key: _csv_value(entry.get(key)) for key in EXPORT_FIELDS})
                    self._respond(200, "\ufeff" + stream.getvalue(), "text/csv; charset=utf-8",
                                  Content_Disposition='attachment; filename="bakery-weekly-log.csv"')
                elif path in {"/api/import-template.csv", "/api/import-example.csv"}:
                    example = path == "/api/import-example.csv"
                    today = _local_now().date()
                    content = example_csv(today) if example else template_csv()
                    filename = "bakery-fictional-example.csv" if example else "bakery-import-template.csv"
                    self._respond(200, "\ufeff" + content, "text/csv; charset=utf-8",
                                  Content_Disposition=f'attachment; filename="{filename}"')
                else:
                    self._respond(404, {"error": "This page or endpoint does not exist."})
                return
            if method == "POST" and path == "/api/entries":
                self._respond(201, {"entry": store.create(self._body())})
                return
            if method == "POST" and path in {"/api/import/preview", "/api/import/commit"}:
                payload = self._body(maximum=6 * 1024 * 1024)
                if path.endswith("/preview"):
                    self._respond(200, store.preview_import(payload.get("csv_text")))
                else:
                    self._respond(201, store.commit_import(payload.get("csv_text"), payload.get("preview_token")))
                return
            match = re.fullmatch(r"/api/entries/([a-f0-9-]{36})(/restore)?", path)
            if match:
                entry_id, restore = match.groups()
                payload = self._body()
                if restore and method == "POST":
                    self._respond(200, {"entry": store.restore(entry_id, payload.get("revision"))})
                elif not restore and method == "PUT":
                    self._respond(200, {"entry": store.update(entry_id, payload)})
                elif not restore and method == "DELETE":
                    self._respond(200, {"entry": store.archive(entry_id, payload.get("revision"))})
                else:
                    self._respond(405, {"error": "This action is not supported."})
                return
            self._respond(404, {"error": "This entry or endpoint does not exist."})

        def _handle(self):
            try:
                self._dispatch()
            except ConflictError as exc:
                self._respond(409, {"error": str(exc)})
            except NotFoundError as exc:
                self._respond(404, {"error": str(exc)})
            except ValueError as exc:
                self._respond(400, {"error": str(exc)})
            except Exception:
                self.log_error("Unexpected error while processing a local request")
                self._respond(500, {"error": "The entry could not be processed. Please refresh and try again."})

        do_GET = _handle
        do_POST = _handle
        do_PUT = _handle
        do_DELETE = _handle

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.log_store = store
    return server


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--db", type=Path, help="Optional SQLite file location")
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    server = make_server(db_path=args.db, port=args.port)
    url = f"http://127.0.0.1:{server.server_port}/log.html"
    print(f"Bakery Lab: {url}  (Ctrl+C to stop)", flush=True)
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
