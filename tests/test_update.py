"""Update without downloading ZIPs (user, 3 Oct 2026): fetch main.zip from GitHub and copy it over the code folder.
Statements, the database and anything else of the user's are never touched. Fake zips only (no internet)."""
import io
import zipfile

import pytest

from fintrack.update import update_code


def fake_zip(files, comment=b"abc1234def"):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("financial-tracker-main/", "")
        for name, text in files.items():
            z.writestr("financial-tracker-main/" + name, text)
        z.comment = comment                                  # GitHub puts the commit id here
    return buf.getvalue()


def test_new_and_changed_files_are_copied_and_the_rest_left_alone(tmp_path):
    code = tmp_path / "code"
    (code / "fintrack").mkdir(parents=True)
    (code / "web.py").write_text("old")
    (code / "start.bat").write_text("same")
    (code / "statements").mkdir()
    (code / "statements" / "mine.pdf").write_text("REAL")
    (code / "tracker.db").write_text("REAL DB")
    (code / "my_notes.txt").write_text("keep me")
    z = fake_zip({"web.py": "new", "start.bat": "same", "fintrack/new.py": "x = 1",
                  "statements/README.txt": "readme", "statements/mine.pdf": "FAKE", "tracker.db": "FAKE",
                  "tests/data/a.pdf": "test pdf"})
    r = update_code(code, fetch=lambda: z)
    assert r["version"] == "abc1234"
    assert sorted(r["changed"]) == ["fintrack/new.py", "tests/data/a.pdf", "web.py"]
    assert (code / "web.py").read_text() == "new" and (code / "fintrack" / "new.py").read_text() == "x = 1"
    assert (code / "statements" / "mine.pdf").read_text() == "REAL"      # never touched
    assert not (code / "statements" / "README.txt").exists()
    assert (code / "tracker.db").read_text() == "REAL DB"
    assert (code / "my_notes.txt").read_text() == "keep me"
    assert (code / "version.txt").read_text().strip() == "abc1234"
    assert update_code(code, fetch=lambda: z)["changed"] == []          # second time: already up to date


def test_a_bad_download_changes_nothing(tmp_path):
    (tmp_path / "web.py").write_text("old")
    with pytest.raises(ValueError):
        update_code(tmp_path, fetch=lambda: b"not a zip")
    with pytest.raises(ValueError):                                      # a zip that is not this project
        update_code(tmp_path, fetch=lambda: fake_zip({"other.txt": "x"}))
    assert (tmp_path / "web.py").read_text() == "old"
