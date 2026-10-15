"""v3 (14 Oct 2026): a backup of tracker.db every day, plus a download of a fresh copy.

PythonAnywhere's free plan has no scheduled tasks, so the first request of each day makes the backup:
<data folder>/backups/tracker-YYYY-MM-DD.db, made with sqlite3's backup API so the copy is whole even while the
site is in use. Only the newest KEEP files are kept. A backup that fails never breaks the page.
GET /backup/download sends a fresh copy as wheres-my-money-backup-YYYY-MM-DD.db.
15 Oct 2026 (Darren): also a copy just before every statement PDF is read (statement-YYYYMMDD-HHMMSS.db, keep 5), and
Settings → Restore a backup (/backup/restore). A restore first saves how things are now (restore-....db, keep 5),
so a restore can be undone too. Nothing is written outside the data folder.
"""
import io
import logging
import sqlite3
import tempfile
import re
from datetime import date, datetime, timezone
from pathlib import Path

KEEP = 7
KEEP_BEFORE = 5
KINDS = {"statement": "Before a statement", "restore": "Before a restore"}
NAME = re.compile(r"^(?:tracker-\d{4}-\d{2}-\d{2}|(?:statement|restore)-\d{8}-\d{6})\.db$")
log = logging.getLogger(__name__)


def today() -> date:
    """The day used for file names (tests patch this)."""
    return date.today()


def now() -> datetime:
    """The time used for file names, in UTC (tests patch this)."""
    return datetime.now(timezone.utc)


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


def before(data_dir, kind) -> Path:
    """A copy of the database right now, kind 'statement' or 'restore'; only the newest KEEP_BEFORE of that kind kept."""
    folder = Path(data_dir) / "backups"
    folder.mkdir(exist_ok=True)
    target = folder / f"{kind}-{now():%Y%m%d-%H%M%S}.db"
    part = target.with_suffix(".part")
    copy_db(Path(data_dir) / "tracker.db", part)
    part.replace(target)
    for old in sorted(folder.glob(f"{kind}-????????-??????.db"))[:-KEEP_BEFORE]:
        old.unlink()
    return target


def _when(name: str) -> datetime:
    if name.startswith("tracker-"):
        return datetime.strptime(name[8:18], "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return datetime.strptime(name.split("-", 1)[1][:15], "%Y%m%d-%H%M%S").replace(tzinfo=timezone.utc)


def list_backups(data_dir) -> list:
    """Every backup, newest first: {name, label}. Daily ones show the day, the others the day and UK time."""
    from fintrack.v3.auth import clock
    folder = Path(data_dir) / "backups"
    found = [p.name for p in folder.glob("*.db") if NAME.match(p.name)] if folder.exists() else []
    out = []
    for name in found:
        t = _when(name)
        if name.startswith("tracker-"):
            label = f"Daily · {t.day} {t:%b %Y}"
        else:
            label = f"{KINDS[name.split('-', 1)[0]]} · {t.day} {t:%b %Y}, {clock(t)}"
        out.append((t, {"name": name, "label": label}))
    return [b for t, b in sorted(out, key=lambda x: x[0], reverse=True)]


def restore(data_dir, name) -> None:
    """Put backup `name` back as the data (a copy of now is saved first). ValueError if it is not a listed backup."""
    if name not in [b["name"] for b in list_backups(data_dir)]:
        raise ValueError("not a backup")
    before(data_dir, "restore")
    db = Path(data_dir) / "tracker.db"
    con = sqlite3.connect(str(db))
    try:                                           # sign-in data and ideas notes stay as they are now: you stay signed in, same passcode
        auth = con.execute("SELECT key, value FROM kv WHERE key LIKE 'auth\\_%' ESCAPE '\\' OR key = 'ideas'").fetchall()
    finally:
        con.close()
    copy_db(Path(data_dir) / "backups" / name, db)
    con = sqlite3.connect(str(db))
    try:
        con.execute("CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT)")
        con.execute("DELETE FROM kv WHERE key LIKE 'auth\\_%' ESCAPE '\\' OR key = 'ideas'")
        con.executemany("INSERT INTO kv (key, value) VALUES (?, ?)", auth)
        con.commit()
    finally:
        con.close()


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
    from flask import abort, redirect, render_template, request, send_file
    from fintrack.appversion import VERSION

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

    def backup_before_statement():
        # Runs after the sign-in check (appended), so only a signed-in upload makes a copy
        if request.method == "POST" and request.path == "/upload":
            try:
                before(data_dir, "statement")
            except Exception:                      # a failed copy never stops the statement being read
                log.exception("backup before a statement failed")
        return None

    app.before_request_funcs.setdefault(None, []).append(backup_before_statement)

    @app.get("/backup/restore")
    def restore_page():
        return render_template("restore.html", backups=list_backups(data_dir), done=request.args.get("done", ""),
                               app_version=VERSION)

    @app.post("/backup/restore")
    def restore_post():
        name = request.form.get("name", "")
        try:
            restore(data_dir, name)
        except ValueError:
            abort(400)
        return redirect("/backup/restore?done=" + name, code=303)

    @app.get("/backup/download")
    def backup_download():
        data = fresh_copy_bytes(data_dir / "tracker.db", data_dir)
        return send_file(io.BytesIO(data), mimetype="application/vnd.sqlite3", as_attachment=True,
                         download_name=f"wheres-my-money-backup-{today().isoformat()}.db")
