from typing import List
from datetime import date
from collections import defaultdict
from pathlib import Path

import pdfplumber

from fintrack.models import Txn, Statement


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
        current_date = None
        paid_out_x1 = None  # Right edge of paid-out column
        paid_in_x1 = None   # Right edge of paid-in column
        balance_x1 = None   # Right edge of balance column
        type_col_x0 = None  # Left edge of type column

        for page_idx in range(len(pdf.pages)):
            page = pdf.pages[page_idx]
            words = page.extract_words()

            # Group words by top position (to identify lines)
            lines = defaultdict(list)
            for word in words:
                lines[round(word['top'])].append(word)

            # Sort by top position
            sorted_tops = sorted(lines.keys())

            # First, find the header row on this page
            page_has_header = False
            header_top_idx = None
            for idx, top in enumerate(sorted_tops):
                line_words = lines[top]
                line_text = ' '.join(w['text'] for w in line_words)
                if 'Balance' in line_text and 'Payment' in line_text:
                    page_has_header = True
                    header_top_idx = idx
                    # Extract column positions from header row
                    for w in line_words:
                        if w['text'] == 'Balance':
                            balance_x1 = w['x1']
                        elif w['text'] == 'out':
                            paid_out_x1 = w['x1']
                        elif w['text'] == 'in':
                            paid_in_x1 = w['x1']
                        elif w['text'] == 'Payment':
                            type_col_x0 = w['x0']
                    break

            # If no header found, skip this page
            if not page_has_header:
                continue

            # Process transaction rows (those below the header)
            # Use extracted positions, with fallbacks for different PDF layouts
            type_col_x0_actual = type_col_x0 if type_col_x0 else 110
            paid_out_x1_actual = paid_out_x1 if paid_out_x1 else 353.3
            paid_in_x1_actual = paid_in_x1 if paid_in_x1 else 435.6
            balance_x1_actual = balance_x1 if balance_x1 else 517.0

            # Type column range is around the Payment header position
            type_col_min = type_col_x0_actual - 20
            type_col_max = type_col_x0_actual + 20

            i = header_top_idx + 1
            while i < len(sorted_tops):
                top = sorted_tops[i]
                line_words = sorted(lines[top], key=lambda w: w['x0'])
                line_text = ' '.join(w['text'] for w in line_words)

                # Skip special lines
                if _is_balance_line(line_text):
                    i += 1
                    continue
                if 'Customer Service Centre' in line_text:
                    i += 1
                    continue

                # Check if this line has a type code
                type_word = None
                for w in line_words:
                    if type_col_min <= w['x0'] <= type_col_max:
                        type_word = w
                        break

                # If no type code, skip this line (shouldn't happen in well-formed data)
                if type_word is None:
                    i += 1
                    continue

                txn_type = type_word['text']

                # Check if this line has a date
                date_words = [w for w in line_words if w['x0'] < 100 and w['x0'] >= 30]
                if len(date_words) >= 3:
                    day_str = date_words[0]['text']
                    month_str = date_words[1]['text']
                    year_str = date_words[2]['text']
                    try:
                        date_str = f"20{year_str} {month_str} {day_str}"
                        current_date = _parse_date(date_str)
                    except:
                        pass  # Keep previous date

                # Extract payee/description (text after type code, before amount columns)
                # Payee starts after type column and is not in the amount columns
                payee_start = type_col_x0_actual + 20
                payee_words = []
                for w in line_words:
                    # Skip if in amount columns
                    if _is_in_amount_column(w['x1'], paid_out_x1_actual, paid_in_x1_actual, balance_x1_actual):
                        continue
                    if w['x0'] > payee_start and w['x0'] < 400:
                        payee_words.append(w)

                description = ' '.join(w['text'] for w in payee_words) if payee_words else ''

                # Collect all amounts and detail from this and following rows
                payment_rows = [line_words]
                detail_parts = []

                # Look ahead for continuation rows
                j = i + 1
                while j < len(sorted_tops):
                    next_top = sorted_tops[j]
                    next_line_words = sorted(lines[next_top], key=lambda w: w['x0'])
                    next_line_text = ' '.join(w['text'] for w in next_line_words)

                    # Skip balance lines
                    if _is_balance_line(next_line_text):
                        j += 1
                        continue

                    # Check if this line has a type code
                    next_type_word = None
                    for w in next_line_words:
                        if type_col_min <= w['x0'] <= type_col_max:
                            next_type_word = w
                            break

                    # If it has a type code and it's not 'DR', it's a new transaction
                    if next_type_word and next_type_word['text'] != 'DR':
                        break

                    # This is a continuation row - collect detail and amounts
                    payment_rows.append(next_line_words)

                    # Extract detail text (text between type col and amount columns)
                    # Amount columns are at x1 positions of the detected column edges
                    for w in next_line_words:
                        # Skip if in amount columns
                        if _is_in_amount_column(w['x1'], paid_out_x1_actual, paid_in_x1_actual, balance_x1_actual):
                            continue
                        # Include text in detail area (after type col, before amount cols)
                        detail_start = type_col_x0_actual + 20
                        if w['x0'] > detail_start and w['x0'] < 350:
                            detail_parts.append(w['text'])

                    j += 1

                # Now sum amounts from all rows of this payment
                total_amount = 0.0
                last_balance = None

                for row_words in payment_rows:
                    for w in row_words:
                        if _looks_like_currency(w['text']):
                            amount_val = _parse_amount(w['text'])
                            # Classify by proximity to column edges
                            dist_to_out = abs(w['x1'] - paid_out_x1_actual)
                            dist_to_in = abs(w['x1'] - paid_in_x1_actual)
                            dist_to_bal = abs(w['x1'] - balance_x1_actual)

                            min_dist = min(dist_to_out, dist_to_in, dist_to_bal)

                            if min_dist > 50:
                                # Not close to any column
                                continue

                            if dist_to_out == min_dist:
                                # Paid out
                                total_amount -= amount_val
                            elif dist_to_in == min_dist:
                                # Paid in
                                total_amount += amount_val
                            elif dist_to_bal == min_dist:
                                # Balance - save this
                                last_balance = amount_val

                # Create transaction
                if current_date:
                    detail = ' '.join(detail_parts)
                    txn = Txn(
                        date=current_date,
                        type=txn_type,
                        description=description,
                        detail=detail,
                        amount=round(total_amount, 2),
                        balance=last_balance
                    )
                    transactions.append(txn)

                # Move to next transaction
                i = j if j > i + 1 else i + 1

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


