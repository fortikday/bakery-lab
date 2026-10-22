"""A small desktop launcher for Bakery Lab's local browser app.

The packaged Windows app includes Python and its HTML resources. Its database
belongs in the user's persistent local application-data folder, not PyInstaller's
temporary resource directory. Packaged builds use a small console window;
source users with a working Tkinter installation can use the desktop window.
"""

from __future__ import annotations

import argparse
from http.client import HTTPConnection
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import webbrowser

import serve


def resource_directory() -> Path:
    """Locate bundled pages without using that folder for private records."""
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))


def default_database_path() -> Path:
    if not getattr(sys, "frozen", False):
        return Path(__file__).resolve().parent / "local" / "waste-log.sqlite3"
    if os.environ.get("LOCALAPPDATA"):
        data_root = Path(os.environ["LOCALAPPDATA"])
    elif os.name == "nt":
        data_root = Path.home() / "AppData" / "Local"
    else:
        data_root = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return data_root / "BakeryLab" / "local" / "waste-log.sqlite3"


def open_data_folder(db_path: Path) -> Path:
    """Open only this installation's data folder, with no shell command text."""
    folder = Path(db_path).resolve().parent
    folder.mkdir(parents=True, exist_ok=True)
    if sys.platform == "win32":
        os.startfile(str(folder))
    else:
        command = "open" if sys.platform == "darwin" else "xdg-open"
        subprocess.run([command, str(folder)], check=True, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, timeout=10)
    return folder


class LocalSession:
    """Own one local server and release it when the launcher closes."""

    def __init__(self, db_path: Path, *, resources: Path | None = None, server_factory=None):
        self.db_path = Path(db_path)
        self.resources = Path(resources) if resources is not None else resource_directory()
        self.server_factory = server_factory or serve.make_server
        self.server = None
        self.worker = None
        self._previous_resources = None

    @property
    def url(self):
        if self.server is None:
            return None
        return f"http://127.0.0.1:{self.server.server_port}/log.html"

    def start(self):
        if self.server is not None:
            return self.url
        for name in ("log.html", "index.html"):
            if not (self.resources / name).is_file():
                raise RuntimeError("Bakery Lab's page files are missing. Extract the complete download and try again.")
        self._previous_resources = serve.ROOT
        serve.ROOT = self.resources
        try:
            self.server = self.server_factory(db_path=self.db_path, port=0)
            self.server.quiet = True
            self.worker = threading.Thread(
                target=self.server.serve_forever,
                kwargs={"poll_interval": 0.1},
                name="BakeryLab-local-server",
                daemon=True,
            )
            self.worker.start()
        except Exception:
            if self.server is not None:
                self.server.server_close()
            self.server = None
            self.worker = None
            serve.ROOT = self._previous_resources
            raise
        return self.url

    def stop(self):
        if self.server is None:
            return
        service, worker = self.server, self.worker
        self.server = None
        self.worker = None
        try:
            try:
                if worker is not None and worker.is_alive():
                    service.shutdown()
                    worker.join(timeout=3)
            finally:
                service.server_close()
        finally:
            if self._previous_resources is not None:
                serve.ROOT = self._previous_resources
                self._previous_resources = None


def check_application(db_path: Path) -> dict:
    """Exercise a packaged build without opening a window or browser.

    The caller supplies an isolated database. Report statuses and metadata only;
    backup bytes and individual records are never put into the check report.
    """
    session = LocalSession(db_path)
    report = {"ok": False, "checks": {}}
    try:
        session.start()
        for path in ("/log.html", "/index.html", "/api/config", "/api/backup.sqlite3"):
            connection = HTTPConnection("127.0.0.1", session.server.server_port, timeout=5)
            try:
                connection.request("GET", path)
                response = connection.getresponse()
                body = response.read()
                report["checks"][path] = {"status": response.status, "bytes": len(body)}
                if response.status != 200:
                    raise RuntimeError(f"The local app could not serve {path}.")
                if path.endswith(".html") and b"Bakery Lab" not in body:
                    raise RuntimeError(f"The bundled page {path} did not contain Bakery Lab.")
                if path == "/api/config":
                    config = json.loads(body)
                    if config.get("storage") != "local":
                        raise RuntimeError("The app did not report local storage.")
                    report["config"] = config
                if path == "/api/backup.sqlite3" and not body.startswith(b"SQLite format 3\0"):
                    raise RuntimeError("The downloaded backup was not a SQLite database.")
            finally:
                connection.close()
        report["ok"] = True
    except Exception as exc:
        report["error"] = str(exc)
    finally:
        session.stop()
    return report


