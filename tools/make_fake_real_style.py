"""Make FAKE statements copying the layout quirks of a real HSBC statement.

All names/amounts are invented. Run:  python tools/make_fake_real_style.py
Writes tests/data/realstyle_*.pdf and tests/data/expected_real_style.json

Quirks copied from the real layout:
- transactions start on the FIRST page, under an account summary block
- columns at different x positions (out ~367, in ~444, balance ~520)
- DD/CR often have the amount on the SAME row as the payee (1 line)
- others have the amount on a 2nd line; foreign payments span many lines and
  have TWO amounts in the paid-out column (rate amount + fee) that add together
- a "DR" line is a continuation of the payment above it, not a new payment
- a page can end mid-day with a dateless BALANCECARRIEDFORWARD row and the next
  page starts with BALANCEBROUGHTFORWARD (no spaces in the words, and a stray ".")
- terms pages have no table at all
"""
import json
from datetime import date
from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

OUT = Path(__file__).resolve().parent.parent / "tests" / "data"
X_DATE, X_TYPE, X_TEXT = 50, 106, 131
R_OUT, R_IN, R_BAL = 367, 444, 520
CAP_FIRST, CAP_NEXT = 28, 34   # table rows per page

OPEN = 120.50
# txn: (day, month, type, payee, single_amount, lines, direction)
#   single_amount: amount printed on the payee row (or None)
#   lines: [(type_col_text, text, amount_or_None)] extra rows
#   direction: "out" or "in"
DAYS = [
    (25, 5, "BP", "SAM PARKER", None, [("", "Food and bil", 6.00)], "out"),
    (25, 5, "VIS", "STREAM AUDIO", None, [("", "stream.co/pymt", 0.99)], "out"),
    (25, 5, "VIS", "STREAM AUDIO", None, [("", "stream.co/pymt", 0.99)], "out"),
    (25, 5, ")))", "MEGA MART", None, [("", "HUNTINGTON", 5.62)], "out"),
    (25, 5, ")))", "DIY STORE 1232", None, [("", "YORK", 17.00)], "out"),
    (27, 5, ")))", "FARM SHOP 321", None, [("", "YORK", 38.87)], "out"),
    (27, 5, "VIS", "INT'L 0078064112", None,
     [("", "Learn Online", None), ("", "+905326253880", 17.99)], "out"),
    (28, 5, "CR", "ACME MOTORS PLC", 2331.43, [], "in"),
    (28, 5, "BP", "SAM PARKER", None, [("", "Food and bil", 50.00)], "out"),
    (2, 6, "DD", "GYM CLUB", 50.00, [], "out"),
    (2, 6, "DD", "WATER BOARD", 15.75, [], "out"),
    (2, 6, "DD", "PHONE CO", 40.11, [], "out"),
    (2, 6, "DD", "SKY DIGITAL", 45.50, [], "out"),
    (2, 6, "DD", "TV LICENCE MBP", 31.80, [], "out"),
    (2, 6, "DD", "CITY COUNCIL GENER", 159.40, [], "out"),
    (2, 6, "SO", "SAM PARKER", None, [("", "BILLS", 150.00)], "out"),
    (2, 6, "SO", "SAM PARKER", None, [("", "RENT", 550.00)], "out"),
    (2, 6, "VIS", "STREAM VIDEO", None, [("", "g.co/helppay#", 12.99)], "out"),
    (2, 6, "VIS", "FURNITURE STORE", None, [("", "MANCHESTER", 279.00)], "out"),
    (3, 6, "SO", "SAM PARKER", None, [("", "FOOD", 200.00)], "out"),
    (5, 6, "DD", "ENERGY CO", None, [("", "FIRST PAYMENT", 162.45)], "out"),
    (5, 6, "SO", "PAT LEE", None, [("", "CAR LOAN PAYMENT", 250.00)], "out"),
    (8, 6, "VIS", "INT'L 0052056981", None,
     [("", "MONOKAI", None), ("", "AMSTERDAM", None), ("", "EUR 12.50 @ 1.1649", None),
      ("", "Visa Rate", 10.73), ("DR", "Non-Sterling", None), ("", "Transaction Fee", 0.29)], "out"),
    (10, 6, ")))", "CHIROPRACTOR", None, [("", "York", 70.00)], "out"),
    (12, 6, "CR", "PAT LEE", None, [("", "Sent from Bank", 30.00)], "in"),
    (15, 6, "ATM", "CASH NOTEMAC JUN15", None, [("", "Notemachine @19:57", 30.00)], "out"),
    (18, 6, "VIS", "PRINT SHOP", None, [("", "www.example.com", 3.99)], "out"),
]
# add three extra months of recurring bills so bills_summary has history? (kept to one month here)


def money(x):
    return f"{x:,.2f}"


def txn_rows(t):
    _, _, typ, payee, single, lines, direction = t
    return 1 + len(lines)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    balance = OPEN
    expected_txns = []
    # pass 1: values
    days = []
    for t in DAYS:
        d = date(2024, t[1], t[0])
        if not days or days[-1][0] != d:
            days.append((d, []))
        days[-1][1].append(t)
    for d, items in days:
        for i, t in enumerate(items):
            _, _, typ, payee, single, lines, direction = t
            amts = ([single] if single is not None else []) + [a for (_, _, a) in lines if a is not None]
            total = round(sum(amts), 2)
            signed = -total if direction == "out" else total
            balance = round(balance + signed, 2)
            detail = " ".join(text for (_, text, _) in lines)
            expected_txns.append({
                "date": d.isoformat(), "type": typ, "description": payee,
                "detail": detail, "amount": signed,
                "balance": balance if i == len(items) - 1 else None,
            })
    closing = balance
    write_pdf(OPEN, closing, days)
    (OUT / "expected_real_style.json").write_text(json.dumps({"statements": [{
        "file": "realstyle_2024_06.pdf", "opening": OPEN, "closing": closing,
        "transactions": expected_txns}]}, indent=2))


