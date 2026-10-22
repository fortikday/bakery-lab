"""Desktop data placement and server ownership, without opening a real window."""

from http.client import HTTPConnection
import json
from pathlib import Path
import socket
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import desktop
import serve


def test_source_and_frozen_default_database_paths_are_separate(tmp_path, monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    source = desktop.default_database_path()
    assert source == Path(desktop.__file__).resolve().parent / "local" / "waste-log.sqlite3"
    user_data = tmp_path / "persistent-user-data"
    bundle = tmp_path / "temporary-bundle"
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(bundle), raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(user_data))
    assert desktop.resource_directory() == bundle
    assert desktop.default_database_path() == user_data / "BakeryLab" / "local" / "waste-log.sqlite3"
    assert not user_data.exists()
    assert not bundle.exists()


def test_session_serves_bundled_resources_and_releases_its_port(tmp_path):
    resources = tmp_path / "resources"
    resources.mkdir()
    (resources / "log.html").write_text("<h1>Bakery Lab isolated log</h1>", encoding="utf-8")
    (resources / "index.html").write_text("<h1>Bakery Lab isolated dashboard</h1>", encoding="utf-8")
    previous = serve.ROOT
    session = desktop.LocalSession(tmp_path / "private" / "check.sqlite3", resources=resources)
    try:
        url = session.start()
        assert url.startswith("http://127.0.0.1:")
        port = session.server.server_port
        assert port != 0
        worker = session.worker
        assert session.start() == url  # Opening again reuses the same local session.
        assert session.worker is worker
        connection = HTTPConnection("127.0.0.1", port, timeout=5)
        connection.request("GET", "/log.html")
        response = connection.getresponse()
        assert response.status == 200
        assert b"isolated log" in response.read()
        connection.close()
        assert session.db_path.is_file()
    finally:
        session.stop()
    assert not worker.is_alive()
    assert serve.ROOT == previous
    with socket.socket() as probe:
        assert probe.connect_ex(("127.0.0.1", port)) != 0
    session.stop()  # Closing twice is harmless.


def test_missing_pages_fail_before_opening_a_database(tmp_path):
    database = tmp_path / "private" / "check.sqlite3"
    session = desktop.LocalSession(database, resources=tmp_path)
    previous = serve.ROOT
    with pytest.raises(RuntimeError, match="page files are missing"):
        session.start()
    assert not database.exists()
    assert serve.ROOT == previous


def test_server_creation_failure_restores_resource_directory(tmp_path):
    resources = tmp_path / "resources"
    resources.mkdir()
    for name in ("log.html", "index.html"):
        (resources / name).write_text("Bakery Lab", encoding="utf-8")

    def unavailable_server(**kwargs):
        raise OSError("An isolated startup failure")

    previous = serve.ROOT
    session = desktop.LocalSession(tmp_path / "check.sqlite3", resources=resources,
                                   server_factory=unavailable_server)
    with pytest.raises(OSError, match="isolated startup failure"):
        session.start()
    assert serve.ROOT == previous
    assert session.server is None


def test_headless_check_requires_explicit_database_before_gui_or_defaults(monkeypatch):
    monkeypatch.setattr(desktop, "run_window", lambda *args: pytest.fail("Opened a GUI"))
    monkeypatch.setattr(desktop, "default_database_path", lambda: pytest.fail("Read a real default path"))
    with pytest.raises(SystemExit) as exc:
        desktop.main(["--check"])
    assert exc.value.code == 2


def test_headless_main_writes_status_report_without_gui(tmp_path, monkeypatch):
    database = tmp_path / "isolated.sqlite3"
    output = tmp_path / "report" / "check.json"
    seen = []
    monkeypatch.setattr(desktop, "run_window", lambda *args: pytest.fail("Opened a GUI"))
    monkeypatch.setattr(desktop, "default_database_path", lambda: pytest.fail("Read a real default path"))
    monkeypatch.setattr(desktop, "check_application", lambda path: seen.append(path) or {"ok": True, "checks": {}})
    assert desktop.main(["--check", "--db", str(database), "--check-output", str(output)]) == 0
    assert seen == [database]
    assert json.loads(output.read_text())["ok"] is True


