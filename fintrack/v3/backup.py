"""v3 (14 Oct 2026): a backup of tracker.db every day, plus a download of a fresh copy.

PythonAnywhere's free plan has no scheduled tasks, so the first request of each day makes the backup:
<data folder>/backups/tracker-YYYY-MM-DD.db, made with sqlite3's backup API so the copy is whole even while the
site is in use. Only the newest KEEP files are kept. A backup that fails never breaks the page.
GET /backup/download sends a fresh copy as wheres-my-money-backup-YYYY-MM-DD.db.
Nothing is written outside the data folder.
"""
import io
import logging
import sqlite3
import tempfile
from datetime import date
from pathlib import Path

KEEP = 7
log = logging.getLogger(__name__)


def today() -> date:
    """The day used for file names (tests patch this)."""
    return date.today()


def copy_db(src_path, dst_path) -> None:
    """A consistent copy of the database at src_path into dst_path (sqlite3 online backup)."""
    src = sqlite3.connect(str(src_path))
    try:
        dst = sqlite3.connect(str(dst_path))
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()


def prune(folder, keep=KEEP) -> None:
    """Delete all but the newest `keep` backups (the dates in the names sort in order)."""
    old = sorted(Path(folder).glob("tracker-????-??-??.db"))[:-keep]
    for p in old:
        p.unlink()


def daily_backup(data_dir, day=None) -> Path:
    """Make today's backup if it is not there yet, then prune. Returns its path."""
    data_dir = Path(data_dir)
    day = day or today()
    folder = data_dir / "backups"
    folder.mkdir(exist_ok=True)
    target = folder / f"tracker-{day.isoformat()}.db"
    if not target.exists():
        part = target.with_suffix(".part")         # a half-made copy never counts as today's
        if part.exists():
            part.unlink()
        copy_db(data_dir / "tracker.db", part)
        part.replace(target)
    prune(folder)
    return target


def fresh_copy_bytes(db_path, data_dir) -> bytes:
    """A consistent copy of the database as bytes (in memory; a temp file in the data folder on old Pythons)."""
    src = sqlite3.connect(str(db_path))
    try:
        mem = sqlite3.connect(":memory:")
        try:
            src.backup(mem)
            if hasattr(mem, "serialize"):          # Python 3.11+
                return mem.serialize()
        finally:
            mem.close()
    finally:
        src.close()
    with tempfile.TemporaryDirectory(dir=str(data_dir)) as tmp:
        path = Path(tmp) / "copy.db"
        copy_db(db_path, path)
        return path.read_bytes()


def register(app) -> None:
    from flask import send_file

    data_dir = Path(app.config["V3_DATA_DIR"])
    state = {"day": None, "file": None}            # the last day tried, and its file (None when it failed)

    def backup_once_a_day():
        day = today()
        if state["day"] == day and (state["file"] is None or state["file"].exists()):
            return None
        state["day"], state["file"] = day, None
        try:
            state["file"] = daily_backup(data_dir, day)
        except Exception:                          # never break the page; try again tomorrow
            log.exception("daily backup failed")
        return None

    # First in line, so a sign-in check that turns a request away does not stop the daily backup.
    app.before_request_funcs.setdefault(None, []).insert(0, backup_once_a_day)

    @app.get("/backup/download")
    def backup_download():
        data = fresh_copy_bytes(data_dir / "tracker.db", data_dir)
        return send_file(io.BytesIO(data), mimetype="application/vnd.sqlite3", as_attachment=True,
                         download_name=f"wheres-my-money-backup-{today().isoformat()}.db")
