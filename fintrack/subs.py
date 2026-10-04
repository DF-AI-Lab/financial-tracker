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
    {"name", "usual", "since": first_regular_date, "last": last_regular_date, "total": sum_all, "months",
     "last12": paid in the 365 days up to end, "this_year": paid since 1 Jan of end's year}

    - end = latest date of all txns (none -> both lists empty)
    - Look at money-out Txns whose item_key starts with "CARD|"
    - Skip keys whose items answer kind is "oneoff" or "yearly"
    - Group by item_key
    - Per key: skip it when it has more than 1.5 payments per month it was paid in (a shop);
      regular = payments whose exact price comes up at least twice for that payee (prices may change);
      months = number of distinct (year, month) of regular payments
    - Subscription when months >= 3, the median regular price <= 50 and months >= 60% of the months from the first
      to the last one, and the set prices are in 60%+ of the months it was paid in. usual = the latest payment's price.
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

        # A subscription is about one payment a month at a set price (the price may change now and then).
        # "Regular" payments are the ones whose exact price (to the penny) comes up at least twice for this payee.
        all_months = set((t.date.year, t.date.month) for t in txns_list)
        if len(txns_list) > 1.5 * len(all_months):
            continue                                  # several payments a month: a shop, not a subscription
        price_count = {}
        for t in txns_list:
            price_count[round(abs(t.amount), 2)] = price_count.get(round(abs(t.amount), 2), 0) + 1
        regular = [t for t in txns_list if price_count[round(abs(t.amount), 2)] >= 2]
        if not regular:
            continue

        # Count distinct (year, month)
        months_set = set((t.date.year, t.date.month) for t in regular)
        months = len(months_set)

        # Check if subscription: set prices in 3+ months, small, and paid in most (60%+) of the months of its run
        first, latest = min(all_months), max(all_months)
        run_months = (latest[0] - first[0]) * 12 + latest[1] - first[1] + 1
        usual = abs(max(txns_list, key=lambda t: t.date).amount)     # the latest price
        if months < 3 or statistics.median(abs(t.amount) for t in regular) > 50 or len(all_months) < 0.6 * run_months \
                or months < 0.6 * len(all_months):
            continue
        months = len(all_months)

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
        since = min(t.date for t in txns_list)
        last = max(t.date for t in txns_list)

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
            "months": months,
            "last12": sum(abs(t.amount) for t in txns_list if (end - t.date).days < 365),
            "this_year": sum(abs(t.amount) for t in txns_list if t.date.year == end.year)
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
            lines.append(
                f"    {name:<24}{usual:>8.2f} a month   since {since:%b %Y}   "
                f"12 mths {sub['last12']:,.2f}   this year {sub['this_year']:,.2f}"
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
            lines.append(
                f"    {name:<24}{usual:>8.2f} a month   {since:%b %Y} to {last:%b %Y}   "
                f"12 mths {sub['last12']:,.2f}   this year {sub['this_year']:,.2f}"
            )

    return lines
