"""Calculate expected spare for this cycle and last cycle check (expected vs actual)."""
from datetime import date
from typing import Optional, List

from fintrack.models import Analysis, Cycle, Txn
from fintrack.common import analyse
from fintrack.yearly import yearly_lines


def balance_before(txns: List[Txn], day: date) -> Optional[float]:
    """The balance of the last txn (in list order, after sort by date) before `day`.

    Returns None if there is no txn before the day or no balance is set.
    """
    best = None
    for t in sorted(txns, key=lambda t: t.date):     # stable: same-day order is kept
        if t.date < day and t.balance is not None:
            best = t.balance
    return best


def expected_bills(analysis: Analysis) -> float:
    """Sum of expected bills from analysis.common.

    For each common entry: use last if > 0, else use average.
    """
    total = 0.0
    for entry in analysis.common.values():
        if entry["last"] > 0:
            total += entry["last"]
        else:
            total += entry["average"]
    return total


def expected_spare(cycles: List[Cycle], analysis: Analysis, wage: float, yearly: Optional[List[dict]] = None) -> dict:
    """Calculate expected spare for the newest cycle.

    Returns dict with keys: "start", "cycles_used", "left_over", "wage", "bills", "normal", "expected", "yearly".
    """
    if yearly is None:
        yearly = []

    # Get all txns from all cycles
    all_txns = []
    for cycle in cycles:
        all_txns.extend(cycle.txns)

    # Get the newest cycle
    newest = cycles[-1]

    # Calculate left_over (balance before this cycle starts)
    left_over = balance_before(all_txns, newest.start)

    # Calculate bills and normal spending
    bills = expected_bills(analysis)
    normal = analysis.random_per_cycle

    # Calculate expected: left_over (or 0 if None) + wage - bills - normal
    left_over_for_calc = left_over if left_over is not None else 0
    expected = left_over_for_calc + wage - bills - normal

    # Build yearly with spare_if_paid (keep only label, amount, paid, and the new spare_if_paid)
    yearly_with_spare = []
    for item in yearly:
        yearly_with_spare.append({
            "label": item["label"],
            "amount": item["amount"],
            "paid": item["paid"],
            "spare_if_paid": expected - item["amount"]
        })

    return {
        "start": newest.start,
        "cycles_used": analysis.cycles_used,
        "left_over": left_over,
        "wage": wage,
        "bills": bills,
        "normal": normal,
        "expected": expected,
        "yearly": yearly_with_spare
    }


def format_expected(e: dict) -> List[str]:
    """Format expected spare as lines.

    cycles_used == 0 -> a single "not enough" line.
    """
    if e["cycles_used"] == 0:
        return ["Not enough finished paydays yet to work out the expected spare."]

    lines = []

    def fmt_money(val: float) -> str:
        return f"{val:,.2f}"

    # Header line
    lines.append(f"IF YOUR PAY IS {fmt_money(e['wage'])}   (this cycle, from {e['start']:%d %b %Y})")

    # Left over line
    if e["left_over"] is not None:
        left_str = fmt_money(e['left_over'])
        left_note = "   (balance just before this payday)"
    else:
        left_str = "unknown"
        left_note = "   (counted as 0)"
    lines.append(f"  {'Left over from last month':<28}{left_str:>10}{left_note}")

    # Wage line
    lines.append(f"+ {'Wage':<28}{fmt_money(e['wage']):>10}")

    # Bills line
    lines.append(f"- {'Bills':<28}{fmt_money(e['bills']):>10}   (last month's amount of each bill)")

    # Normal spending line
    lines.append(f"- {'Normal spending':<28}{fmt_money(e['normal']):>10}   ({e['cycles_used']}-cycle average, no one-offs)")

    # Expected spare line
    lines.append(f"= {'Expected spare':<28}{fmt_money(e['expected']):>10}")

    # Yearly lines
    for item in e["yearly"]:
        # Add the warning line from yearly_lines
        warning_lines = yearly_lines([item])
        for warning in warning_lines:
            lines.append(warning)
        # Add the spare_if_paid line
        lines.append(f"  {'Expected spare if paid':<28}{fmt_money(item['spare_if_paid']):>10}")

    return lines


