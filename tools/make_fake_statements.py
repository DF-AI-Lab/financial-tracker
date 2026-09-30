"""Make FAKE bank statement PDFs (all names/amounts are invented) plus expected.json.

Run:  python tools/make_fake_statements.py
Writes: tests/data/statement_*.pdf and tests/data/expected.json
The layout copies the real statement style: date shown once per day, a 2-line
payment (payee line + detail line with the amount), separate paid-out / paid-in
columns, balance only after the last payment of a day, brought/carried forward
lines, a cover page and a junk terms page.
"""
import json
from datetime import date
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

OUT = Path(__file__).resolve().parent.parent / "tests" / "data"

# x positions (right edge for money columns)
X_DATE, X_TYPE, X_TEXT = 40, 130, 170
X_OUT, X_IN, X_BAL = 430, 500, 570

# (day, month, type, payee, detail, amount)  amount > 0 = paid out, < 0 = paid in
# Three statement periods: 23 Jul-22 Aug, 23 Aug-22 Sep, 23 Sep-22 Oct (2024)
STATEMENTS = [
    {"file": "statement_2024_08.pdf", "open": 350.00,
     "from": date(2024, 7, 22), "to": date(2024, 8, 22), "txns": [
        (25, 7, "CR", "ACME MOTORS PLC", "PAYROLL", -2410.00),
        (26, 7, ")))", "TACO PLACE", "LEEDS", 12.50),
        (26, 7, ")))", "GREENGROCER 12", "LEEDS", 31.20),
        (29, 7, "BP", "SAM PARKER", "Food and bil", 20.00),
        (1, 8, "DD", "GYM CLUB", "MEMBERSHIP", 50.00),
        (1, 8, "DD", "WATER BOARD", "WATER", 15.75),
        (1, 8, "DD", "TV LICENCE", "LICENCE", 13.25),
        (1, 8, "SO", "SAM PARKER", "RENT", 550.00),
        (2, 8, "DD", "SKY DIGITAL", "SKY", 46.50),
        (2, 8, "DD", "PHONE CO", "MOBILE", 40.11),
        (5, 8, ")))", "PETROL STATION 7", "LEEDS", 45.00),
        (7, 8, "VIS", "STREAM VIDEO", "London", 12.99),
        (9, 8, "ATM", "CASH MACHINE", "LEEDS", 50.00),
        (12, 8, "BP", "SAM PARKER", "Food and bil", 30.00),
        (15, 8, "CR", "PAT LEE", "Sent from Bank", -30.00),
        (20, 8, ")))", "TACO PLACE", "LEEDS", 9.80),
    ]},
    {"file": "statement_2024_09.pdf", "open": None,
     "from": date(2024, 8, 22), "to": date(2024, 9, 22), "txns": [
        (27, 8, ")))", "GREENGROCER 12", "LEEDS", 28.13),
        (27, 8, "VIS", "INT'L 0095911310", "Learn Online +905326253880", 11.99),
        (28, 8, ")))", "PETROL STATION 7", "LEEDS", 25.01),
        (29, 8, "BP", "SAM PARKER", "Food and bil", 20.00),
        (30, 8, "CR", "ACME MOTORS PLC", "PAYROLL", -2388.30),
        (30, 8, ")))", "CHIROPRACTOR", "York", 70.00),
        (31, 8, "BP", "SAM PARKER", "Food and bil", 50.00),
        (1, 9, "DD", "GYM CLUB", "MEMBERSHIP", 50.00),
        (1, 9, "DD", "WATER BOARD", "WATER", 15.75),
        (1, 9, "DD", "TV LICENCE", "LICENCE", 13.25),
        (1, 9, "SO", "SAM PARKER", "RENT", 550.00),
        (2, 9, "DD", "SKY DIGITAL", "SKY", 46.50),
        (2, 9, "DD", "PHONE CO", "MOBILE", 40.11),
        (6, 9, ")))", "TACO PLACE", "LEEDS", 14.20),
        (9, 9, "ATM", "CASH MACHINE", "LEEDS", 40.00),
        (10, 9, "VIS", "STREAM VIDEO", "London", 12.99),
        (13, 9, "BP", "SAM PARKER", "Food and bil", 40.00),
        (16, 9, "VIS", "INT'L 0093267280", "CLOUD HOST aws.example.co", 26.59),
        (18, 9, "VIS", "INT'L 0093267280", "CLOUD HOST aws.example.co", -26.59),
    ]},
    {"file": "statement_2024_10.pdf", "open": None,
     "from": date(2024, 9, 22), "to": date(2024, 10, 22), "txns": [
        (24, 9, ")))", "GREENGROCER 12", "LEEDS", 9.80),
        (24, 9, "BP", "TOOL SHOP Ltd", "tools", 10.00),
        (30, 9, "CR", "ACME MOTORS PLC", "PAYROLL", -2462.62),
        (30, 9, ")))", "FARM SHOP 321", "YORK", 52.44),
        (1, 10, "DD", "GYM CLUB", "MEMBERSHIP", 50.00),
        (1, 10, "DD", "WATER BOARD", "WATER", 15.75),
        (1, 10, "DD", "TV LICENCE", "LICENCE", 13.25),
        (1, 10, "DD", "COUNCIL TAX", "CITY COUNCIL", 161.00),
        (1, 10, "SO", "SAM PARKER", "BILLS", 150.00),
        (1, 10, "SO", "SAM PARKER", "RENT", 550.00),
        (2, 10, "DD", "SKY DIGITAL", "SKY", 46.50),
        (2, 10, "DD", "PHONE CO", "MOBILE", 40.11),
        (2, 10, "BP", "SAM PARKER", "Food and bil", 30.00),
        (2, 10, "VIS", "FURNITURE STORE", "MANCHESTER", 279.00),
        (7, 10, "DD", "ENERGY CO", "ENERGY", 157.12),
        (8, 10, ")))", "TACO PLACE", "LEEDS", 18.90),
        (10, 10, ")))", "PETROL STATION 7", "LEEDS", 61.30),
        (15, 10, "VIS", "STREAM VIDEO", "London", 12.99),
        (21, 10, "VIS", "PRINT SHOP", "www.example.com", 1.49),
    ]},
]

