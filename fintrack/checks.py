from typing import List

from fintrack.models import Statement


def check_statement(st: Statement) -> List[str]:
    """Return a list of plain-English problems, or [] if the statement adds up.

    Start at st.opening and add each payment's amount. Whenever a payment has a balance,
    it must match the running total (tolerance 0.005): otherwise add a message that
    names the date and payee. At the end the running total must equal st.closing.
    If opening or closing is None, add a message saying so.
    """
    problems = []

    # Check for missing opening/closing
    if st.opening is None:
        problems.append("Missing opening balance")
    if st.closing is None:
        problems.append("Missing closing balance")

    # If we can't do the math, return what we have
    if st.opening is None or st.closing is None:
        return problems

    # Start at opening balance and add each payment
    running = st.opening
    for txn in st.txns:
        running = round(running + txn.amount, 2)

        # If the transaction has a balance recorded, check if it matches
        if txn.balance is not None:
            if abs(round(txn.balance, 2) - running) > 0.005:
                problems.append(f"{txn.date.strftime('%d %b')} {txn.description}: balance mismatch (expected {running:.2f}, got {txn.balance:.2f})")

    # Check if final balance matches closing
    if abs(running - st.closing) > 0.005:
        problems.append(f"Final balance mismatch: expected {st.closing:.2f}, got {running:.2f}")

    return problems
