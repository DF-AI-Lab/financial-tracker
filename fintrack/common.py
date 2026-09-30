from typing import List

from fintrack.models import Analysis, Cycle, Txn


def payee_key(t: Txn) -> str:
    """Name a payment is grouped under when looking for common payments.

    - DD and SO payments: use fintrack.sort.bill_key(t).
    - Everything else: the description upper-cased; but if it starts with "INT'L" (foreign
      card payments) use the detail instead. Remove every run of digits, remove a trailing
      " LTD", " LIMITED" or " PLC", collapse repeated spaces, strip.
      e.g. "CORNER SHOP 12" -> "CORNER SHOP".
    """
    raise NotImplementedError


def analyse(cycles: List[Cycle], window: int = 6, min_cycles: int = 4, tolerance: float = 0.15,
            oneoff_limit: float = 1000.0) -> Analysis:
    """Work out which spending is COMMON, which is a ONE-OFF and which is RANDOM.

    - Use only cycles with complete=True, and only the last `window` of them.
      cycles_used = how many that is (0 -> Analysis(0, {}, 0.0, 0.0, [])).
    - needed = min(min_cycles, cycles_used).
    - Only money OUT counts (amount < 0). Wage and other money in are ignored.
    - Group payments by payee_key. For each key, its total per cycle = sum of the amounts
      paid out in that cycle (as a positive number).
    - A key is COMMON when
        * any payment of it is type DD or SO ("bill"): it appears in >= needed cycles of
          the window, whatever the amounts; or
        * otherwise ("other"): at least `needed` of the window's cycles have a total within
          `tolerance` (a fraction, 0.15 = 15%) of the MEDIAN of that key's per-cycle totals.
    - If a key is common, ALL its payments in the window are common.
    - A payment that is not common and whose size is >= oneoff_limit is a ONE-OFF
      (collected in Analysis.one_offs, in date order) and is left out of every average.
    - Every other payment is RANDOM.
    - common[key] = {"cycles": number of window cycles the key appears in, "total": its total
      over the window, "average": total / cycles_used, "kind": "bill" or "other"}.
    - common_per_cycle = sum of common totals / cycles_used;
      random_per_cycle = sum of random payments / cycles_used. Round nothing (tests use approx).
    """
    raise NotImplementedError
