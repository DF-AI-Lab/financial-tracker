from typing import Optional

from fintrack.models import Analysis


def parse_money(text: str) -> Optional[float]:
    """Turn what the user typed into a number, or None.

    Accepts "2450", "2,450.50", "GBP 2450" and a leading pound sign (£). Spaces are
    ignored. Blank, not a number, zero or negative -> None.
    """
    raise NotImplementedError


def what_is_left(wage: float, a: Analysis) -> dict:
    """{"wage", "common", "spare_after_common", "random", "left"}, all rounded to 2 decimals.

    common = a.common_per_cycle; spare_after_common = wage - common; random = a.random_per_cycle;
    left = wage - common - random. Work from the unrounded values, then round each result.
    """
    raise NotImplementedError


def format_left(wage: float, a: Analysis) -> str:
    """Plain-ASCII text block (lines joined with newlines, money as 1,234.56):

    IF YOUR PAY IS 2,500.00
      Common per cycle          817.16
      Spare after common        1,682.84
      Typical random spending   27.17
      Left after typical month  1,655.68
      (based on the last 6 complete cycles)

    If a.cycles_used == 0 return "Not enough finished paydays yet to work out what is left."
    A "1 complete cycle" / "6 complete cycles" wording uses the singular for 1.
    """
    raise NotImplementedError
