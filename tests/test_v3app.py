"""v3 (14 Oct 2026): the website entry point. Fake data only."""
import json
import shutil
from datetime import date

import pytest

import run
from tests.conftest import DATA

pytest.importorskip("flask")
import v3app  # noqa: E402

ACME = "ACME MOTORS PLC"


@pytest.fixture
def data_dir(tmp_path):
    inbox = tmp_path / "statements"
    inbox.mkdir()
    for n in ("statement_2024_08.pdf", "statement_2024_09.pdf", "statement_2024_10.pdf"):
        shutil.copy(DATA / n, inbox / n)
    run.main(in_dir=inbox, out_dir=tmp_path / "output", ask=lambda p: "2500", wage_payer=ACME, ask_items=lambda p: "")
    d = tmp_path / "v3data"
    d.mkdir()
    shutil.copy(tmp_path / "tracker.db", d / "tracker.db")
    return d


def test_settings_file_is_made_with_a_secret_key(tmp_path):
    s = v3app.load_settings(tmp_path / "data")
    saved = json.loads((tmp_path / "data" / "v3_settings.json").read_text())
    assert len(s["secret_key"]) == 64 and saved["secret_key"] == s["secret_key"]
    assert v3app.load_settings(tmp_path / "data")["secret_key"] == s["secret_key"]       # kept, not remade
    assert s["email"] == "" and s["update"] == "zip" and s["branch"] == "v3"


def test_v3_app_has_no_phone_copy_and_keeps_no_pdfs(data_dir, monkeypatch):
    import web
    sent = []
    monkeypatch.setattr(web.phone, "sync_once", lambda *a, **k: sent.append("sync") or 0)
    app = v3app.make_app(data_dir, wage_payer=ACME, today=date(2024, 10, 25))
    assert app.config["CLOUD"] is True and app.secret_key
    assert sent == []
    pdf = (DATA / "statement_2024_10.pdf").read_bytes()
    from fintrack.inbox import import_pdf
    from fintrack.store import open_db
    r = import_pdf(open_db(data_dir / "tracker.db"), data_dir / "statements", "s.pdf", pdf, keep=False)
    assert "error" not in r and not (data_dir / "statements").exists()


def test_git_update_reports_changes():
    class R:
        def __init__(self, out, code=0):
            self.stdout, self.stderr, self.returncode = out, "", code
    calls = []

    def fake(cmd, **k):
        calls.append(cmd)
        return R(" web.py | 2 +-\n 1 file changed") if "pull" in cmd else R("abc1234\n")
    r = v3app.git_update("/code", run=fake)
    assert r == {"changed": ["web.py | 2 +-"], "version": "abc1234"}
    r = v3app.git_update("/code", run=lambda cmd, **k: R("Already up to date.") if "pull" in cmd else R("abc1234"))
    assert r["changed"] == []
    with pytest.raises(RuntimeError):
        v3app.git_update("/code", run=lambda cmd, **k: R("", 1))
