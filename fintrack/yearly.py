"""Detect annual bills that may be due for payment."""
from datetime import date
from typing import List, Dict

from fintrack.models import Txn
from fintrack.store import item_key


def yearly_due(txns: List[Txn], items: dict, today: date) -> List[dict]:
    """Find yearly bills that are due (11-13 months since last payment).

    txns: list of transactions.
    items: dict from fintrack.store.get_items: {key: {"kind": "yearly" or other, "label": str, ...}}.
    today: reference date for calculating months since last payment.

    Returns a list of dicts, one per yearly item that is due, sorted by paid date (oldest first):
    {"key": key, "label": label, "amount": positive amount, "paid": date}.

    For each key in items where kind is "yearly":
    - Find all money-OUT payments (amount < 0) where fintrack.store.item_key(t) == key.
    - Take the LATEST one by date. Skip if there are no payments.
    - Calculate months = (today.year*12 + today.month) - (paid.year*12 + paid.month).
    - Include if 11 <= months <= 13.
    - label = the saved label if non-empty, else the NAME part of the key (text between 1st and 2nd "|").
    - amount = the latest payment as a positive number.
    """
    due_list = []

    for key, item_info in items.items():
        if item_info.get("kind") != "yearly":
            continue

        # Find all payments for this key that are money OUT (amount < 0)
        matching_txns = [t for t in txns if t.amount < 0 and item_key(t) == key]

        if not matching_txns:
            # Skip items with no payments
            continue

        # Find the latest payment by date
        latest_txn = max(matching_txns, key=lambda t: t.date)

        # Calculate months since the latest payment
        today_months = today.year * 12 + today.month
        paid_months = latest_txn.date.year * 12 + latest_txn.date.month
        months = today_months - paid_months

        # Check if it's in the due window (11-13 months)
        if 11 <= months <= 13:
            # Determine label: use saved label if non-empty, else extract NAME part from key
            label = item_info.get("label", "")
            if not label:
                # Extract NAME from key (text between 1st and 2nd "|")
                parts = key.split("|")
                if len(parts) >= 2:
                    label = parts[1]
                else:
                    label = key

            due_list.append({
                "key": key,
                "label": label,
                "amount": abs(latest_txn.amount),
                "paid": latest_txn.date
            })

    # Sort by paid date (oldest first)
    due_list.sort(key=lambda d: d["paid"])

    return due_list


def yearly_lines(due: List[dict]) -> List[str]:
    """Format yearly due items as warning lines.

    due: list of dicts from yearly_due.

    Returns a list of strings, one per item:
    "WARNING Possible yearly bill: {label} {amount:.2f}, paid {date:%b %Y}"
    """
    lines = []
    for item in due:
        line = f"WARNING Possible yearly bill: {item['label']} {item['amount']:.2f}, paid {item['paid']:%b %Y}"
        lines.append(line)
    return lines
