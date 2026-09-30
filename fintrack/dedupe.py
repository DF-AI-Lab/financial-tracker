from typing import List, Tuple

from fintrack.models import Statement


def unique_statements(statements: List[Statement]) -> Tuple[List[Statement], List[Statement]]:
    """Return (kept, skipped).

    Two statements are duplicates when start, end, opening and closing are all equal.
    Keep the first one in the order given; the rest go in `skipped`. Statements whose
    start or end is None are never treated as duplicates.
    """
    raise NotImplementedError
