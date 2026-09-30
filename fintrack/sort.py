from typing import Dict, List

from fintrack.models import Txn


def classify(txns: List[Txn]) -> Dict[str, List[Txn]]:
    """Return {"income": [...], "bills": [...], "random": [...]}.

    income = money in; bills = money out with type DD or SO; random = all other money out.
    """
    raise NotImplementedError


def bills_summary(txns: List[Txn]) -> Dict[str, dict]:
    """For each bill return {"months": n, "average": x}.

    Key is "<description> - <detail>", e.g. "GYM CLUB - MEMBERSHIP".
    months = number of distinct calendar months with a payment.
    average = total paid / months, as a positive number rounded to 2 decimals.
    """
    raise NotImplementedError


def monthly_report(txns: List[Txn]) -> Dict[str, dict]:
    """For each calendar month "YYYY-MM" return
    {"income": x, "bills": y, "random": z, "spare": income - bills - random}.
    All values positive numbers rounded to 2 decimals.
    """
    raise NotImplementedError
