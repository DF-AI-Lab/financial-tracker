from typing import List

from fintrack.models import Txn


def parse_pdf(path) -> List[Txn]:
    """Read one bank statement PDF and return its transactions in order.

    Rules (see README.md): ignore cover and terms pages, skip BALANCE BROUGHT/CARRIED
    FORWARD lines, carry the date down to lines without one, join a payment's two
    lines, and decide paid-out vs paid-in (x position of the amount, or balance maths).
    """
    raise NotImplementedError
