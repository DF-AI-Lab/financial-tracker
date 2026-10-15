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
    auth.sign_in_for_tests(v3_app, c)
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


# 15 Oct 2026 (Darren): a backup before every statement PDF (keep 5), and Settings → Restore a backup.
from datetime import datetime, timezone  # noqa: E402

T = datetime(2026, 10, 15, 13, 7, 12, tzinfo=timezone.utc)


@pytest.fixture
def clock(monkeypatch):
    box = {"t": T}
    monkeypatch.setattr(backup, "now", lambda: box["t"])
    return box


def names(data_dir, kind):
    return sorted(p.name for p in (data_dir / "backups").glob(f"{kind}-*.db"))


def test_a_backup_is_made_before_a_statement_is_read(client, v3_data, day, clock):
    original = dump(v3_data / "tracker.db")
    client.post("/upload", data={"files": []})
    assert names(v3_data, "statement") == ["statement-20261015-130712.db"]
    assert dump(v3_data / "backups" / "statement-20261015-130712.db") == original


def test_only_the_newest_five_statement_backups_are_kept(v3_data, clock):
    for n in range(7):
        clock["t"] = T + timedelta(minutes=n)
        backup.before(v3_data, "statement")
    assert names(v3_data, "statement") == [f"statement-20261015-13{7 + n:02d}12.db" for n in range(2, 7)]


def test_backups_are_listed_newest_first_with_a_plain_label(v3_data, day, clock):
    backup.daily_backup(v3_data, DAY)
    backup.before(v3_data, "statement")
    found = backup.list_backups(v3_data)
    assert [b["name"] for b in found] == ["statement-20261015-130712.db", "tracker-2026-10-14.db"]
    assert found[0]["label"].startswith("Before a statement") and "15 Oct" in found[0]["label"]
    assert found[1]["label"].startswith("Daily") and "14 Oct" in found[1]["label"]


def test_restore_puts_the_data_back_and_keeps_a_copy_of_now(client, v3_data, day, clock):
    client.get("/")
    backup.before(v3_data, "statement")
    before = dump(v3_data / "tracker.db")
    client.post("/add", data={"amount": "9.99", "name": "Oops"})
    after = dump(v3_data / "tracker.db")
    assert after != before
    page = client.get("/backup/restore").get_data(as_text=True)
    assert "statement-20261015-130712.db" in page and "Before a statement" in page
    clock["t"] = T + timedelta(minutes=5)
    r = client.post("/backup/restore", data={"name": "statement-20261015-130712.db"})
    assert r.status_code in (302, 303)
    assert dump(v3_data / "tracker.db") == before
    assert names(v3_data, "restore") == ["restore-20261015-131212.db"]           # how it was, so a restore can be undone
    assert dump(v3_data / "backups" / "restore-20261015-131212.db") == after


def test_restore_only_takes_a_listed_backup(client, v3_data, day, clock):
    client.get("/")
    was = dump(v3_data / "tracker.db")
    for bad in ("../tracker.db", "tracker.db", "nope.db", ""):
        assert client.post("/backup/restore", data={"name": bad}).status_code == 400
    assert dump(v3_data / "tracker.db") == was


def test_settings_has_restore_a_backup(client):
    assert 'href="/backup/restore"' in client.get("/").get_data(as_text=True)


def test_restore_keeps_you_signed_in_with_the_same_passcode(client, v3_data, day, clock):
    """Sign-in data (devices, passcode, backup codes) is not part of a restore: you stay signed in."""
    backup.before(v3_data, "statement")
    con = sqlite3.connect(str(v3_data / "backups" / "statement-20261015-130712.db"))
    con.execute("DELETE FROM kv WHERE key LIKE 'auth_%'"); con.commit(); con.close()       # an old backup: no sign-in data
    now_auth = sorted(sqlite3.connect(str(v3_data / "tracker.db")).execute("SELECT * FROM kv WHERE key LIKE 'auth_%'"))
    assert now_auth
    client.post("/backup/restore", data={"name": "statement-20261015-130712.db"})
    assert sorted(sqlite3.connect(str(v3_data / "tracker.db")).execute("SELECT * FROM kv WHERE key LIKE 'auth_%'")) == now_auth
    assert client.get("/").status_code == 200
