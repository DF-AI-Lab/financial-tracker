"""v3 (15 Oct 2026): devices stay up to date (GET /stamp). Fake data only."""
from datetime import timedelta

import pytest

from tests.v3_helpers import v3_data, v3_app, v3_client, ACME  # noqa: F401

pytest.importorskip("flask")
from fintrack.v3 import auth  # noqa: E402


def test_stamp_changes_when_the_data_changes(v3_client, v3_data):
    import os
    a = v3_client.get("/stamp").get_json()["stamp"]
    assert a and v3_client.get("/stamp").get_json()["stamp"] == a
    db = v3_data / "tracker.db"
    st = db.stat()
    v3_client.post("/add", data={"amount": "3.50", "name": "Costa"})
    os.utime(db, ns=(st.st_atime_ns, st.st_mtime_ns + 10**9))        # file systems with coarse times
    assert v3_client.get("/stamp").get_json()["stamp"] != a


def test_stamp_needs_sign_in_and_does_not_keep_the_site_unlocked(v3_app, monkeypatch):
    assert v3_app.test_client().get("/stamp").status_code == 401         # a check gets 401, never a page
    from datetime import datetime
    t = {"now": datetime(2026, 10, 15, 9, 0)}
    monkeypatch.setattr(auth, "now", lambda: t["now"])
    c = v3_app.test_client()
    auth.sign_in_for_tests(v3_app, c)
    for _ in range(4):                                                # the page checking every 5 minutes...
        t["now"] += timedelta(minutes=5)
        c.get("/stamp")
    assert c.get("/stamp").status_code == 401                         # the page then reloads to the passcode
    assert c.get("/").headers["Location"].endswith("/unlock")         # ...still asks for the passcode after 15


def test_page_has_the_checker(v3_client):
    html = v3_client.get("/").get_data(as_text=True)
    assert "fetch('/stamp'" in html and "visibilitychange" in html
