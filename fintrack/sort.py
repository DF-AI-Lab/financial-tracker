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

    # Group by (description, detail)
    bill_groups = defaultdict(lambda: {"total": 0.0, "months": set()})

    for txn in bills:
        key = f"{txn.description} - {txn.detail}"
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
