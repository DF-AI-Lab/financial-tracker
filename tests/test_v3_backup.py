"""v3 (14 Oct 2026): daily backups of tracker.db plus a download. Fake data only."""
import sqlite3
from datetime import date, timedelta

import pytest

from tests.v3_helpers import v3_data, v3_app, ACME  # noqa: F401

pytest.importorskip("flask")
from fintrack.v3 import backup  # noqa: E402

DAY = date(2026, 10, 14)


@pytest.fixture
def client(v3_app):
    """Like v3_helpers.v3_client, but also works before fintrack/v3/auth.py exists (that raises ImportError)."""
    c = v3_app.test_client()
    try:
        from fintrack.v3 import auth
    except ImportError:
        return c
    c.set_cookie(auth.COOKIE, auth.make_device(v3_app))
    return c


def dump(path) -> dict:
    """Every table's rows, so two databases can be compared."""
    con = sqlite3.connect(str(path))
    try:
        tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        return {t: sorted(map(repr, con.execute(f'SELECT * FROM "{t}"'))) for t in tables}
    finally:
        con.close()


@pytest.fixture
def day(monkeypatch):
    box = {"d": DAY}
    monkeypatch.setattr(backup, "today", lambda: box["d"])
    return box


def files(data_dir):
    return sorted(p.name for p in (data_dir / "backups").glob("tracker-*.db"))


def test_first_request_makes_todays_backup_only_once(client, v3_data, day):
    client.get("/")
    assert files(v3_data) == ["tracker-2026-10-14.db"]
    made = (v3_data / "backups" / "tracker-2026-10-14.db").stat().st_mtime_ns
    client.get("/")
    assert files(v3_data) == ["tracker-2026-10-14.db"]
    assert (v3_data / "backups" / "tracker-2026-10-14.db").stat().st_mtime_ns == made


def test_backup_has_the_same_tables_and_rows(client, v3_data, day):
    original = dump(v3_data / "tracker.db")       # as it was when the backup is made (the page itself saves things)
    client.get("/")
    copy = v3_data / "backups" / "tracker-2026-10-14.db"
    assert sqlite3.connect(str(copy)).execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert original and any(original.values())
    assert dump(copy) == original


def test_backup_made_again_if_the_file_is_deleted(client, v3_data, day):
    client.get("/")
    (v3_data / "backups" / "tracker-2026-10-14.db").unlink()
    client.get("/")
    assert files(v3_data) == ["tracker-2026-10-14.db"]


def test_only_the_newest_seven_are_kept(client, v3_data, day):
    for n in range(9):
        day["d"] = DAY + timedelta(days=n)
        client.get("/")
    want = [f"tracker-{(DAY + timedelta(days=n)).isoformat()}.db" for n in range(2, 9)]
    assert files(v3_data) == want


def test_download_is_a_fresh_copy(client, v3_data, day, tmp_path):
    r = client.get("/backup/download")
    assert r.status_code == 200
    cd = r.headers["Content-Disposition"]
    assert "attachment" in cd and "wheres-my-money-backup-2026-10-14.db" in cd
    got = tmp_path / "got.db"
    got.write_bytes(r.data)
    assert dump(got) == dump(v3_data / "tracker.db")


def test_broken_backups_folder_does_not_break_the_page(client, v3_data, day):
    (v3_data / "backups").write_text("not a folder")
    r = client.get("/")
    assert r.status_code == 200
    assert (v3_data / "backups").is_file()


def test_nothing_written_outside_the_data_folder(client, v3_data, day):
    before = sorted(p.name for p in v3_data.parent.iterdir())
    client.get("/")
    client.get("/backup/download")
    assert sorted(p.name for p in v3_data.parent.iterdir()) == before
