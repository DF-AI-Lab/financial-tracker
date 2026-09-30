import shutil

import run
from fintrack.settings import saved_folder
from fintrack.store import get_items, open_db, statement_rows
from tests.conftest import DATA

FAKE = ("statement_2024_08.pdf", "statement_2024_09.pdf", "statement_2024_10.pdf")
ACME = "ACME MOTORS PLC"


def setup(tmp_path, with_copy=True):
    inbox = tmp_path / "statements"
    inbox.mkdir()
    for n in FAKE:
        shutil.copy(DATA / n, inbox / n)
    if with_copy:
        shutil.copy(DATA / "statement_2024_09.pdf", inbox / "copy_of_sep.PDF")
    return inbox, tmp_path / "output"


def pay(prompt):
    return "2500"


def accept_all(prompt):
    return ""


def never(prompt):
    raise AssertionError("must not ask: " + prompt)


def go(tmp_path, capsys, inbox, out, ask_items=accept_all, ask=pay):
    run.main(in_dir=inbox, out_dir=out, ask=ask, wage_payer=ACME, ask_items=ask_items)
    return capsys.readouterr().out


def test_first_run_stores_asks_and_remembers(tmp_path, capsys):
    inbox, out = setup(tmp_path)
    text = go(tmp_path, capsys, inbox, out)
    db = tmp_path / "tracker.db"                      # next to the statements folder
    assert db.exists()
    assert "Stored 3 new statements" in text and "Skipped duplicate" in text
    assert "NEW ITEMS" in text and "IF YOUR PAY IS 2,500.00" in text
    conn = open_db(db)
    assert len(statement_rows(conn)) == 3 and len(get_items(conn)) > 10
    assert all(ord(c) < 128 for c in text)


def test_second_run_asks_nothing_and_stores_nothing(tmp_path, capsys):
    inbox, out = setup(tmp_path)
    go(tmp_path, capsys, inbox, out)
    text = go(tmp_path, capsys, inbox, out, ask_items=never)
    assert "Stored 0 new statements" in text and "NEW ITEMS" not in text
    assert "PAYDAY TO PAYDAY" in text


def test_reports_still_work_after_the_pdfs_are_deleted(tmp_path, capsys):
    inbox, out = setup(tmp_path)
    go(tmp_path, capsys, inbox, out)
    for f in inbox.iterdir():
        f.unlink()
    text = go(tmp_path, capsys, inbox, out, ask_items=never)
    assert "PAYDAY TO PAYDAY" in text and "IF YOUR PAY IS 2,500.00" in text
    assert "No PDFs found" not in text


def test_no_pdfs_and_no_database_says_so(tmp_path, capsys):
    inbox, out = setup(tmp_path, with_copy=False)
    for f in inbox.iterdir():
        f.unlink()
    text = go(tmp_path, capsys, inbox, out, ask_items=never)
    assert "No PDFs found" in text


def test_typed_answer_changes_the_reports(tmp_path, capsys):
    inbox, out = setup(tmp_path)
    go(tmp_path, capsys, inbox, out)
    db = tmp_path / "tracker.db"
    first_key = sorted(get_items(open_db(db)))[0]                # listed as item 1 by `fix`
    assert run.run_command(["fix"], ask=lambda p: "oneoff 1", out=lambda s: None, db_path=db, in_dir=inbox) is True
    assert get_items(open_db(db))[first_key]["kind"] == "oneoff"
    text = go(tmp_path, capsys, inbox, out, ask_items=never)
    after = text.split("ONE-OFFS")[1].split("Latest pay?")[0]
    assert first_key.split("|")[1] in after                      # that payer is now listed as a one-off


def test_fix_without_a_database(tmp_path):
    lines = []
    db = tmp_path / "none.db"
    assert run.run_command(["fix"], ask=never, out=lines.append, db_path=db, in_dir=tmp_path) is True
    assert any("No database yet" in l for l in lines) and not db.exists()


def test_folder_command(tmp_path):
    f, lines = tmp_path / "saved.txt", []
    good = tmp_path / "my statements"
    good.mkdir()
    assert run.run_command(["folder", str(good)], out=lines.append, saved_file=f) is True
    assert saved_folder(saved_file=f) == good and any("Saved" in l for l in lines)
    lines.clear()
    assert run.run_command(["folder", str(tmp_path / "nope")], out=lines.append, saved_file=f) is True
    assert any("does not exist" in l for l in lines) and saved_folder(saved_file=f) == good
    lines.clear()
    assert run.run_command(["folder"], out=lines.append, saved_file=f) is True      # no path given
    assert lines and saved_folder(saved_file=f) == good


def test_other_arguments_are_not_commands():
    assert run.run_command([]) is False
    assert run.run_command(["test"]) is False
    assert run.run_command(["banana"]) is False
