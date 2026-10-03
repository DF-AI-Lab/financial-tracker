"""Calculate expected spare for this cycle and last cycle check (expected vs actual)."""
from datetime import date
from typing import Optional, List
import statistics

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


def pay_block(cycles: List[Cycle], analysis: Analysis, wage: float, categories=None, items=None, yearly=None,
              changes=None) -> dict:
    """Calculate the pay block: bills, spending, spare cash.

    Returns dict with keys: "start", "cycles_used", "left_over", "wage", "bills", "bills_avg",
    "bills_last", "spare", "spending", "spending_last", "spending_avg", "left_usual".
    """
    if categories is None:
        categories = {}
    if items is None:
        items = {}
    if yearly is None:
        yearly = []

    # Get the expected spare for "start", "left_over", "cycles_used"
    e = expected_spare(cycles, analysis, wage, yearly)

    # Build bills: one dict per analysis.common entry
    # used = what counts for this cycle: a change typed on the home page (fintrack/billchange.py), else last month,
    # else the average (not paid last month: shown with a *). diff = used - average (None when the average is used).
    changes = changes or {}
    bills = []
    for key, entry in analysis.common.items():
        changed = key in changes
        estimated = not changed and entry["last"] <= 0
        used = changes[key] if changed else (entry["average"] if estimated else entry["last"])
        bills.append({
            "key": key,
            "name": entry.get("label", key),
            "avg": entry["average"],
            "last": entry["last"],
            "used": used,
            "changed": changed,
            "estimated": estimated,
            "diff": None if estimated else used - entry["average"]
        })

    # Sort by avg biggest first (ties: name)
    bills.sort(key=lambda b: (-b["avg"], b["name"]))

    # Calculate bills_avg and bills_last
    bills_avg = sum(b["avg"] for b in bills)
    bills_last = sum(b["used"] for b in bills)

    # Spare = pay - bills (last month's amounts). Left over is not added (user, 3 Oct 2026).
    spare = wage - bills_last

    # Get the last COMPLETE cycle
    complete_cycles = [c for c in cycles if c.complete]
    if not complete_cycles:
        spending = []
        spending_last = 0.0
        spending_avg = 0.0
    else:
        last_cycle = complete_cycles[-1]

        # Build spending dict: category -> {...}
        spending_dict = {}
        last_ids = {id(t) for t in last_cycle.txns}

        # Get all random_txns that are in the last complete cycle
        for txn in analysis.random_txns:
            if id(txn) not in last_ids:
                continue

            # Get category and label
            from fintrack.bycategory import label_and_category
            rules = []  # No rules needed for this context
            label, category = label_and_category(txn, items, categories, rules, last_cycle, 1000.0)

            if category is None or label is None:
                continue

            if category not in spending_dict:
                spending_dict[category] = {"last": 0.0, "labels": {}}

            spending_dict[category]["last"] += abs(txn.amount)
            if label not in spending_dict[category]["labels"]:
                spending_dict[category]["labels"][label] = 0.0
            spending_dict[category]["labels"][label] += abs(txn.amount)

        # Calculate averages for all random_txns
        cycles_used = analysis.cycles_used
        for txn in analysis.random_txns:
            from fintrack.bycategory import label_and_category
            rules = []
            label, category = label_and_category(txn, items, categories, rules, last_cycle, 1000.0)

            if category is None or label is None:
                continue

            if category not in spending_dict:
                spending_dict[category] = {"last": 0.0, "labels": {}}
            if "avg" not in spending_dict[category]:
                spending_dict[category]["avg"] = 0.0
            if label not in spending_dict[category]["labels"]:
                spending_dict[category]["labels"][label] = 0.0

            spending_dict[category]["avg"] += abs(txn.amount) / cycles_used if cycles_used > 0 else 0.0

        # Build spending list with top 3 labels per category
        spending = []
        for category, data in spending_dict.items():
            # Get top 3 labels by last-cycle total
            label_totals = [(label, total) for label, total in data["labels"].items() if total > 0]
            label_totals.sort(key=lambda x: (-x[1], x[0]))
            top_labels = [label for label, _ in label_totals[:3]]

            row = {
                "category": category,
                "last": data.get("last", 0.0),
                "avg": data.get("avg", 0.0),
                "labels": top_labels
            }
            spending.append(row)

        # Sort by last biggest first, then avg biggest first, then category
        spending.sort(key=lambda s: (-s["last"], -s["avg"], s["category"]))

        spending_last = sum(s["last"] for s in spending)
        spending_avg = sum(s["avg"] for s in spending)

    # Calculate left_usual
    left_usual = spare - spending_avg

    return {
        "start": e["start"],
        "cycles_used": e["cycles_used"],
        "left_over": e["left_over"],
        "wage": wage,
        "bills": bills,
        "bills_avg": bills_avg,
        "bills_last": bills_last,
        "spare": spare,
        "spending": spending,
        "spending_last": spending_last,
        "spending_avg": spending_avg,
        "left_usual": left_usual,
        "yearly": [dict(label=y["label"], amount=y["amount"], paid=y["paid"], left_if_paid=spare - y["amount"])
                   for y in yearly]
    }


def format_pay_block(p: dict) -> List[str]:
    """Format the pay block as lines.

    cycles_used == 0 -> a single "not enough" line.
    """
    if p["cycles_used"] == 0:
        return ["Not enough finished paydays yet to work out the spare cash."]

    lines = []

    def fmt_money(val: float) -> str:
        return f"{val:,.2f}"

    # Header line
    lines.append(f"IF YOUR PAY IS {fmt_money(p['wage'])}   (this cycle, from {p['start']:%d %b %Y})")
    lines.append("")

    # Bills section
    avg_head = f"{p['cycles_used']}-mth avg"
    lines.append(f"{'BILLS (every month)':<34}{avg_head:>10}  {'Last month':>10}")
    for bill in p["bills"]:
        mark = "*" if bill.get("estimated") else ("  (changed)" if bill.get("changed") else "")
        used = bill.get("used", bill["last"])
        lines.append(f"  {bill['name']:<32}{fmt_money(bill['avg']):>10}  {fmt_money(used):>10}{mark}")

    lines.append(f"  {'Bills total':<32}{fmt_money(p['bills_avg']):>10}  {fmt_money(p['bills_last']):>10}")
    if any(b.get("estimated") for b in p["bills"]):
        lines.append("  * not paid last month, average used")
    lines.append("")

    lines.append(f"  {'Pay':<32}{fmt_money(p['wage']):>10}")
    lines.append(f"- {'Bills (last month amounts)':<32}{fmt_money(p['bills_last']):>10}")
    lines.append(f"= {'SPARE CASH':<32}{fmt_money(p['spare']):>10}")
    lines.append("")

    # Spending section
    if p["spending"]:
        lines.append(f"{'LAST MONTH SPENDING (not bills)':<34}{'Last month':>10}  {avg_head:>10}")
        for spend in p["spending"]:
            labels_str = f"   ({', '.join(spend['labels'])})" if spend["labels"] else ""
            lines.append(f"  {spend['category']:<32}{fmt_money(spend['last']):>10}  {fmt_money(spend['avg']):>10}{labels_str}")

        lines.append(f"  {'Total':<32}{fmt_money(p['spending_last']):>10}  {fmt_money(p['spending_avg']):>10}")
        lines.append("")


    # Yearly items
    from fintrack.yearly import yearly_lines
    for item in p.get("yearly", []):
        for warning in yearly_lines([item]):
            lines.append(warning)
        lines.append(f"  {'If that is paid too, left':<32}{fmt_money(item['left_if_paid']):>10}")

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
