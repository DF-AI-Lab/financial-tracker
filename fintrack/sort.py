from typing import Dict, List
from collections import defaultdict

from fintrack.models import Txn


def classify(txns: List[Txn]) -> Dict[str, List[Txn]]:
    """Return {"income": [...], "bills": [...], "random": [...]}.

    income = money in; bills = money out with type DD or SO; random = all other money out.
    """
    result = {"income": [], "bills": [], "random": []}

    for txn in txns:
        if txn.amount > 0:
            result["income"].append(txn)
        elif txn.type in ("DD", "SO"):
            result["bills"].append(txn)
        else:
            result["random"].append(txn)

    return result


def bills_summary(txns: List[Txn]) -> Dict[str, dict]:
    """For each bill return {"months": n, "average": x}.

    Key is "<description> - <detail>", e.g. "GYM CLUB - MEMBERSHIP", or just
    "<description>" when the detail is empty (e.g. "GYM CLUB").
    months = number of distinct calendar months with a payment.
    average = total paid / months, as a positive number rounded to 2 decimals.
    """
    # Classify first to get only bills
    classified = classify(txns)
    bills = classified["bills"]

    # Group by bill_key
    bill_groups = defaultdict(lambda: {"total": 0.0, "months": set()})

    for txn in bills:
        key = bill_key(txn)
        bill_groups[key]["total"] += abs(txn.amount)  # Convert to positive
        bill_groups[key]["months"].add(txn.date.strftime("%Y-%m"))

    # Calculate averages
    result = {}
    for key, data in bill_groups.items():
        num_months = len(data["months"])
        average = round(data["total"] / num_months, 2) if num_months > 0 else 0.0
        result[key] = {"months": num_months, "average": average}

    return result


def monthly_report(txns: List[Txn]) -> Dict[str, dict]:
    """For each calendar month "YYYY-MM" return
    {"income": x, "bills": y, "random": z, "spare": income - bills - random}.
    All values positive numbers rounded to 2 decimals.
    """
    # Classify first
    classified = classify(txns)
    income_txns = classified["income"]
    bills_txns = classified["bills"]
    random_txns = classified["random"]

    # Group by month
    months = defaultdict(lambda: {"income": 0.0, "bills": 0.0, "random": 0.0})

    for txn in income_txns:
        m = txn.date.strftime("%Y-%m")
        months[m]["income"] += txn.amount

    for txn in bills_txns:
        m = txn.date.strftime("%Y-%m")
        months[m]["bills"] += abs(txn.amount)  # Convert to positive

    for txn in random_txns:
        m = txn.date.strftime("%Y-%m")
        months[m]["random"] += abs(txn.amount)  # Convert to positive

    # Calculate spare and round
    result = {}
    for m, data in months.items():
        income = round(data["income"], 2)
        bills = round(data["bills"], 2)
        random = round(data["random"], 2)
        spare = round(income - bills - random, 2)
        result[m] = {
            "income": income,
            "bills": bills,
            "random": random,
            "spare": spare
        }

    return result


def bill_key(t: Txn) -> str:
    """Name a bill is grouped under (used by bills_summary).

    description is upper-cased and stripped; a trailing " LTD", " LIMITED" or " PLC" is
    removed, so "E.ON NEXT LTD" and "E.ON NEXT" are the same bill. The detail is ignored
    when it is empty or "FIRST PAYMENT" (any case); otherwise key = "<description> - <detail>".
    """
    # Upper-case and strip the description
    desc = t.description.strip().upper()

    # Remove trailing " LTD", " LIMITED", or " PLC"
    if desc.endswith(" LTD"):
        desc = desc[:-4].strip()
    elif desc.endswith(" LIMITED"):
        desc = desc[:-8].strip()
    elif desc.endswith(" PLC"):
        desc = desc[:-4].strip()

    # Check if detail should be included
    detail = t.detail.strip().upper()

    # Ignore detail if empty or "FIRST PAYMENT"
    if not detail or detail == "FIRST PAYMENT":
        return desc

    # Otherwise include detail
    return f"{desc} - {t.detail}"


def statement_report(statements) -> List[dict]:
    """One row per Statement (a list of fintrack.models.Statement), sorted by end date:
    {"file", "label", "end", "income", "bills", "random", "spare"}.
    label = end date formatted like "Apr 2024"; end = ISO date string; income/bills/random
    are positive numbers rounded to 2 decimals (same rules as classify); spare =
    income - bills - random. Skip statements whose end is None.
    """
    rows = []

    for st in statements:
        # Skip statements without end date
        if st.end is None:
            continue

        # Classify transactions
        classified = classify(st.txns)

        # Calculate income (sum of positive amounts)
        income = sum(t.amount for t in classified["income"])

        # Calculate bills (sum of absolute negative amounts for DD/SO)
        bills = sum(abs(t.amount) for t in classified["bills"])

        # Calculate random (sum of absolute negative amounts for other)
        random = sum(abs(t.amount) for t in classified["random"])

        # Calculate spare
        spare = income - bills - random

        # Round all values
        income = round(income, 2)
        bills = round(bills, 2)
        random = round(random, 2)
        spare = round(spare, 2)

        # Format label
        label = st.end.strftime("%b %Y")
        end_str = st.end.isoformat()

        rows.append({
            "file": st.file,
            "label": label,
            "end": end_str,
            "income": income,
            "bills": bills,
            "random": random,
            "spare": spare
        })

    # Sort by end date
    rows.sort(key=lambda r: r["end"])

    return rows


def big_items(txns: List[Txn], limit: float = 1000.0) -> List[Txn]:
    """Payments (in or out) whose amount is >= limit in size, sorted by date."""
    result = [t for t in txns if abs(t.amount) >= limit]
    result.sort(key=lambda t: t.date)
    return result
