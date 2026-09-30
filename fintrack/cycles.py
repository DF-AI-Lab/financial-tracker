from typing import List

from fintrack.models import Cycle, Txn

WAGE_PAYER = "VERTU MOTORS PLC"
WAGE_MIN = 500.0


def is_wage(t: Txn, payer: str = WAGE_PAYER, min_amount: float = WAGE_MIN) -> bool:
    """True if t is money IN from the wage payer: amount >= min_amount and the payer name
    (case-insensitive) is contained in t.description."""
    raise NotImplementedError


def build_cycles(txns: List[Txn], payer: str = WAGE_PAYER, min_amount: float = WAGE_MIN) -> List[Cycle]:
    """Split payments into payday-to-payday cycles, oldest first.

    - Sort by date (keep the given order for the same date).
    - A wage payment (is_wage) starts a new cycle on its date, and the wage payment is the
      first txn of that cycle. EXCEPTION: a wage payment within 10 days after the cycle's
      first wage is NOT a new cycle (bonus/extra); it stays in the same cycle and adds to
      Cycle.wage.
    - Payments before the first wage are dropped (not part of any cycle).
    - A cycle runs until the next cycle starts. For a complete cycle, end = the day before the
      next cycle's start. The last cycle has complete=False and end = date of its last payment.
    - No wage found at all -> [].
    """
    raise NotImplementedError


def cycle_report(cycles: List[Cycle]) -> List[dict]:
    """One row per cycle, in order: {"label", "start", "end", "complete", "wage", "other_in",
    "bills", "random", "spare"}.

    start/end are ISO date strings. wage = Cycle.wage. other_in = money IN that is not a wage
    payment (refunds, family money). bills = money OUT with type DD or SO. random = all other
    money OUT. All positive numbers rounded to 2 decimals. spare = wage + other_in - bills - random.
    """
    raise NotImplementedError