def test_open_data_folder_uses_only_database_parent_on_windows(tmp_path, monkeypatch):
    database = tmp_path / "Bakery files with spaces" / "waste-log.sqlite3"
    opened = []
    monkeypatch.setattr(desktop.sys, "platform", "win32")
    monkeypatch.setattr(desktop.os, "startfile", opened.append, raising=False)
    assert desktop.open_data_folder(database) == database.parent
    assert opened == [str(database.parent)]
    assert database.parent.is_dir()
    assert not database.exists()


@pytest.mark.parametrize("platform, command", [("darwin", "open"), ("linux", "xdg-open")])
def test_open_data_folder_uses_argument_list_without_a_shell(tmp_path, monkeypatch, platform, command):
    database = tmp_path / "Bakery files ; fictional" / "waste-log.sqlite3"
    calls = []
    monkeypatch.setattr(desktop.sys, "platform", platform)
    monkeypatch.setattr(desktop.subprocess, "run", lambda args, **kwargs: calls.append((args, kwargs)))
    desktop.open_data_folder(database)
    assert calls[0][0] == [command, str(database.parent)]
    assert calls[0][1].get("shell", False) is False
    assert calls[0][1]["check"] is True


def test_console_launcher_opens_browser_and_stops_on_interrupt(tmp_path, capsys):
    database = tmp_path / "private" / "waste-log.sqlite3"
    events = []

    class FakeSession:
        def __init__(self, path):
            assert path == database

        def start(self):
            events.append("start")
            return "http://127.0.0.1:12345/log.html"

        def stop(self):
            events.append("stop")

    def browser(url, **kwargs):
        events.append(("browser", url))
        assert kwargs == {"new": 2}
        return True

    def interrupted():
        events.append("wait")
        raise KeyboardInterrupt

    assert desktop.run_console(database, wait_for_exit=interrupted, opener=browser,
                               session_factory=FakeSession) == 0
    assert events == ["start", ("browser", "http://127.0.0.1:12345/log.html"), "wait", "stop"]
    text = capsys.readouterr().out
    assert "Keep this window open" in text
    assert "Ctrl+C" in text
    assert str(database.parent) in text


def test_console_start_failure_returns_error_and_still_closes_session(tmp_path, monkeypatch, capsys):
    stopped = []

    class FakeSession:
        def __init__(self, path):
            pass

        def start(self):
            raise OSError("A fictional startup failure")

        def stop(self):
            stopped.append(True)

    monkeypatch.setattr(desktop.sys, "stdin", None)
    assert desktop.run_console(tmp_path / "check.sqlite3", session_factory=FakeSession,
                               opener=lambda *args, **kwargs: pytest.fail("Opened a browser")) == 1
    assert stopped == [True]
    assert "saved records have not been removed" in capsys.readouterr().out


@pytest.mark.parametrize("frozen, console, expected", [
    (False, False, "window"), (False, True, "console"), (True, False, "console"),
])
def test_frozen_build_uses_console_without_importing_tk(tmp_path, monkeypatch, frozen, console, expected):
    seen = []
    database = tmp_path / "explicit.sqlite3"
    monkeypatch.setattr(sys, "frozen", frozen, raising=False)
    monkeypatch.setattr(desktop, "run_window", lambda path: seen.append(("window", path)))
    monkeypatch.setattr(desktop, "run_console", lambda path: seen.append(("console", path)) or 0)
    monkeypatch.setattr(desktop, "default_database_path", lambda: pytest.fail("Used the real default data folder"))
    args = ["--db", str(database)] + (["--console"] if console else [])
    assert desktop.main(args) == 0
    assert seen == [(expected, database)]
