from datetime import date, timedelta

import pytest

from fintrack.models import Cycle, Txn
from fintrack.paydayrule import days_after_payday, find_candidates, matches_rule, payer_name, review_rules
from fintrack.store import add_rule, get_rules, open_db
from tests.rentdata import PAYER, RULE, all_txns, bp, cycles, payday, paydays


def test_payer_name():
    assert payer_name(Txn(date(2024, 1, 1), "BP", "Sam Parker", "Rent", -5)) == "SAM PARKER"
    assert payer_name(Txn(date(2024, 1, 1), "BP", "ACME LTD", "", -5)) == "ACME"


def test_days_after_payday():
    p = paydays()
    assert days_after_payday(date(2024, 1, 28), p) == 0
    assert days_after_payday(date(2024, 2, 2), p) == 5
    assert days_after_payday(date(2024, 2, 28), p) == 0
    assert days_after_payday(date(2024, 1, 10), p) is None       # before the first payday
    assert days_after_payday(date(2024, 1, 10), []) is None


def test_matches_rule():
    p = payday(1)
    t = lambda amt, d=1, typ="BP", desc=PAYER: Txn(p + timedelta(days=d), typ, desc, "x", -float(amt))
    assert matches_rule(t(550), RULE, p)
    assert matches_rule(t(590), RULE, p)                          # 7% over
    assert matches_rule(t(510), RULE, p)                          # 7% under
    assert matches_rule(t(550, d=0), RULE, p) and matches_rule(t(550, d=2), RULE, p)
    assert not matches_rule(t(550, d=3), RULE, p)                 # too late
    assert not matches_rule(t(620), RULE, p)                      # 13% over
    assert not matches_rule(t(550, typ="VIS"), RULE, p)           # not a bill payment
    assert not matches_rule(t(550, desc="SOMEONE ELSE"), RULE, p)
    assert not matches_rule(Txn(p, "BP", PAYER, "", 550.0), RULE, p)            # money in
    assert not matches_rule(t(550), dict(RULE, kind="declined"), p)
    assert not matches_rule(Txn(p - timedelta(days=1), "BP", PAYER, "", -550.0), RULE, p)   # before payday


def test_find_candidates_finds_the_rent():
    found = find_candidates(all_txns(), paydays(), [])
    assert len(found) == 1
    c = found[0]
    assert c["payer"] == PAYER and c["usual"] == pytest.approx(550.0)
    assert c["suggest_label"] == "Rent"
    assert [(e["date"], e["amount"], e["reference"], e["days"]) for e in c["examples"]] == [
        ("2024-01-29", 550.0, "RENT", 1), ("2024-02-29", 550.0, "FOOD", 1),
        ("2024-03-30", 550.0, "RENT", 2), ("2024-04-29", 590.0, "RENT", 1)]


def test_small_top_ups_and_late_payments_are_not_candidates():
    txns = [t for t in all_txns() if abs(t.amount) < 100 or (t.date - payday(1)).days < 0 or t.type == "CR"]
    assert find_candidates(txns, paydays(), []) == []


def test_needs_three_payments_unless_the_payer_already_has_a_rule():
    two = [t for t in all_txns() if t.type == "CR" or (t.detail != "Food and bil" and t.date < date(2024, 3, 1))]
    assert find_candidates(two, paydays(), []) == []                              # only 2 rent payments
    assert len(find_candidates(two, paydays(), [RULE])) == 0                     # already covered by the rule


def test_existing_rules_hide_the_candidate():
    assert find_candidates(all_txns(), paydays(), [RULE]) == []
    declined = dict(RULE, kind="declined", label="")
    assert find_candidates(all_txns(), paydays(), [declined]) == []


def test_new_price_is_noticed_after_two_payments_when_a_rule_exists():
    extra = {5: [bp(payday(5) + timedelta(days=1), "RENT", 700)], 6: [bp(payday(6) + timedelta(days=2), "RENT", 700)]}
    cs = cycles(extra)
    found = find_candidates(all_txns(cs), paydays(cs), [RULE])
    assert len(found) == 1 and found[0]["usual"] == pytest.approx(700.0)
    assert [(e["date"], e["amount"]) for e in found[0]["examples"]] == [
        ("2024-05-29", 700.0), ("2024-06-29", 650.0), ("2024-06-30", 700.0)]
    assert find_candidates(all_txns(cs), paydays(cs), []) != []                   # without a rule it is found too (550 group)


