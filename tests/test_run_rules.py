from datetime import date

import run
from fintrack.models import Statement
from fintrack.store import get_rules, import_statement, open_db
from tests.rentdata import all_txns

ACME = "ACME MOTORS PLC"


def seed(tmp_path):
    """A database that already holds a made-up statement with rent paid by transfer (no PDFs needed)."""
    txns = all_txns()
    from tests.rentdata import Txn
    txns.append(Txn(date(2024, 7, 28), "CR", ACME, "PAYROLL", 2400.0))        # a 7th wage so six cycles are complete
    txns.sort(key=lambda t: t.date)
    st = Statement("made-up.pdf", date(2024, 1, 22), date(2024, 8, 5), 100.0, 100.0, txns)
    conn = open_db(tmp_path / "tracker.db")
    assert import_statement(conn, st, [])
    conn.close()
    inbox = tmp_path / "statements"
    inbox.mkdir()
    return inbox, tmp_path / "output"


def accept(prompt):
    return ""


def pay(prompt):
    return "3000"


def never(prompt):
    raise AssertionError("must not ask: " + prompt)


def go(inbox, out, ask_items, capsys):
    run.main(in_dir=inbox, out_dir=out, ask=pay, wage_payer=ACME, ask_items=ask_items)
    return capsys.readouterr().out


def test_rent_rule_is_asked_once_and_used_in_the_averages(tmp_path, capsys):
    inbox, out = seed(tmp_path)
    text = go(inbox, out, accept, capsys)
    assert "PAYDAY TRANSFERS" in text and "Count these as Common" in text
    assert text.index("NEW ITEMS") < text.index("PAYDAY TRANSFERS") < text.index("STATEMENT BY STATEMENT")
    rules = get_rules(open_db(tmp_path / "tracker.db"))
    assert len(rules) == 1 and rules[0]["kind"] == "common" and rules[0]["label"] == "Rent"
    common = text.split("COMMON (")[1].split("ONE-OFFS")[0]
    assert "Rent" in common and "373.33" in common                # 2240 / 6 complete cycles
    assert all(ord(c) < 128 for c in text)
    again = go(inbox, out, never, capsys)                          # second run: nothing new to ask
    assert "PAYDAY TRANSFERS" not in again
    assert "373.33" in again.split("COMMON (")[1].split("ONE-OFFS")[0]


def test_saying_no_keeps_it_random_and_is_not_asked_again(tmp_path, capsys):
    inbox, out = seed(tmp_path)
    answers = iter(["", "", "n"])        # items list (Enter), same bill? (Enter = no), rent question (no)
    text = go(inbox, out, lambda p: next(answers), capsys)
    assert get_rules(open_db(tmp_path / "tracker.db"))[0]["kind"] == "declined"
    assert "373.33" not in text
    again = go(inbox, out, never, capsys)
    assert "PAYDAY TRANSFERS" not in again
