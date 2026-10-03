"""Typed spends: matching to statements and managing expectations."""
from datetime import date
from typing import List, Optional, Tuple

from fintrack.left import parse_money
from fintrack.models import Analysis, Cycle, Txn
from fintrack.spare import expected_spare


def parse_add(args: List[str]) -> Optional[Tuple[float, str]]:
    """Parse command-line args for "add" command.

    Returns (amount, name) or None:
    - amount = left.parse_money(args[0])
    - name = " ".join(args[1:]).strip()
    - None if no args, amount None or name empty.
    """
    if not args:
        return None

    amount = parse_money(args[0])
    if amount is None:
        return None

    name = " ".join(args[1:]).strip()
    if not name:
        return None

    return (amount, name)


def match_spends(spends: List[dict], txns: List[Txn]) -> Tuple[List[int], List[dict]]:
    """Match typed spends to transactions.

    Go through spends in list order; for each, candidates are money-out Txns
    (amount < 0) not used yet with abs(abs(t.amount) - spend amount) < 0.005
    and -1 <= (t.date - spend date).days <= 5; take the one with the smallest
    abs day difference (ties: earliest date); mark it used.

    Returns (matched_ids, unmatched_spends):
    - matched_ids = list of spend ids matched (in spend order)
    - unmatched_spends = the other spend dicts in order
    """
    matched_ids = []
    used_txn_indices = set()

    # Sort txns by date for processing
    indexed_txns = [(i, t) for i, t in enumerate(txns)]

    for spend in spends:
        spend_date = spend["date"]
        spend_amount = spend["amount"]

        # Find candidates
        candidates = []
        for idx, txn in indexed_txns:
            if idx in used_txn_indices:
                continue
            if txn.amount >= 0:  # Only money-out
                continue

            # Check amount match
            if abs(abs(txn.amount) - spend_amount) >= 0.005:
                continue

            # Check date match
            day_diff = (txn.date - spend_date).days
            if day_diff < -1 or day_diff > 5:
                continue

            candidates.append((idx, txn, abs(day_diff)))

        # Find best match
        if candidates:
            # Sort by day difference (ascending), then by date (ascending)
            candidates.sort(key=lambda x: (x[2], x[1].date))
            best_idx, best_txn, _ = candidates[0]
            matched_ids.append(spend["id"])
            used_txn_indices.add(best_idx)

    # Find unmatched spends
    matched_set = set(matched_ids)
    unmatched_spends = [s for s in spends if s["id"] not in matched_set]

    return (matched_ids, unmatched_spends)


def swap_spends(conn, txns: List[Txn], ask, out=print) -> int:
    """Match typed spends to txns and delete matched ones.

    Deletes matched spends from the database. For each unmatched spend with
    date <= last txn date, asks whether to keep it.

    Returns number matched.
    """
    from fintrack.store import get_spends, delete_spend

    spends = get_spends(conn)
    matched_ids, unmatched_spends = match_spends(spends, txns)

    # Delete matched spends
    for spend_id in matched_ids:
        delete_spend(conn, spend_id)

    # Find the latest txn date
    last_date = None
    if txns:
        last_date = max(t.date for t in txns)

    # Ask about unmatched spends
    for spend in unmatched_spends:
        # Only ask if spend date <= latest txn date
        if last_date is not None and spend["date"] <= last_date:
            try:
                answer = ask(
                    f"Typed spend {spend['amount']:.2f} {spend['name']} "
                    f"({spend['date']:%d %b %Y}) is not in your statements. "
                    f"Keep it? y/n (Enter = keep) "
                )
                # Answer "n" (any case, stripped) -> delete it
                if answer.strip().lower() == "n":
                    delete_spend(conn, spend["id"])
            except (EOFError, OSError):
                # No keyboard -> stop asking, keep the rest
                break

    # Output message
    if matched_ids:
        n = len(matched_ids)
        plural = "s" if n != 1 else ""
        out(f"Matched {n} typed spend{plural} to your statements (removed from the typed list).")

    return len(matched_ids)


def money_for_spending(cycles: List[Cycle], analysis: Analysis, wage: float) -> float:
    """Calculate left over + wage - bills.

    Uses spare.expected_spare(cycles, analysis, wage) to get "left_over" and "bills".
    Returns left_over (or 0) + wage - bills.
    """
    if not cycles:
        return wage

    spare = expected_spare(cycles, analysis, wage)
    left_over = spare["left_over"] if spare["left_over"] is not None else 0
    return left_over + wage - spare["bills"]


def format_spends(spends: List[dict], money: float) -> List[str]:
    """Format typed spends as a display block.

    Returns list[str] as shown in test_format_spends / test_format_spends_when_nothing_is_typed.
    """
    lines = []
    lines.append("SO FAR THIS CYCLE (typed in)")

    if not spends:
        lines.append("  (nothing typed yet)")
    else:
        # Format each spend
        for i, spend in enumerate(spends, 1):
            name = spend["name"]
            category = spend["category"] if spend["category"] else "Unsorted"
            date_str = f"{spend['date']:%d %b}"
            amount_str = f"{spend['amount']:,.2f}"
            line = f"  {i:>2}  {date_str}  {name:<22}{amount_str:>10}   ({category})"
            lines.append(line)

    # Total typed
    total_typed = sum(s["amount"] for s in spends)
    total_str = f"{total_typed:,.2f}"
    lines.append(f"  {'Typed so far':<34}{total_str:>10}")

    # Blank line
    lines.append("")

    # Money for spending
    money_str = f"{money:,.2f}"
    lines.append(f"  {'Money for spending':<34}{money_str:>10}   (left over + wage - bills)")

    # Left now
    left_now = money - total_typed
    left_str = f"{left_now:,.2f}"
    lines.append(f"  {'Left now':<34}{left_str:>10}")

    # Usage help
    lines.append("  Add one: run.py add 12.50 Costa    Remove one: run.py remove 1")

    return lines