def scripted(*replies):
    it = iter(replies)
    calls = []

    def ask(prompt):
        calls.append(prompt)
        r = next(it)
        if isinstance(r, Exception):
            raise r
        return r
    ask.calls = calls
    return ask


@pytest.mark.parametrize("reply", ["y", "", "Y"])
def test_yes_saves_a_common_rule(reply):
    conn, lines = open_db(":memory:"), []
    ask = scripted(reply)
    assert review_rules(conn, all_txns(), paydays(), ask, out=lines.append) == 1
    rule = get_rules(conn)[0]
    assert (rule["payer"], rule["kind"], rule["label"], rule["max_days"]) == (PAYER, "common", "Rent", 2)
    assert rule["usual"] == pytest.approx(550.0) and rule["tolerance"] == pytest.approx(0.10)
    text = "\n".join(lines)
    for want in ("PAYDAY TRANSFERS", "SAM PARKER", "550.00", "within 2 days of payday", "ref FOOD",
                 "2024-02-29", "Count these as Common", '"Rent"'):
        assert want in text, want
    assert all(ord(c) < 128 for c in text)
    # asked once only
    again = scripted()
    assert review_rules(conn, all_txns(), paydays(), again, out=lambda s: None) == 0 and again.calls == []


def test_no_saves_a_declined_rule_and_is_not_asked_again():
    conn = open_db(":memory:")
    assert review_rules(conn, all_txns(), paydays(), scripted("n"), out=lambda s: None) == 1
    r = get_rules(conn)[0]
    assert r["kind"] == "declined" and r["label"] == ""
    again = scripted()
    assert review_rules(conn, all_txns(), paydays(), again, out=lambda s: None) == 0 and again.calls == []


def test_typing_a_label_uses_it():
    conn = open_db(":memory:")
    review_rules(conn, all_txns(), paydays(), scripted("  House rent "), out=lambda s: None)
    r = get_rules(conn)[0]
    assert r["kind"] == "common" and r["label"] == "House rent"


@pytest.mark.parametrize("err", [EOFError(), OSError()])
def test_no_keyboard_stops_quietly(err):
    conn = open_db(":memory:")
    assert review_rules(conn, all_txns(), paydays(), scripted(err), out=lambda s: None) == 0
    assert get_rules(conn) == []


def test_nothing_to_ask_prints_nothing():
    conn, lines = open_db(":memory:"), []
    assert review_rules(conn, [], [], scripted(), out=lines.append) == 0 and lines == []


def test_store_rules_round_trip_and_validation():
    conn = open_db(":memory:")
    add_rule(conn, "SAM PARKER", 550.0, "Rent")
    add_rule(conn, "CHLOE", 120.0, "", kind="declined", max_days=3, tolerance=0.2, source="suggested")
    rules = get_rules(conn)
    assert [r["payer"] for r in rules] == ["SAM PARKER", "CHLOE"]
    assert rules[0] == {"payer": "SAM PARKER", "usual": 550.0, "label": "Rent", "kind": "common",
                        "max_days": 2, "tolerance": 0.10, "source": "user"}
    assert rules[1]["kind"] == "declined" and rules[1]["max_days"] == 3 and rules[1]["source"] == "suggested"
    with pytest.raises(ValueError):
        add_rule(conn, "X", 1.0, "", kind="banana")


def test_many_small_payday_top_ups_do_not_hide_the_rent():
    # Real oddity (Oct 2026): small food top-ups to the same person on payday outnumbered the rent
    # payments, so the small group won and the rent was never asked about. Amounts under MIN_USUAL
    # are left out before looking for the usual amount.
    extra = {k: [bp(payday(k), "Food", 50), bp(payday(k) + timedelta(days=1), "Food", 52)] for k in range(1, 7)}
    cs = cycles(extra)
    found = find_candidates(all_txns(cs), paydays(cs), [])
    assert len(found) == 1
    assert found[0]["usual"] == pytest.approx(550.0)
    assert found[0]["suggest_label"] == "Rent"
    assert [e["amount"] for e in found[0]["examples"]] == [550.0, 550.0, 550.0, 590.0]
