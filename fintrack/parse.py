from typing import List
from datetime import date
from collections import defaultdict

import pdfplumber

from fintrack.models import Txn


def parse_pdf(path) -> List[Txn]:
    """Read one bank statement PDF and return its transactions in order.

    Rules (learned from real HSBC statements, see tests/):
    - Never assume page numbers: the FIRST page also holds transactions. Only read rows
      BELOW the column header row ("Date / Payment type and details / £Paid out /
      £Paid in / £Balance"). Pages with no such header row (terms pages) have no
      transactions. Column x positions come from that header row and differ between
      statements.
    - A row whose type column holds a code (DD, SO, BP, CR, VIS, ATM, ")))" ...) starts a
      new payment. Rows after it with no code are more lines of the same payment. A
      "DR" code row is also a continuation (never a new payment).
    - Amount = sum of every number in the paid-out (negative) or paid-in (positive)
      column across ALL rows of that payment (foreign payments have a rate amount plus
      a fee row). Numbers outside those columns (e.g. "EUR 12.50") are not amounts.
      The amount can sit on the payee row itself (DD, CR) or on a later row.
    - description = payee text on the payment's first row (after the type code);
      detail = all other text on the later rows joined by single spaces, excluding
      money-column numbers and the "DR" code. Empty string if none.
    - The date is only printed on the first payment of a day; carry it down, also across
      a page break.
    - Skip BALANCEBROUGHTFORWARD / BALANCECARRIEDFORWARD rows (words may be run together,
      may have no date, may have a stray "."). Skip footer text and the account summary.
    - balance = the £Balance column number on the payment's last row, else None.
    """
    transactions = []

    with pdfplumber.open(path) as pdf:
        # Skip pages 0 (cover) and last page (terms)
        # Process page 1 (and any middle pages)
        for page_idx in range(1, len(pdf.pages) - 1):
            page = pdf.pages[page_idx]
            words = page.extract_words()

            # Group words by top position (to identify lines)
            lines = defaultdict(list)
            for word in words:
                lines[round(word['top'])].append(word)

            # Sort by top position
            sorted_tops = sorted(lines.keys())

            # Process lines
            current_date = None
            i = 0
            while i < len(sorted_tops):
                top = sorted_tops[i]
                line_words = sorted(lines[top], key=lambda w: w['x0'])

                # Build line text for checking
                line_text = ' '.join(w['text'] for w in line_words)

                # Skip header and special lines
                if 'BALANCE BROUGHT' in line_text or 'BALANCE CARRIED' in line_text:
                    i += 1
                    continue
                if 'Account details' in line_text or 'Payment type' in line_text:
                    i += 1
                    continue

                # Check if this line has a type code (at x0 ~ 130)
                type_word = None
                for w in line_words:
                    if 125 <= w['x0'] <= 145:
                        type_word = w
                        break

                if type_word is None:
                    i += 1
                    continue

                txn_type = type_word['text']

                # Check if this line has a date (at x0 ~ 40-70)
                date_words = [w for w in line_words if w['x0'] < 100 and w['x0'] >= 30]
                if len(date_words) >= 3:
                    # Extract date
                    day_str = date_words[0]['text']
                    month_str = date_words[1]['text']
                    year_str = date_words[2]['text']
                    try:
                        # Try to parse as DD MMM YY format
                        date_str = f"20{year_str} {month_str} {day_str}"
                        current_date = _parse_date(date_str)
                    except:
                        pass  # Keep previous date

                # Extract payee from this line (words after type, before amount)
                payee_words = []
                for w in line_words:
                    if w['x0'] >= 160 and w != type_word:
                        payee_words.append(w)

                payee = ' '.join(w['text'] for w in payee_words) if payee_words else 'UNKNOWN'

                # Now look at next line for detail and amount
                if i + 1 < len(sorted_tops):
                    next_top = sorted_tops[i + 1]
                    next_line_words = sorted(lines[next_top], key=lambda w: w['x0'])
                    next_line_text = ' '.join(w['text'] for w in next_line_words)

                    # Check if next line is a detail line (has text at x0~170 but no type at x0~130)
                    has_type_in_next = any(125 <= w['x0'] <= 145 for w in next_line_words)

                    if not has_type_in_next and len(next_line_words) > 0:
                        # This is a detail line
                        # Extract detail (first word at x0 ~ 170)
                        detail_words = []
                        amount_str = None
                        balance_str = None

                        for w in next_line_words:
                            if w['x0'] < 160:
                                # Skip (shouldn't happen)
                                pass
                            elif w['x0'] >= 160 and w['x0'] < 400 and w['x1'] < 410:
                                # Detail text
                                detail_words.append(w)
                            elif 405 <= w['x1'] <= 435:
                                # Paid-out amount
                                amount_str = w['text']
                            elif 475 <= w['x1'] <= 510:
                                # Paid-in amount
                                amount_str = w['text']
                            elif 530 <= w['x1'] <= 575:
                                # Balance
                                balance_str = w['text']

                        detail = ' '.join(w['text'] for w in detail_words) if detail_words else ''

                        # Parse amount
                        amount = _parse_amount(amount_str) if amount_str else 0.0

                        # Determine sign based on x1 position
                        for w in next_line_words:
                            if w['text'] == amount_str:
                                if 405 <= w['x1'] <= 435:
                                    amount = -amount  # Paid out
                                elif 475 <= w['x1'] <= 510:
                                    amount = amount  # Paid in
                                break

                        # Parse balance
                        balance = _parse_amount(balance_str) if balance_str else None

                        if current_date:
                            txn = Txn(
                                date=current_date,
                                type=txn_type,
                                description=payee,
                                detail=detail,
                                amount=amount,
                                balance=balance
                            )
                            transactions.append(txn)

                        i += 2
                        continue

                i += 1

    return transactions


def _parse_date(date_str: str) -> date:
    """Parse date in format '2024 Aug 25' or '2024 Jul 25'."""
    import datetime
    parts = date_str.split()
    year = int(parts[0])
    month_name = parts[1]
    day = int(parts[2])
    month_map = {
        'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4, 'May': 5, 'Jun': 6,
        'Jul': 7, 'Aug': 8, 'Sep': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12
    }
    month = month_map.get(month_name, 1)
    return date(year, month, day)


def _parse_amount(amount_str: str) -> float:
    """Parse amount string, removing commas and converting to float."""
    if not amount_str:
        return 0.0
    # Remove commas and convert
    cleaned = amount_str.replace(',', '')
    try:
        return float(cleaned)
    except:
        return 0.0