FIRST_OPEN = 350.00


def money(x):
    return f"{x:,.2f}"


def build():
    OUT.mkdir(parents=True, exist_ok=True)
    expected = {"statements": []}
    balance = FIRST_OPEN
    for st in STATEMENTS:
        opening = balance
        txns = []
        # working out balances, per day
        days = []
        for (d, m, typ, payee, detail, amt) in st["txns"]:
            year = 2024
            dt = date(year, m, d)
            if not days or days[-1][0] != dt:
                days.append((dt, []))
            days[-1][1].append((typ, payee, detail, amt))
        for dt, items in days:
            for i, (typ, payee, detail, amt) in enumerate(items):
                balance = round(balance - amt, 2)
                last = i == len(items) - 1
                txns.append({
                    "date": dt.isoformat(), "type": typ, "description": payee,
                    "detail": detail, "amount": -amt,  # negative = paid out
                    "balance": balance if last else None,
                })
        closing = balance
        write_pdf(st, opening, closing, txns)
        expected["statements"].append({
            "file": st["file"], "opening": opening, "closing": closing,
            "transactions": txns,
        })
    (OUT / "expected.json").write_text(json.dumps(expected, indent=2))


def header(c, y):
    c.setFont("Times-Bold", 14)
    c.drawString(X_DATE, y, "Your Bank Account  details")
    c.setFont("Times-BoldItalic", 9)
    c.drawString(X_DATE, y - 20, "Date")
    c.drawString(X_TYPE, y - 20, "Payment type and details")
    c.drawRightString(X_OUT + 20, y - 20, "£ Paid out")
    c.drawRightString(X_IN + 10, y - 20, "£ Paid in")
    c.drawRightString(X_BAL, y - 20, "£ Balance")
    return y - 45


def fmt_date(dt):
    return dt.strftime("%d %b %y")


def write_pdf(st, opening, closing, txns):
    c = canvas.Canvas(str(OUT / st["file"]), pagesize=A4)
    # cover page
    c.setFont("Helvetica-Bold", 30)
    c.drawString(40, 780, "FAKE BANK UK")
    c.setFont("Times-Bold", 11)
    c.drawString(60, 700, f"{st['from'].day + 1} {st['from']:%B} to {st['to']:%d %B %Y}")
    c.setFillColorRGB(0.9, 0.2, 0.1)
    c.setFont("Helvetica", 20)
    c.drawString(400, 690, "Your Statement")
    c.setFillColorRGB(0, 0, 0)
    c.showPage()

    y = header(c, 780)
    c.setFont("Times-Bold", 9)
    c.drawString(X_DATE, y, fmt_date(st["from"]))
    c.drawString(X_TEXT, y, "BALANCE BROUGHT FORWARD")
    c.drawRightString(X_BAL, y, money(opening))
    y -= 16
    last_date = None
    running = opening
    for t in txns:
        if y < 90:
            c.showPage()
            y = header(c, 780)
            c.setFont("Times-Bold", 9)
            c.drawString(X_TEXT, y, "BALANCE BROUGHT FORWARD")
            c.drawRightString(X_BAL, y, money(running))
            y -= 16
            last_date = None
        running = round(running + t["amount"], 2)
        c.setFont("Times-Roman", 9)
        if t["date"] != last_date:
            c.drawString(X_DATE, y, fmt_date(date.fromisoformat(t["date"])))
            last_date = t["date"]
        c.drawString(X_TYPE, y, t["type"])
        c.drawString(X_TEXT, y, t["description"])
        y -= 12
        c.drawString(X_TEXT, y, t["detail"])
        if t["amount"] < 0:
            c.drawRightString(X_OUT, y, money(-t["amount"]))
        else:
            c.drawRightString(X_IN, y, money(t["amount"]))
        if t["balance"] is not None:
            c.drawRightString(X_BAL, y, money(t["balance"]))
        y -= 16
    c.setFont("Times-Bold", 9)
    c.drawString(X_DATE, y, fmt_date(st["to"]))
    c.drawString(X_TEXT, y, "BALANCE CARRIED FORWARD")
    c.drawRightString(X_BAL, y, money(closing))
    c.showPage()

    # junk terms page
    c.setFont("Helvetica-Bold", 11)
    c.drawString(60, 780, "Business Banking Customers")
    c.setFont("Helvetica", 8)
    for i, line in enumerate([
        "Interest and charges: these terms are made up for testing.",
        "Overdrafts: an arranged overdraft lets you spend up to a limit.",
        "Lost and stolen cards: please call the number on your card.",
        "Customer service: lines are open 24 hours. Amount 12.34 is not a payment.",
    ]):
        c.drawString(60, 760 - i * 12, line)
    c.showPage()
    c.save()


if __name__ == "__main__":
    build()
    print("Wrote fake PDFs and expected.json to", OUT)
