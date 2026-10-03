"""Paid early: a payment made a day or two before payday can count from that payday."""
from datetime import date

import run
from fintrack.cycles import build_cycles
from fintrack.early import apply_moves, candidates, key, moved_keys, toggle
from fintrack.models import Txn
from fintrack.spare import balance_before
from fintrack.store import open_db

PAY = ["NEW JOB LTD"]

def txns():
    return [
        Txn(date(2026, 7, 28), "CR", "NEW JOB LTD", "", 2700.0, 2900.0),
        Txn(date(2026, 7, 28), "BP", "KATIE FINCH", "Rent", -600.0, 2300.0),
        Txn(date(2026, 8, 24), "VIS", "TESCO", "", -10.0, 916.38),
        Txn(date(2026, 8, 27), "VIS", "COFFEE", "", -5.0),
        Txn(date(2026, 8, 27), "BP", "KATIE FINCH", "Rent", -610.0, 301.38),
        Txn(date(2026, 8, 28), "CR", "NEW JOB LTD", "", 3053.07, 3354.45),
        Txn(date(2026, 8, 29), "VIS", "TESCO", "", -20.0, 3334.45),
    ]

def test_candidates_are_money_out_in_the_days_before_a_payday():
    found = candidates(txns(), PAY)
    assert [(t.description, t.amount, pay) for t, pay in found] == [
        ("KATIE FINCH", -610.0, date(2026, 8, 28))]          # newest first; under 20 left out

def test_moved_payment_counts_in_the_next_cycle_and_left_over_ignores_it():
    t = txns()
    keys = {key(t[4])}
    moved = apply_moves(t, keys, PAY)
    cs = build_cycles(moved, payer=PAY)
    assert -610.0 not in [x.amount for x in cs[0].txns]
    assert cs[1].txns[0].description == "NEW JOB LTD"          # wage still first
    assert -610.0 in [x.amount for x in cs[1].txns]
    # balance just before payday = as if the rent had not gone yet (coffee still counted)
    assert round(balance_before(moved, date(2026, 8, 28)), 2) == 911.38

def test_toggle_is_saved_and_undone(tmp_path):
    conn = open_db(":memory:")
    t = txns()[4]
    assert toggle(conn, t) is True
    assert len(moved_keys(conn)) == 1
    assert toggle(conn, t) is False
    assert moved_keys(conn) == set()

def test_early_command_lists_and_moves(tmp_path, monkeypatch):
    import fintrack.early as early
    db = tmp_path / "tracker.db"
    open_db(db).close()
    monkeypatch.setattr(run, "load_txns", lambda conn: txns(), raising=False)
    monkeypatch.setattr(early, "load_txns", lambda conn: txns())
    lines = []
    run.run_command(["early"], out=lines.append, db_path=db, in_dir=tmp_path, wage_payer="NEW JOB LTD")
    text = "\n".join(lines)
    assert "1" in text and "KATIE FINCH" in text and "610.00" in text and "28 Aug" in text
    lines.clear()
    run.run_command(["early", "1"], out=lines.append, db_path=db, in_dir=tmp_path, wage_payer="NEW JOB LTD")
    assert any("Moved" in l for l in lines)
    assert len(moved_keys(open_db(db))) == 1
    lines.clear()
    run.run_command(["early", "9"], out=lines.append, db_path=db, in_dir=tmp_path, wage_payer="NEW JOB LTD")
    assert any("no" in l.lower() for l in lines)
