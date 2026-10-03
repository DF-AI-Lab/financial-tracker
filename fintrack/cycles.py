from datetime import timedelta
from typing import List

from fintrack.models import Cycle, Txn

WAGE_PAYER = "VERTU MOTORS PLC"
WAGE_MIN = 500.0


def is_wage(t: Txn, payer=WAGE_PAYER, min_amount: float = WAGE_MIN) -> bool:
    """True if t is money IN from the wage payer: amount >= min_amount and the payer name
    (case-insensitive) is contained in t.description. `payer` may be one name or a list
    of names (after a job change)."""
    payers = [payer] if isinstance(payer, str) else payer
    return t.amount >= min_amount and any(p.lower() in t.description.lower() for p in payers)


def build_cycles(txns: List[Txn], payer=WAGE_PAYER, min_amount: float = WAGE_MIN) -> List[Cycle]:
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
    # Sort by date, maintaining order for same date
    sorted_txns = sorted(txns, key=lambda t: t.date)

    # Find first wage
    first_wage_idx = None
    for i, t in enumerate(sorted_txns):
        if is_wage(t, payer, min_amount):
            first_wage_idx = i
            break

    if first_wage_idx is None:
        return []

    cycles = []
    current_cycle_start = None
    current_cycle_txns = []
    current_cycle_wage = 0.0

    for t in sorted_txns:
        if t.date < sorted_txns[first_wage_idx].date:
            # Before first wage, drop it
            continue

        if is_wage(t, payer, min_amount):
            # Check if this wage is within 10 days of the current cycle start
            if current_cycle_start is not None and (t.date - current_cycle_start).days <= 10:
                # Same cycle, add to wage
                current_cycle_txns.append(t)
                current_cycle_wage += t.amount
            else:
                # New cycle
                if current_cycle_start is not None:
                    # Close previous cycle
                    cycles.append(Cycle(
                        start=current_cycle_start,
                        end=current_cycle_txns[-1].date,  # Will be updated
                        wage=current_cycle_wage,
                        txns=current_cycle_txns,
                        complete=False  # Will be updated
                    ))

                # Start new cycle
                current_cycle_start = t.date
                current_cycle_txns = [t]
                current_cycle_wage = t.amount
        else:
            # Regular payment
            if current_cycle_start is not None:
                current_cycle_txns.append(t)

    # Close the last cycle
    if current_cycle_start is not None:
        cycles.append(Cycle(
            start=current_cycle_start,
            end=current_cycle_txns[-1].date,
            wage=current_cycle_wage,
            txns=current_cycle_txns,
            complete=False
        ))

    # Update end dates for complete cycles
    for i in range(len(cycles) - 1):
        cycles[i].end = cycles[i + 1].start - timedelta(days=1)
        cycles[i].complete = True

    return cycles


def cycle_report(cycles: List[Cycle]) -> List[dict]:
    """One row per cycle, in order: {"label", "start", "end", "complete", "wage", "other_in",
    "bills", "random", "spare"}.

    start/end are ISO date strings. wage = Cycle.wage. other_in = money IN that is not a wage
    payment (refunds, family money). bills = money OUT with type DD or SO. random = all other
    money OUT. All positive numbers rounded to 2 decimals. spare = wage + other_in - bills - random.
    """
    rows = []
    for c in cycles:
        # Sum all amounts
        total_in = 0.0
        bills = 0.0
        random = 0.0

        for t in c.txns:
            if t.amount > 0:
                total_in += t.amount
            else:
                # Money out
                if t.type in ('DD', 'SO'):
                    bills += abs(t.amount)
                else:
                    random += abs(t.amount)

        other_in = total_in - c.wage
        spare = c.wage + other_in - bills - random

        rows.append({
            'label': c.label,
            'start': c.start.isoformat(),
            'end': c.end.isoformat(),
            'complete': c.complete,
            'wage': round(c.wage, 2),
            'other_in': round(other_in, 2),
            'bills': round(bills, 2),
            'random': round(random, 2),
            'spare': round(spare, 2)
        })

    return rows
