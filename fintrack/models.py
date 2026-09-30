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


@dataclass
class Cycle:
    """One payday-to-payday period (from one wage arriving to the day before the next)."""
    start: date        # date of the wage payment that opens the cycle
    end: date          # complete cycle: day before the next wage; last cycle: date of its last payment
    wage: float        # sum of the wage credits in this cycle
    txns: list         # list[Txn]: every payment dated in the cycle, including the wage credit(s)
    complete: bool     # False for the last cycle (the next wage has not arrived yet)

    @property
    def label(self) -> str:
        return self.start.strftime("%d %b %Y")
