from typing import Optional

from fintrack.models import Analysis


def parse_money(text: str) -> Optional[float]:
    """Turn what the user typed into a number, or None.

    Accepts "2450", "2,450.50", "GBP 2450" and a leading pound sign (£). Spaces are
    ignored. Blank, not a number, zero or negative -> None.
    """
    # Remove spaces
    text = text.replace(" ", "")

    # Remove "GBP" prefix if present
    if text.startswith("GBP"):
        text = text[3:]

    # Remove pound sign if present
    text = text.replace("£", "")

    # Remove commas
    text = text.replace(",", "")

    # Try to parse as float
    if not text:
        return None

    try:
        value = float(text)
    except ValueError:
        return None

    # Return None for zero or negative
    if value <= 0:
        return None

    return value


def what_is_left(wage: float, a: Analysis) -> dict:
    """{"wage", "common", "spare_after_common", "random", "left"}, all rounded to 2 decimals.

    common = a.common_per_cycle; spare_after_common = wage - common; random = a.random_per_cycle;
    left = wage - common - random. Work from the unrounded values, then round each result.
    """
    common = round(a.common_per_cycle, 2)
    spare_after_common = round(wage - a.common_per_cycle, 2)
    random = round(a.random_per_cycle, 2)
    left = round(wage - a.common_per_cycle - a.random_per_cycle, 2)

    return {
        "wage": wage,
        "common": common,
        "spare_after_common": spare_after_common,
        "random": random,
        "left": left
    }


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
    if a.cycles_used == 0:
        return "Not enough finished paydays yet to work out what is left."

    left_data = what_is_left(wage, a)

    # Format money values
    def fmt_money(val: float) -> str:
        return f"{val:,.2f}"

    # Determine singular/plural for cycles
    cycle_word = "cycle" if a.cycles_used == 1 else "cycles"

    lines = [
        f"IF YOUR PAY IS {fmt_money(wage)}",
        f"  Common per cycle          {fmt_money(left_data['common'])}",
        f"  Spare after common        {fmt_money(left_data['spare_after_common'])}",
        f"  Typical random spending   {fmt_money(left_data['random'])}",
        f"  Left after typical month  {fmt_money(left_data['left'])}",
        f"  (based on the last {a.cycles_used} complete {cycle_word})"
    ]

    return "\n".join(lines)
