"""Read your statement PDFs, store them in a database, and print analysis.

  python run.py              reads the REAL folder (Financial Tracker Project\\statements).
                             Creates tracker.db next to that folder (or in .parent if the
                             folder does not exist). If that folder does not exist, falls
                             back to the `statements` folder inside the code folder.
  python run.py test         reads the `statements` folder inside the code folder.
  python run.py fix          lets you change saved item classifications (regular/common/etc).
  python run.py folder PATH  saves the folder path for future runs.

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
from fintrack.settings import saved_folder, save_folder, SAVED_FILE
from fintrack.store import open_db, import_statement, load_statements, load_txns, get_items
from fintrack.questions import review, fix_items

HERE = Path(__file__).parent
IN_DIR = HERE / "statements"          # the folder inside the code folder (testing)
REAL_DIR = HERE.parent / "statements"  # the folder next to the code folder (your real statements)
OUT_DIR = HERE / "output"


def pick_folder(argv, real_dir=REAL_DIR, test_dir=IN_DIR, saved_file=None):
    """Which statements folder to read: "test" on the command line -> test_dir;
    otherwise the remembered folder (fintrack.settings.saved_folder) if it exists;
    else real_dir if it is a directory; else test_dir."""
    if "test" in argv:
        return Path(test_dir)

    if saved_file is None:
        saved_file = SAVED_FILE
    remembered = saved_folder(saved_file)
    if remembered is not None:
        return remembered

    if Path(real_dir).is_dir():
        return Path(real_dir)

    return Path(test_dir)


def main(in_dir=IN_DIR, out_dir=OUT_DIR, ask=input, wage_payer=WAGE_PAYER, ask_items=input, db_path=None):
    in_dir = Path(in_dir)
    out_dir = Path(out_dir)

    # Make in_dir if needed and print it
    in_dir.mkdir(exist_ok=True)
    print(f"Reading statements from: {in_dir}")

    # Determine db_path: default to parent / "tracker.db"
    if db_path is None:
        db_path = in_dir.parent / "tracker.db"
    else:
        db_path = Path(db_path)
    print(f"Database: {db_path}")

    # Parse all PDF statements
    pdfs = sorted(in_dir.glob("*.pdf")) + sorted(in_dir.glob("*.PDF"))
    pdfs = list(set(pdfs))  # Remove duplicates from case-insensitive globbing
    pdfs = sorted(pdfs, key=lambda p: p.name)

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

    # Open database and import statements
    conn = open_db(db_path)
    new_count = 0
    for st in kept:
        problems = check_statement(st)
        if import_statement(conn, st, problems):
            new_count += 1
    existing_count = len(kept) - new_count
    print(f"Stored {new_count} new statements; {existing_count} already in the database.")

    # If no PDFs and no statements in database: print message and return
    if not pdfs:
        db_statements = load_statements(conn)
        if not db_statements:
            print(f"No PDFs found. Drop your statements in: {in_dir}")
            return

    # Load everything from database
    all_stmts = load_statements(conn)
    all_txns = load_txns(conn)

    # Run review before reports
    review(conn, all_txns, ask_items, out=print)
    answers = get_items(conn)

    # Get all transactions from kept statements for report building (using database)
    # all_txns and all_stmts are already loaded from database above
    all_txns.sort(key=lambda t: t.date)

    # Generate reports
    out_dir.mkdir(exist_ok=True)

    # Statement by statement report
    print("\nSTATEMENT BY STATEMENT")
    rows = statement_report(all_stmts)
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
    analysis = analyse(cycles, answers=answers)

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


def run_command(argv, ask=input, out=print, saved_file=None, db_path=None, in_dir=None) -> bool:
    """Handle command-line commands. Returns True if argv was recognized, False otherwise.

    Commands:
    - ["folder", <path>]: save a folder path for future runs
    - ["folder"]: show usage for folder command (when no path given)
    - ["fix"]: enter fix mode to change saved item classifications
    - anything else ([], ["test"], etc): return False
    """
    if not argv:
        return False

    cmd = argv[0].lower()

    if cmd == "folder":
        # Handle folder command
        if len(argv) < 2:
            # No path given, show usage
            out("Usage: python run.py folder <path>")
            return True

        path = Path(argv[1])
        if not path.is_dir():
            out(f"That folder does not exist: {path}")
            return True

        # Save the folder
        if saved_file is None:
            saved_file = SAVED_FILE
        save_folder(path, saved_file)
        out(f"Saved. From now on I read statements from: {path}")
        return True

    if cmd == "fix":
        # Handle fix command
        if in_dir is None:
            in_dir = pick_folder(argv)
        else:
            in_dir = Path(in_dir)

        if db_path is None:
            db_path = in_dir.parent / "tracker.db"
        else:
            db_path = Path(db_path)

        # Check if database exists
        if not db_path.exists():
            out("No database yet. Run run.py first.")
            return True

        # Open database and call fix_items
        conn = open_db(db_path)
        fix_items(conn, ask, out)
        return True

    # Unknown command
    return False


if __name__ == "__main__":
    if not run_command(sys.argv[1:]):
        main(in_dir=pick_folder(sys.argv[1:]))
