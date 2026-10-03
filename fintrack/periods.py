"""Totals for the last 6 months, the last 12 months and this year so far (whole pay cycles)."""
from fintrack.paydayrule import matches_rule
from fintrack.store import item_key


def period_totals(cycles, answers=None, rules=None):
    """Return period summaries: [{"name", "cycles", "wage", "other_in", "bills", "spending", "oneoffs", "left"}].

    Periods (in order): "Last 6 months" (last 6 complete cycles, or fewer), "Last 12 months" (last 12, or fewer),
    "{year} so far" (the complete cycles that start in the year of the last complete cycle). [] if none complete.

    wage = sum of cycle.wage; other_in = all money in - wage; left = wage + other_in - bills - spending - oneoffs.
    Every money-out payment goes in exactly one of bills / spending / oneoffs, decided per payment:
    1. covered by a "common" payday-transfer rule (matches_rule with its cycle's start) -> bills;
    2. else the saved answer for its item_key: "regular"/"common" -> bills, "oneoff"/"yearly" -> oneoffs,
       "random" -> spending;
    3. else (no rule, no answer): DD or SO -> bills; 1,000 or more -> oneoffs; anything else -> spending.
    """
    answers = answers or {}
    rules = rules or []
    complete = [c for c in cycles if c.complete]
    if not complete:
        return []

    year = complete[-1].start.year
    return [_summarize("Last 6 months", complete[-6:], answers, rules),
            _summarize("Last 12 months", complete[-12:], answers, rules),
            _summarize(f"{year} so far", [c for c in complete if c.start.year == year], answers, rules)]


def _kind(t, cycle, answers, rules):
    """"bills", "spending" or "oneoffs" for one money-out payment (rules in period_totals' docstring)."""
    if any(r["kind"] == "common" and matches_rule(t, r, cycle.start) for r in rules):
        return "bills"
    answer = answers.get(item_key(t))
    if answer:
        if answer["kind"] in ("regular", "common"):
            return "bills"
        if answer["kind"] in ("oneoff", "yearly"):
            return "oneoffs"
        if answer["kind"] == "random":
            return "spending"
    if t.type in ("DD", "SO"):
        return "bills"
    return "oneoffs" if abs(t.amount) >= 1000 else "spending"


def _summarize(name, period_cycles, answers, rules):
    totals = {"bills": 0.0, "spending": 0.0, "oneoffs": 0.0}
    money_in = 0.0
    for cycle in period_cycles:
        for t in cycle.txns:
            if t.amount > 0:
                money_in += t.amount
            elif t.amount < 0:
                totals[_kind(t, cycle, answers, rules)] += -t.amount
    wage = sum(c.wage for c in period_cycles)
    other_in = money_in - wage
    return {"name": name, "cycles": len(period_cycles), "wage": wage, "other_in": other_in, **totals,
            "left": wage + other_in - totals["bills"] - totals["spending"] - totals["oneoffs"]}
