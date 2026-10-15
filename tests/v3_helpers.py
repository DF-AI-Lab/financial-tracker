"""Shared fixtures for the v3 website tests (14 Oct 2026). Fake data only.

v3_data: a data folder with tracker.db built from the fake statements (ACME MOTORS PLC pays the wage).
v3_app / v3_client: the v3 website for it; when sign-in exists (fintrack/v3/auth.py), the client is already signed in
(auth.make_device(app) gives a device token, set as the auth.COOKIE cookie).
Use in a test file:  from tests.v3_helpers import v3_data, v3_app, v3_client, ACME  # noqa: F401
"""
import shutil
from datetime import date

import pytest

import run
from tests.conftest import DATA

ACME = "ACME MOTORS PLC"
TODAY = date(2024, 10, 25)


@pytest.fixture
def v3_data(tmp_path):
    inbox = tmp_path / "statements"
    inbox.mkdir()
    for n in ("statement_2024_08.pdf", "statement_2024_09.pdf", "statement_2024_10.pdf"):
        shutil.copy(DATA / n, inbox / n)
    run.main(in_dir=inbox, out_dir=tmp_path / "output", ask=lambda p: "2500", wage_payer=ACME, ask_items=lambda p: "")
    d = tmp_path / "v3data"
    d.mkdir()
    shutil.copy(tmp_path / "tracker.db", d / "tracker.db")
    return d


@pytest.fixture
def v3_app(v3_data):
    pytest.importorskip("flask")
    import v3app
    app = v3app.make_app(v3_data, wage_payer=ACME, today=TODAY, updater=lambda: {"changed": [], "version": "t"},
                         restart=lambda: None)
    app.testing = True
    return app


@pytest.fixture
def v3_client(v3_app):
    client = v3_app.test_client()
    try:
        from fintrack.v3 import auth
    except ImportError:                       # sign-in not built yet
        return client
    auth.sign_in_for_tests(v3_app, client)                 # device, passcode set, unlocked
    return client
