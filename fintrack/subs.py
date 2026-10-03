"""Subscription spotter: small card payments most months (Oct 2026)."""
import statistics
from datetime import date
from typing import List, Optional, Dict

from fintrack.models import Txn
from fintrack.store import item_key


def find_subscriptions(txns: List[Txn], items: Optional[Dict] = None) -> Dict:
    """Find recurring card payments that look like subscriptions.

    Args:
        txns: list of transactions, sorted by date
        items: dict from fintrack.store.get_items: {key: {"kind": str, "label": str, ...}}

    Returns dict with "active" and "stopped" lists. Each entry:
    {"name", "usual", "since": first_regular_date, "last": last_regular_date, "total": sum_all, "months"}

    - end = latest date of all txns (none -> both lists empty)
    - Look at money-out Txns whose item_key starts with "CARD|"
    - Skip keys whose items answer kind is "oneoff" or "yearly"
    - Group by item_key
    - Per key: usual = median of amounts; regular = payments within 15% of usual
    - months = number of distinct (year, month) of regular payments
    - Subscription when months >= 3 and usual <= 50
    - active when (end - last).days <= 45, else stopped
    """
    if items is None:
        items = {}

    # Find end date (latest date of all txns)
    if not txns:
        return {"active": [], "stopped": []}

    end = max(t.date for t in txns)

    # Filter to money-out card transactions
    card_txns = []
    for t in txns:
        if t.amount >= 0:  # Money in, skip
            continue

        key = item_key(t)
        if not key.startswith("CARD|"):  # Not a card transaction, skip
            continue

        # Check if kind is oneoff or yearly
        if key in items:
            if items[key]["kind"] in ("oneoff", "yearly"):
                continue

        card_txns.append((key, t))

    # Group by item_key
    groups = {}
    for key, txn in card_txns:
        if key not in groups:
            groups[key] = []
        groups[key].append(txn)

    # Analyze each group
    subscriptions = []

    for key, txns_list in groups.items():
        # Get amounts (positive)
        amounts = [abs(t.amount) for t in txns_list]

        # Calculate usual as median
        usual = statistics.median(amounts)

        # Find regular payments (within 15% of usual)
        regular = [t for t in txns_list if abs(abs(t.amount) - usual) <= usual * 0.15]

        if not regular:
            continue

        # Count distinct (year, month)
        months_set = set((t.date.year, t.date.month) for t in regular)
        months = len(months_set)

        # Check if subscription
        if months < 3 or usual > 50:
            continue

        # Get name from items label or key's NAME part
        if key in items and items[key].get("label"):
            name = items[key]["label"]
        else:
            # Extract NAME part (text between 1st and 2nd "|")
            parts = key.split("|")
            if len(parts) >= 2:
                name = " ".join(w.capitalize() for w in parts[1].split())
            else:
                name = key

        # Get first and last regular date
        since = min(t.date for t in regular)
        last = max(t.date for t in regular)

        # Calculate total of all payments (positive)
        total = sum(abs(t.amount) for t in txns_list)

        # Determine if active or stopped
        days_since_last = (end - last).days
        is_active = days_since_last <= 45

        subscription = {
            "name": name,
            "usual": usual,
            "since": since,
            "last": last,
            "total": total,
            "months": months
        }

        if is_active:
            subscriptions.append(("active", subscription))
        else:
            subscriptions.append(("stopped", subscription))

    # Sort actives by usual biggest first (ties: name)
    active = [s[1] for s in subscriptions if s[0] == "active"]
    active.sort(key=lambda x: (-x["usual"], x["name"]))

    # Sort stopped by last newest first (ties: name)
    stopped = [s[1] for s in subscriptions if s[0] == "stopped"]
    stopped.sort(key=lambda x: (-x["last"].toordinal(), x["name"]))

    return {"active": active, "stopped": stopped}


def format_subscriptions(s: Dict) -> List[str]:
    """Format subscriptions as lines.

    s: dict from find_subscriptions with "active" and "stopped" lists.

    Returns list of strings.
    """
    active = s.get("active", [])
    stopped = s.get("stopped", [])

    if not active and not stopped:
        return ["SUBSCRIPTIONS: none found."]

    lines = ["SUBSCRIPTIONS (card payments most months)"]

    # Active section
    if active:
        lines.append("  Still paying:")
        active_total = 0.0
        for sub in active:
            name = sub["name"]
            usual = sub["usual"]
            since = sub["since"]
            total = sub["total"]
            lines.append(
                f"    {name:<24}{usual:>8.2f} a month   since {since:%b %Y}   paid {total:,.2f} so far"
            )
            active_total += usual

        lines.append(f"    {'Total':<24}{active_total:>8.2f} a month")

    # Stopped section
    if stopped:
        lines.append("  Stopped:")
        for sub in stopped:
            name = sub["name"]
            usual = sub["usual"]
            since = sub["since"]
            last = sub["last"]
            total = sub["total"]
            lines.append(
                f"    {name:<24}{usual:>8.2f} a month   {since:%b %Y} to {last:%b %Y}   paid {total:,.2f}"
            )

    return lines
