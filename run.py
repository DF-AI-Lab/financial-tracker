"""Read your statement PDFs and print bills, payday-to-payday cycles and what is left.

  python run.py        reads the REAL folder: `statements` next to this code folder
                       (Financial Tracker Project\\statements). If that folder does not
                       exist it falls back to the `statements` folder inside the code folder.
  python run.py test   reads the `statements` folder inside the code folder (for testing)

CSV files are written to `output/` inside the code folder.
"""
import sys
import csv
from pathlib import Path

from fintrack.parse import parse_statement
from fintrack.checks import check_statement
from fintrack.dedupe import unique_statements
from fintrack.sort import bills_summary, classify, statement_report, big_items
from fintrack.cycles import build_cycles, cycle_report, WAGE_PAYER
from fintrack.common import analyse
from fintrack.left import parse_money, format_left

HERE = Path(__file__).parent
IN_DIR = HERE / "statements"          # the folder inside the code folder (testing)
REAL_DIR = HERE.parent / "statements"  # the folder next to the code folder (your real statements)
OUT_DIR = HERE / "output"


def pick_folder(argv, real_dir=REAL_DIR, test_dir=IN_DIR, saved_file=None):
    """Which statements folder to read: "test" on the command line -> test_dir;
    otherwise real_dir if it exists, else test_dir."""
    if "test" in argv:
        return Path(test_dir)
    if Path(real_dir).is_dir():
        return Path(real_dir)
    return Path(test_dir)


def main(in_dir=IN_DIR, out_dir=OUT_DIR, ask=input, wage_payer=WAGE_PAYER):
    in_dir = Path(in_dir)
    out_dir = Path(out_dir)

    in_dir.mkdir(exist_ok=True)
    print(f"Reading statements from: {in_dir}")
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

    # Payday-to-payday cycles and pay question
    cycles = build_cycles(all_txns, payer=wage_payer)

    if not cycles:
        print(f"\nNo wage from {wage_payer} found, so payday cycles and the pay question are skipped.")
        return

    # Print payday-to-payday cycles
    print("\nPAYDAY TO PAYDAY")
    cycle_rows = cycle_report(cycles)
    for row in cycle_rows:
        status = "" if row["complete"] else " (so far)"
        print(f"  {row['label']:<12} wage {row['wage']:>9.2f}  bills {row['bills']:>8.2f}  random {row['random']:>8.2f}  spare {row['spare']:>9.2f}{status}")

    # Analyze spending patterns
    analysis = analyse(cycles)

    # Print common spending
    print("\nCOMMON (average per cycle over the last N complete cycles)")
    if analysis.common:
        for key in sorted(analysis.common.keys(), key=lambda k: analysis.common[k]["average"], reverse=True):
            data = analysis.common[key]
            print(f"  {key:<35} {data['average']:>9.2f}")

    # Print one-offs
    print("\nONE-OFFS (left out of the averages)")
    if analysis.one_offs:
        for t in analysis.one_offs:
            print(f"  {t.date.isoformat()} {t.description:<30} {t.amount:>9.2f}")
    else:
        print("  none")

    # Write cycles.csv
    with open(out_dir / "cycles.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["label", "start", "end", "complete", "wage", "other_in", "bills", "random", "spare"])
        for row in cycle_rows:
            w.writerow([row["label"], row["start"], row["end"], row["complete"], row["wage"],
                       row["other_in"], row["bills"], row["random"], row["spare"]])

    # Write common.csv
    with open(out_dir / "common.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["key", "kind", "cycles", "total", "average"])
        for key in sorted(analysis.common.keys(), key=lambda k: analysis.common[k]["average"], reverse=True):
            data = analysis.common[key]
            w.writerow([key, data["kind"], data["cycles"], f"{data['total']:.2f}", f"{data['average']:.2f}"])

    # Ask for wage
    last_wage = cycles[-1].wage
    tries = 0
    while tries < 3:
        try:
            answer = ask(f"Latest pay? Press Enter to use last wage ({last_wage:,.2f}): ")
        except (EOFError, OSError):
            print("(No keyboard available, skipping the pay question.)")
            return

        if answer == "":
            # Use last wage
            wage = last_wage
            break

        wage = parse_money(answer)
        if wage is None:
            print("Sorry, I could not read that as money.")
            tries += 1
        else:
            break

    if tries >= 3:
        return

    # Print the wage breakdown
    print(format_left(wage, analysis))


if __name__ == "__main__":
    main(in_dir=pick_folder(sys.argv[1:]))