def table_header(c, y):
    c.setFont("Helvetica-Bold", 9)
    c.drawString(X_DATE, y, "Your Bank Account details")
    y -= 14
    c.setFont("Helvetica", 7)
    c.drawString(X_DATE, y, "Date")
    c.drawString(110, y, "Payment type and details")
    c.drawRightString(365, y, "£Paid out")
    c.drawRightString(443, y, "£Paid in")
    c.drawRightString(517, y, "£Balance")
    return y - 14


def write_pdf(opening, closing, days):
    c = canvas.Canvas(str(OUT / "realstyle_2024_06.pdf"), pagesize=letter)
    H = 792
    c.setFont("Helvetica", 8)
    for i, s in enumerate(["Contact tel 00000 000 000", "see reverse for call times",
                           "www.example-bank.test", "Your Statement", "Mr A Sample",
                           "1 Example Street", "Sampletown", "AB1 2CD"]):
        c.drawString(50, H - 50 - i * 11, s)
    c.drawString(300, H - 150, "Account Summary")
    for i, s in enumerate([f"OpeningBalance £{money(opening)}", "Payments In £2,361.43",
                           "Payments Out £2,500.00", f"ClosingBalance £{money(closing)}"]):
        c.drawString(300, H - 165 - i * 11, s)
    c.drawString(50, H - 200, "23 May to 22 June 2024")
    c.drawString(50, H - 214, "Account Name Sortcode Account Number Sheet Number")
    c.drawString(50, H - 225, "Mr A Sample 00-00-00 00000000 101")
    y = table_header(c, H - 260)

    def row_y(y):
        return y - 11

    c.setFont("Times-Roman", 8)
    c.drawString(X_DATE, y, "22 May 24")
    c.drawString(X_TEXT, y, "BALANCEBROUGHTFORWARD")
    c.drawString(295, y, ".")
    c.drawRightString(R_BAL, y, money(opening))
    y = row_y(y)
    used, cap, running, last_date = 1, CAP_FIRST, opening, None

    def new_page(carried):
        nonlocal y, used, cap
        c.setFont("Times-Roman", 8)
        c.drawString(X_TEXT, y, "BALANCECARRIEDFORWARD")
        c.drawRightString(R_BAL, y, money(carried))
        c.showPage()
        c.setFont("Helvetica", 7)
        c.drawString(50, H - 60, "23 May to 22 June 2024")
        c.drawString(50, H - 72, "Your Statement")
        c.drawString(50, H - 84, "Mr A Sample 00-00-00 00000000 102")
        y = table_header(c, H - 130)
        c.setFont("Times-Roman", 8)
        c.drawString(X_TEXT, y, "BALANCEBROUGHTFORWARD")
        c.drawRightString(R_BAL, y, money(carried))
        y = row_y(y)
        used, cap = 1, CAP_NEXT

    for d, items in days:
        for i, t in enumerate(items):
            _, _, typ, payee, single, lines, direction = t
            if used + txn_rows(t) > cap:
                new_page(running)
                # date NOT repeated after a page break, real statements carry it down
                first_in_day_shown = True
            else:
                first_in_day_shown = False
            col = R_OUT if direction == "out" else R_IN
            c.setFont("Times-Roman", 8)
            if i == 0 and not first_in_day_shown:
                c.drawString(X_DATE, y, d.strftime("%d %b %y"))
            c.drawString(X_TYPE, y, typ)
            c.drawString(X_TEXT, y, payee)
            if single is not None:
                c.drawRightString(col, y, money(single))
            for (tc, text, amt) in lines:
                y = row_y(y)
                if tc:
                    c.drawString(X_TYPE, y, tc)
                c.drawString(X_TEXT, y, text)
                if amt is not None:
                    c.drawRightString(col, y, money(amt))
            amts = ([single] if single is not None else []) + [a for (_, _, a) in lines if a is not None]
            tot = round(sum(amts), 2)
            running = round(running + (-tot if direction == "out" else tot), 2)
            if i == len(items) - 1:
                c.drawRightString(R_BAL, y, money(running))
            y = row_y(y)
            used += txn_rows(t)
    c.drawString(X_DATE, y, "22 Jun 24")
    c.drawString(X_TEXT, y, "BALANCECARRIEDFORWARD")
    c.drawRightString(R_BAL, y, money(closing))
    c.setFont("Helvetica", 7)
    c.drawString(50, 40, "Customer Service Centre . BX8 1HB")
    c.showPage()
    # terms page, no table
    c.setFont("Helvetica", 8)
    c.drawString(50, H - 60, "Information about the Compensation Scheme")
    c.drawString(50, H - 75, "Credit interest rates: upto 25 0.00%  over 25 39.90%  balance 1,000.00")
    c.showPage()
    c.save()


if __name__ == "__main__":
    main()
    print("Wrote real-style fake PDF and expected_real_style.json")
