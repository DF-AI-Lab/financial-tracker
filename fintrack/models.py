from dataclasses import dataclass
from datetime import date
from typing import Optional


@dataclass
class Txn:
    date: date
    type: str            # DD, SO, BP, CR, VIS, ATM or ")))"
    description: str     # the payee line, e.g. "GYM CLUB"
    detail: str          # the second line(s), e.g. "MEMBERSHIP"
    amount: float        # negative = paid out, positive = paid in
    balance: Optional[float] = None  # only set on the last payment of a day


@dataclass
class Statement:
    """One bank statement PDF."""
    file: str                 # file name, e.g. "2024_Apr.PDF"
    start: Optional[date]     # date on the first BALANCE BROUGHT FORWARD row (e.g. 22 Mar 24)
    end: Optional[date]       # date on the last BALANCE CARRIED FORWARD row (e.g. 22 Apr 24)
    opening: Optional[float]  # balance on that first row
    closing: Optional[float]  # balance on that last row
    txns: list                # list[Txn]
