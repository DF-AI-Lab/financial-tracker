"""Drop your statement PDFs in the `statements` folder, then run:  python run.py

Prints bills, monthly report and random spending, and writes CSV files to `output/`.
"""
import csv
from pathlib import Path

from fintrack.parse import parse_pdf
from fintrack.sort import bills_summary, classify, monthly_report

HERE = Path(__file__).parent
IN_DIR = HERE / "statements"
OUT_DIR = HERE / "output"


def main():
    IN_DIR.mkdir(exist_ok=True)
    pdfs = sorted(IN_DIR.glob("*.pdf"))
    if not pdfs:
        print(f"No PDFs found. Drop your statements in: {IN_DIR}")
        return
    txns = []
    for p in pdfs:
        got = parse_pdf(p)
        print(f"Read {p.name}: {len(got)} transactions")
        txns += got
    txns.sort(key=lambda t: t.date)

    OUT_DIR.mkdir(exist_ok=True)
    bills = bills_summary(txns)
    months = monthly_report(txns)
    groups = classify(txns)

    with open(OUT_DIR / "bills.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["bill", "months_seen", "average"])
        for k, v in sorted(bills.items()):
            w.writerow([k, v["months"], f"{v['average']:.2f}"])
    with open(OUT_DIR / "monthly.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["month", "income", "bills", "random", "spare"])
        for m, v in sorted(months.items()):
            w.writerow([m, v["income"], v["bills"], v["random"], v["spare"]])
    with open(OUT_DIR / "random_spending.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date", "type", "description", "detail", "amount"])
        for t in groups["random"]:
            w.writerow([t.date, t.type, t.description, t.detail, f"{-t.amount:.2f}"])

    print("\nBILLS (average per month)")
    for k, v in sorted(bills.items()):
        print(f"  {k:<35} {v['average']:>9.2f}   ({v['months']} months)")
    print("\nMONTH BY MONTH")
    for m, v in sorted(months.items()):
        print(f"  {m}  in {v['income']:>9.2f}  bills {v['bills']:>8.2f}  random {v['random']:>8.2f}  spare {v['spare']:>9.2f}")
    print(f"\nCSV files saved in: {OUT_DIR}")


if __name__ == "__main__":
    main()
