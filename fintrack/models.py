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
