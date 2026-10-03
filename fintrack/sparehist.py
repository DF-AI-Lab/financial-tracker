"""Spare cash in past months: pay - bills actually paid, for the last finished month and the average
over the months the averages use (usually 6). Lets the user see when this month looks odd."""
from typing import List, Optional

from fintrack.models import Analysis, Cycle


def spare_history(cycles: List[Cycle], analysis: Analysis) -> Optional[dict]:
    """{"last", "avg", "months"} or None when no month has finished yet."""
    if analysis.cycles_used == 0:
        return None
    window = [c for c in cycles if c.complete][-analysis.cycles_used:]
    bill_ids = {id(t) for ts in analysis.common_txns.values() for t in ts}
    spares = [c.wage - sum(-t.amount for t in c.txns if id(t) in bill_ids) for c in window]
    return {"last": spares[-1], "avg": sum(spares) / len(spares), "months": len(spares)}