def _is_balance_line(text: str) -> bool:
    """Check if a line is a balance brought/carried line."""
    text_upper = text.upper().replace(' ', '')
    return 'BALANCEBROUGHTFORWARD' in text_upper or 'BALANCECARRIEDFORWARD' in text_upper


def _looks_like_currency(text: str) -> bool:
    """Check if text looks like a currency amount."""
    text = text.strip()
    # Remove common currency symbols and separators
    cleaned = text.replace('£', '').replace(',', '').replace('@', '')
    try:
        float(cleaned)
        return True
    except ValueError:
        return False


def _is_in_amount_column(x1: float, paid_out_x1: float, paid_in_x1: float, balance_x1: float) -> bool:
    """Check if x1 position is close to any of the amount columns."""
    dist_to_out = abs(x1 - paid_out_x1)
    dist_to_in = abs(x1 - paid_in_x1)
    dist_to_bal = abs(x1 - balance_x1)

    min_dist = min(dist_to_out, dist_to_in, dist_to_bal)
    return min_dist < 50


def parse_statement(path):
    """Like parse_pdf but returns a fintrack.models.Statement.

    file = the file NAME only (not the folder). start/opening come from the first
    BALANCEBROUGHTFORWARD row that has a date, end/closing from the last
    BALANCECARRIEDFORWARD row that has a date. Use None for anything not found.
    txns = the same list parse_pdf returns.
    """
    # Get the file name only (not the full path)
    if isinstance(path, str):
        path = Path(path)
    file_name = path.name

    # Get transactions from parse_pdf
    txns = parse_pdf(path)

    # Extract balance information
    start = None
    opening = None
    end = None
    closing = None

    with pdfplumber.open(path) as pdf:
        for page_idx in range(len(pdf.pages)):
            page = pdf.pages[page_idx]
            words = page.extract_words()

            # Group words by top position (to identify lines)
            lines = defaultdict(list)
            for word in words:
                lines[round(word['top'])].append(word)

            # Sort by top position
            sorted_tops = sorted(lines.keys())

            for idx, top in enumerate(sorted_tops):
                line_words = lines[top]
                line_text = ' '.join(w['text'] for w in line_words)

                # Look for BALANCE BROUGHT FORWARD (first occurrence with date)
                if 'BALANCE' in line_text.upper() and 'BROUGHT' in line_text.upper() and start is None:
                    # Extract date from this line
                    date_parts = []
                    for w in line_words:
                        if len(date_parts) < 3 and w['text'] in ('Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                                                                   'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
                                                                   '01', '02', '03', '04', '05', '06', '07', '08', '09',
                                                                   '10', '11', '12', '13', '14', '15', '16', '17', '18', '19',
                                                                   '20', '21', '22', '23', '24', '25', '26', '27', '28', '29', '30', '31',
                                                                   '24', '23', '22', '21', '20', '19'):
                            date_parts.append(w['text'])

                    # Try to parse the date from the line
                    words_in_line = [w['text'] for w in line_words]
                    for i, word in enumerate(words_in_line):
                        if word.isdigit() and len(word) == 2 and 1 <= int(word) <= 31:
                            # Potential day
                            if i + 1 < len(words_in_line):
                                month_str = words_in_line[i + 1]
                                if month_str in ('Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                                                'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'):
                                    if i + 2 < len(words_in_line):
                                        year_str = words_in_line[i + 2]
                                        if year_str.isdigit() and len(year_str) == 2:
                                            try:
                                                date_str = f"20{year_str} {month_str} {word}"
                                                start = _parse_date(date_str)
                                                break
                                            except:
                                                pass

                    # Extract the opening balance (the last number in the line that looks like currency)
                    for w in reversed(line_words):
                        if _looks_like_currency(w['text']):
                            opening = _parse_amount(w['text'])
                            break

                # Look for BALANCE CARRIED FORWARD (keep updating to get the last one)
                if 'BALANCE' in line_text.upper() and 'CARRIED' in line_text.upper():
                    # Extract date from this line
                    words_in_line = [w['text'] for w in line_words]
                    for i, word in enumerate(words_in_line):
                        if word.isdigit() and len(word) == 2 and 1 <= int(word) <= 31:
                            # Potential day
                            if i + 1 < len(words_in_line):
                                month_str = words_in_line[i + 1]
                                if month_str in ('Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                                                'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'):
                                    if i + 2 < len(words_in_line):
                                        year_str = words_in_line[i + 2]
                                        if year_str.isdigit() and len(year_str) == 2:
                                            try:
                                                date_str = f"20{year_str} {month_str} {word}"
                                                end = _parse_date(date_str)
                                                break
                                            except:
                                                pass

                    # Extract the closing balance (the last number in the line that looks like currency)
                    for w in reversed(line_words):
                        if _looks_like_currency(w['text']):
                            closing = _parse_amount(w['text'])
                            break

    return Statement(file=file_name, start=start, end=end, opening=opening, closing=closing, txns=txns)