def run_console(db_path: Path, *, wait_for_exit=None, opener=None, session_factory=None):
    """Keep the packaged browser app running until Ctrl+C or window closure."""
    session = (session_factory or LocalSession)(db_path)
    wait_for_exit = wait_for_exit or threading.Event().wait
    opener = opener or webbrowser.open
    try:
        url = session.start()
        print("Bakery Lab is ready.\n", flush=True)
        print("Your browser address:", url, flush=True)
        print("Your data folder:", Path(db_path).resolve().parent, flush=True)
        print("\nKeep this window open while you use Bakery Lab.", flush=True)
        print("Close this window or press Ctrl+C to exit.\n", flush=True)
        try:
            opened = opener(url, new=2)
        except Exception:
            opened = False
        if not opened:
            print("Copy the browser address above into your browser to open the app.\n", flush=True)
        try:
            wait_for_exit()
        except KeyboardInterrupt:
            pass
        print("Bakery Lab is closing. Your saved records stay on this computer.", flush=True)
        return 0
    except Exception as exc:
        print("Bakery Lab could not start. Your saved records have not been removed.", flush=True)
        print(str(exc), flush=True)
        if sys.stdin is not None and sys.stdin.isatty():
            try:
                input("Press Enter to close this window.")
            except (EOFError, KeyboardInterrupt):
                pass
        return 1
    finally:
        session.stop()


def run_window(db_path: Path):
    import tkinter as tk
    from tkinter import messagebox, ttk

    window = tk.Tk()
    window.title("Bakery Lab")
    window.geometry("480x305")
    window.minsize(440, 285)
    window.configure(background="#f5f6ee")
    session = LocalSession(db_path)
    frame = ttk.Frame(window, padding=25)
    frame.pack(fill="both", expand=True)
    ttk.Label(frame, text="Bakery Lab", font=("Segoe UI", 21, "bold")).pack(anchor="w")
    ttk.Label(frame, text="Daily records. A clearer picture of waste.", wraplength=390).pack(anchor="w", pady=(6, 16))
    status = tk.StringVar(value="Starting your local bakery log…")
    ttk.Label(frame, textvariable=status, wraplength=390).pack(anchor="w")
    address = tk.StringVar()
    ttk.Entry(frame, textvariable=address, state="readonly").pack(fill="x", pady=(10, 14))

    def open_app():
        try:
            url = session.start()
            address.set(url)
            opened = webbrowser.open(url, new=2)
            status.set("Your app is ready. Keep this window open while you use it." if opened else
                       "Your app is ready. Copy the address below into your browser.")
        except Exception as exc:
            status.set("Bakery Lab could not start. Your saved records have not been removed.")
            messagebox.showerror("Bakery Lab could not start", str(exc), parent=window)

    def close_app():
        session.stop()
        window.destroy()

    def show_data_folder():
        try:
            open_data_folder(session.db_path)
        except (OSError, subprocess.SubprocessError):
            messagebox.showerror(
                "The data folder could not be opened",
                "Your files have not been removed. You can find the data folder at:\n\n"
                + str(session.db_path.resolve().parent), parent=window,
            )

    buttons = ttk.Frame(frame)
    buttons.pack(fill="x")
    ttk.Button(buttons, text="Open Bakery Lab", command=open_app).pack(side="left")
    ttk.Button(buttons, text="Open data folder", command=show_data_folder).pack(side="left", padx=(10, 0))
    ttk.Button(buttons, text="Exit", command=close_app).pack(side="right")
    ttk.Label(frame, text="Your records stay on this computer.", wraplength=390).pack(anchor="w", pady=(14, 0))
    window.protocol("WM_DELETE_WINDOW", close_app)
    window.after(50, open_app)
    try:
        window.mainloop()
    finally:
        session.stop()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, help="Optional SQLite file location")
    parser.add_argument("--check", action="store_true", help="Check an isolated build without opening a window")
    parser.add_argument("--check-output", type=Path, help="Write the headless check result as JSON")
    parser.add_argument("--console", action="store_true", help="Use the browser app with a small console window")
    args = parser.parse_args(argv)
    if args.check:
        if args.db is None:
            parser.error("--check requires --db pointing to an isolated test database")
        report = check_application(args.db)
        content = json.dumps(report, indent=2) + "\n"
        if args.check_output is not None:
            args.check_output.parent.mkdir(parents=True, exist_ok=True)
            args.check_output.write_text(content, encoding="utf-8")
        elif sys.stdout is not None:
            print(content)
        return 0 if report["ok"] else 1
    if args.check_output is not None:
        parser.error("--check-output is used with --check")
    db_path = args.db if args.db is not None else default_database_path()
    if args.console or getattr(sys, "frozen", False):
        return run_console(db_path)
    run_window(db_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
