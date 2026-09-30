from typing import List

from fintrack.models import Statement


def check_statement(st: Statement) -> List[str]:
    """Return a list of plain-English problems, or [] if the statement adds up.

    Start at st.opening and add each payment's amount. Whenever a payment has a balance,
    it must match the running total (tolerance 0.005): otherwise add a message that
    names the date and payee. At the end the running total must equal st.closing.
    If opening or closing is None, add a message saying so.
    """
    raise NotImplementedError
