"""v3 move-in helper (15 Oct 2026). Fake values only."""
import json

from tools import pa_setup


def test_setup_writes_the_settings(tmp_path):
    answers = iter(["me@example.com", ""])
    s = pa_setup.main(ask=lambda q: next(answers), secret=lambda q: "abcd efgh ijkl mnop", data=tmp_path)
    saved = json.loads((tmp_path / "v3_settings.json").read_text())
    assert saved["email"] == "me@example.com" and saved["smtp_user"] == "me@example.com"
    assert saved["smtp_password"] == "abcdefghijklmnop" and saved["update"] == "git" and saved["branch"] == "v3"
    assert saved["wsgi_file"].startswith("/var/www/") and saved["wsgi_file"].endswith("_pythonanywhere_com_wsgi.py")
    assert len(saved["secret_key"]) == 64 and s == saved
    again = iter(["", ""])                                      # Enter keeps everything, blank password kept
    pa_setup.main(ask=lambda q: next(again), secret=lambda q: "", data=tmp_path)
    assert json.loads((tmp_path / "v3_settings.json").read_text())["smtp_password"] == "abcdefghijklmnop"
