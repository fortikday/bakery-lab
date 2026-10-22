"""Consistent, private SQLite recovery copies for the local daily log.

The SQLite backup API includes committed WAL contents and archived records.
Automatic copies stay beside their own database; downloaded copies can be
stored elsewhere by the user. Neither operation replaces the live database.
"""

from contextlib import closing, contextmanager
from datetime import date
from pathlib import Path
import re
import sqlite3
import tempfile
import threading
import uuid


AUTOMATIC_WARNING = (
    "The automatic recovery copy could not be updated. Download a backup and "
    "check available disk space or folder permissions."
)


class BackupManager:
    """Serialize automatic snapshots so a later save cannot get an older copy."""

    def __init__(self, db_path, local_now):
        self.path = Path(db_path).resolve()
        self.directory = self.path.parent / (self.path.name + "-backups")
        self.local_now = local_now
        self._lock = threading.RLock()
        self._last_error = None
        self._revision = 0
        self._instance_id = str(uuid.uuid4())

    def _source(self):
        # Read-only mode fails if the source disappears instead of silently
        # creating an empty database and describing it as a valid backup.
        return sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True, timeout=10)

    def _has_records(self):
        with closing(self._source()) as source:
            return bool(source.execute("SELECT EXISTS(SELECT 1 FROM entries)").fetchone()[0])

    def status(self):
        """Return useful status without exposing a private filesystem path."""
        with self._lock:
            dates = []
            error = self._last_error
            try:
                for candidate in self.directory.glob("*.sqlite3"):
                    if candidate.is_file() and re.fullmatch(r"\d{4}-\d{2}-\d{2}", candidate.stem):
                        try:
                            dates.append(date.fromisoformat(candidate.stem).isoformat())
                        except ValueError:
                            continue
                has_records = self._has_records()
            except (OSError, sqlite3.Error):
                has_records = None
                error = AUTOMATIC_WARNING
            return {
                "automatic": True,
                "latest_date": max(dates) if dates else None,
                "last_error": error,
                "has_records": has_records,
                "download_url": "/api/backup.sqlite3",
                "revision": self._revision,
                "instance_id": self._instance_id,
            }

    def _write_snapshot(self, destination):
        """Finish and close both connections before the file is read or moved."""
        with closing(self._source()) as source, closing(sqlite3.connect(destination, timeout=10)) as target:
            source.backup(target, pages=256, sleep=0.01)

    @contextmanager
    def _snapshot_mutex(self):
        """Coordinate app instances without locking writes to the daily log.

        SQLite owns the lock's lifetime, so a stopped or crashed process cannot
        leave a stale PID lock behind. Keep the sidecar private and hold its
        write lock across both taking the snapshot and publishing the copy.
        """
        lock_path = self.directory / ".snapshot-lock.sqlite3"
        with closing(sqlite3.connect(lock_path, timeout=10)) as mutex:
            mutex.execute("CREATE TABLE IF NOT EXISTS snapshot_lock (singleton INTEGER PRIMARY KEY)")
            mutex.commit()
            mutex.execute("BEGIN IMMEDIATE")
            try:
                yield
            finally:
                mutex.rollback()

    def failure_status(self):
        """Keep a post-save failure visible even if status collection failed."""
        with self._lock:
            self._last_error = AUTOMATIC_WARNING
            self._revision += 1
            return {"automatic": True, "latest_date": None, "last_error": AUTOMATIC_WARNING,
                    "has_records": None, "download_url": "/api/backup.sqlite3",
                    "revision": self._revision, "instance_id": self._instance_id}

    def refresh(self):
        """Update today's recovery copy; a backup failure never undoes a save.

        Keep previous calendar-day copies. There is no automatic deletion or
        retention limit in this version. Temporary files stay in the private
        recovery directory and a failed replacement preserves the older copy.
        """
        with self._lock:
            temporary = None
            try:
                if not self._has_records():
                    self._last_error = None
                else:
                    self.directory.mkdir(parents=True, exist_ok=True)
                    with self._snapshot_mutex():
                        # A queued instance may acquire the lock after midnight.
                        today = self.local_now().date().isoformat()
                        with tempfile.NamedTemporaryFile(prefix=".recovery-", suffix=".sqlite3",
                                                         dir=self.directory, delete=False) as file:
                            temporary = Path(file.name)
                        self._write_snapshot(temporary)
                        temporary.replace(self.directory / (today + ".sqlite3"))
                        temporary = None
                    self._last_error = None
            except Exception:
                # This happens only after a successful data operation (or at
                # startup). A friendly warning must not imply that save failed.
                self._last_error = AUTOMATIC_WARNING
            finally:
                if temporary is not None:
                    try:
                        temporary.unlink(missing_ok=True)
                    except OSError:
                        # A leftover incomplete file is private and its prefix
                        # means status() never presents it as a recovery copy.
                        pass
                # Version the completed attempt before constructing its return
                # value. A delayed success must not clear a newer failure in UI.
                self._revision += 1
            return self.status()

    def download(self):
        """Return a full closed snapshot, with no SQLite lock held during send."""
        with tempfile.TemporaryDirectory(prefix="bakery-backup-") as directory:
            destination = Path(directory) / "snapshot.sqlite3"
            self._write_snapshot(destination)
            return destination.read_bytes()