def last_cycle_check(cycles: List[Cycle], answers: Optional[dict] = None, rules: Optional[list] = None) -> Optional[dict]:
    """Check last finished cycle: expected vs actual.

    Returns None if no complete cycle, or i == 0 (nothing before it), or before.cycles_used == 0.
    """
    # Find the last complete cycle
    complete_cycles = [c for c in cycles if c.complete]

    if not complete_cycles:
        return None

    # Get index of the last complete cycle in the full cycles list
    target_idx = None
    for i, c in enumerate(cycles):
        if c.complete and c is complete_cycles[-1]:
            target_idx = i
            break

    if target_idx is None or target_idx == 0:
        return None

    target = cycles[target_idx]

    # Analyse the cycles before this one
    before = analyse(cycles[:target_idx], answers=answers, rules=rules)

    if before.cycles_used == 0:
        return None

    # Get all txns from all cycles
    all_txns = []
    for cycle in cycles:
        all_txns.extend(cycle.txns)

    # Calculate left_over
    left_over = balance_before(all_txns, target.start)
    lo = left_over if left_over is not None else 0

    # Calculate expected
    bills = expected_bills(before)
    normal = before.random_per_cycle
    expected = lo + target.wage - bills - normal

    # Calculate actual
    # Other money in = everything in minus the wage credit(s), which can be more than one payment
    other_in = sum(t.amount for t in target.txns if t.amount > 0) - target.wage
    money_out = sum(-t.amount for t in target.txns if t.amount < 0)

    actual = lo + target.wage + other_in - money_out
    missing = expected - actual

    return {
        "start": target.start,
        "end": target.end,
        "left_over": left_over,
        "wage": target.wage,
        "bills": bills,
        "normal": normal,
        "expected": expected,
        "other_in": other_in,
        "money_out": money_out,
        "actual": actual,
        "missing": missing
    }


def format_last_cycle(c: Optional[dict]) -> List[str]:
    """Format last cycle check as lines.

    Returns [] for None.
    """
    if c is None:
        return []

    lines = []

    def fmt_money(val: float) -> str:
        return f"{val:,.2f}"

    # Header line
    lines.append(f"LAST CYCLE: EXPECTED vs ACTUAL   ({c['start']:%d %b %Y} to {c['end']:%d %b %Y})")

    # Expected section
    if c["left_over"] is None:
        left_str = "unknown"
    else:
        left_str = fmt_money(c['left_over'])
    lines.append(f"  {'Left over from last month':<28}{left_str:>10}")

    lines.append(f"+ {'Wage':<28}{fmt_money(c['wage']):>10}")
    lines.append(f"- {'Bills':<28}{fmt_money(c['bills']):>10}")
    lines.append(f"- {'Normal spending':<28}{fmt_money(c['normal']):>10}")
    lines.append(f"= {'Expected spare':<28}{fmt_money(c['expected']):>10}")

    # Blank line
    lines.append("")

    # Actual section
    lines.append(f"  {'Left over from last month':<28}{left_str:>10}")
    lines.append(f"+ {'Wage':<28}{fmt_money(c['wage']):>10}")
    lines.append(f"+ {'Other money in':<28}{fmt_money(c['other_in']):>10}")
    lines.append(f"- {'All money out':<28}{fmt_money(c['money_out']):>10}")
    lines.append(f"= {'Actual spare':<28}{fmt_money(c['actual']):>10}   (your balance at the end of the cycle)")

    # Blank line
    lines.append("")

    # Missing line
    if c["missing"] >= -0.005:
        lines.append(f"  {'Missing':<28}{fmt_money(c['missing']):>10}   (expected - actual)")
    else:
        lines.append(f"  {'Better than expected by':<28}{fmt_money(-c['missing']):>10}")

    return lines
