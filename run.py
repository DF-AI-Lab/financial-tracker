"""Drop your statement PDFs in the `statements` folder, then run:  python run.py

Prints bills, monthly report and random spending, and writes CSV files to `output/`.
"""
import csv
from pathlib import Path

from fintrack.parse import parse_statement
from fintrack.checks import check_statement
from fintrack.dedupe import unique_statements
from fintrack.sort import bills_summary, classify, statement_report, big_items

HERE = Path(__file__).parent
IN_DIR = HERE / "statements"
OUT_DIR = HERE / "output"


def main(in_dir=IN_DIR, out_dir=OUT_DIR):
    in_dir = Path(in_dir)
    out_dir = Path(out_dir)

    in_dir.mkdir(exist_ok=True)
    pdfs = sorted(in_dir.glob("*.pdf")) + sorted(in_dir.glob("*.PDF"))
    pdfs = list(set(pdfs))  # Remove duplicates from case-insensitive globbing
    pdfs = sorted(pdfs, key=lambda p: p.name)

    if not pdfs:
        print(f"No PDFs found. Drop your statements in: {in_dir}")
        return

    # Parse all statements
    statements = []
    for p in pdfs:
        st = parse_statement(p)
        statements.append(st)

        # Check statement
        problems = check_statement(st)
        if problems:
            print(f"Read {p.name}: {len(st.txns)} payments  CHECK")
            for problem in problems:
                print(f"  {problem}")
        else:
            print(f"Read {p.name}: {len(st.txns)} payments  OK")

    # Find unique statements and skip duplicates
    kept, skipped = unique_statements(statements)
    for st in skipped:
        # Find which statement it's a duplicate of
        for kept_st in kept:
            if (st.start == kept_st.start and st.end == kept_st.end and
                st.opening == kept_st.opening and st.closing == kept_st.closing):
                print(f"Skipped duplicate: {st.file} (same period as {kept_st.file})")
                break

    # Get all transactions from kept statements
    all_txns = []
    for st in kept:
        all_txns.extend(st.txns)
    all_txns.sort(key=lambda t: t.date)

    # Generate reports
    out_dir.mkdir(exist_ok=True)

    # Statement by statement report
    print("\nSTATEMENT BY STATEMENT")
    rows = statement_report(kept)
    for row in rows:
        print(f"  {row['label']:<12} income {row['income']:>9.2f}  bills {row['bills']:>8.2f}  random {row['random']:>8.2f}  spare {row['spare']:>9.2f}")

    # Bills summary (average per month)
    bills = bills_summary(all_txns)
    print("\nBILLS (average per month)")
    for k, v in sorted(bills.items()):
        print(f"  {k:<35} {v['average']:>9.2f}   ({v['months']} months)")

    # Big items
    big = big_items(all_txns)
    print("\nBIG ITEMS")
    for t in big:
        print(f"  {t.date.isoformat()} {t.description:<30} {t.amount:>9.2f}")

    # Write CSV files
    with open(out_dir / "statements.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["file", "label", "end", "income", "bills", "random", "spare"])
        for row in rows:
            w.writerow([row["file"], row["label"], row["end"], row["income"], row["bills"], row["random"], row["spare"]])

    with open(out_dir / "bills.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["bill", "months_seen", "average"])
        for k, v in sorted(bills.items()):
            w.writerow([k, v["months"], f"{v['average']:.2f}"])

    with open(out_dir / "big_items.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date", "description", "amount"])
        for t in big:
            w.writerow([t.date.isoformat(), t.description, f"{t.amount:.2f}"])

    groups = classify(all_txns)
    with open(out_dir / "random_spending.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date", "type", "description", "detail", "amount"])
        for t in groups["random"]:
            w.writerow([t.date.isoformat(), t.type, t.description, t.detail, f"{-t.amount:.2f}"])

    print(f"\nCSV files saved in: {out_dir}")


if __name__ == "__main__":
    main()
