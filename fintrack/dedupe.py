from typing import List, Tuple

from fintrack.models import Statement


def unique_statements(statements: List[Statement]) -> Tuple[List[Statement], List[Statement]]:
    """Return (kept, skipped).

    Two statements are duplicates when start, end, opening and closing are all equal.
    Keep the first one in the order given; the rest go in `skipped`. Statements whose
    start or end is None are never treated as duplicates.
    """
    kept = []
    skipped = []
    seen = {}

    for st in statements:
        # Skip if start or end is None
        if st.start is None or st.end is None:
            kept.append(st)
            continue

        # Create a key for this statement (start, end, opening, closing)
        key = (st.start, st.end, st.opening, st.closing)

        # Check if we've seen this key before
        if key in seen:
            skipped.append(st)
        else:
            seen[key] = st
            kept.append(st)

    return kept, skipped
