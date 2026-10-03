"""No. 4 (user, 3 Oct 2026): a new job spotted by itself.

When no wage from a known payer has come in for GAP_DAYS or more (up to the last statement day), any other payer
that has paid in WAGE_MIN or more in 2+ different months since the last wage is a candidate. The page asks once:
'Is X your new job?'. Yes -> fintrack.wages.add_payer (as `run.py wage NAME` does); No -> not asked about again.
"""
import re
from typing import List

from fintrack.cycles import WAGE_MIN, is_wage

GAP_DAYS = 35


def payer_of(description: str) -> str:
    """The payer name to save: the description up to the first digit, upper case ("PENDRAGON PAYROLL 0042" ->
    "PENDRAGON PAYROLL"), so is_wage (name contained in the description) matches every payment."""
    return " ".join(re.split(r"\d", description.upper())[0].split())


def new_job_candidates(txns, payers: List[str], declined: List[str]) -> List[dict]:
    """[{"name", "count", "usual" (the latest amount), "first", "last"}], most payments first."""
    if not txns:
        return []
    end = max(t.date for t in txns)
    wages = [t.date for t in txns if is_wage(t, payers)]
    last_wage = max(wages) if wages else None
    if last_wage is not None and (end - last_wage).days < GAP_DAYS:
        return []
    skip = {p.upper() for p in payers} | {d.upper() for d in declined}
    groups = {}
    for t in sorted(txns, key=lambda t: t.date):
        if t.amount < WAGE_MIN or (last_wage is not None and t.date <= last_wage):
            continue
        name = payer_of(t.description)
        if len(name) < 3 or name in skip:
            continue
        groups.setdefault(name, []).append(t)
    out = []
    for name, ts in groups.items():
        if len({(t.date.year, t.date.month) for t in ts}) < 2:
            continue
        out.append({"name": name, "count": len(ts), "usual": ts[-1].amount, "first": ts[0].date, "last": ts[-1].date})
    out.sort(key=lambda c: (-c["count"], c["name"]))
    return out
