"""Read your statement PDFs, store them in a database, and print analysis.

  python run.py              reads the REAL folder (Financial Tracker Project\\statements).
                             Creates tracker.db next to that folder (or in .parent if the
                             folder does not exist). If that folder does not exist, falls
                             back to the `statements` folder inside the code folder.
  python run.py test         reads the `statements` folder inside the code folder.
  python run.py fix          lets you change saved item classifications (regular/common/etc).
  python run.py cat <n>      shows the details of category <n> from the spending list.
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
from fintrack.left import parse_money
from fintrack.spare import expected_spare, last_cycle_check, format_last_cycle, pay_block, format_pay_block
from fintrack.settings import saved_folder, save_folder, SAVED_FILE
from fintrack.store import open_db, import_statement, load_statements, load_txns, get_items, get_categories, set_value, get_spends, get_value
from fintrack.questions import review, fix_items
from fintrack.samebill import ask_same_bills
from fintrack.yearly import yearly_due, yearly_lines
from fintrack.picture import six_month_picture, format_picture
from fintrack.bycategory import category_spending, format_categories, format_category_detail
from fintrack.where import where_did_it_go, format_where, show_lines
from fintrack.subs import find_subscriptions, format_subscriptions

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

    # Sort transactions early for cycle building
    all_txns.sort(key=lambda t: t.date)

    # Run review before reports
    review(conn, all_txns, ask_items, out=print, skip_small=True)
    ask_same_bills(conn, all_txns, ask_items, out=print)
    answers = get_items(conn)

    # Review payday-transfer rules and get rules for analysis
    from fintrack.paydayrule import review_rules
    from fintrack.store import get_rules
    from fintrack.typed import swap_spends

    # Build cycles early for rule review
    cycles = build_cycles(all_txns, payer=wage_payer)
    if cycles:
        paydays = [c.start for c in cycles]
        review_rules(conn, all_txns, paydays, ask_items, out=print)

    # Swap typed spends with statements
    swap_spends(conn, all_txns, ask_items, out=print)

    rules = get_rules(conn)

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
    if not cycles:
        print(f"\nNo wage from {wage_payer} found, so payday cycles and the pay question are skipped.")
        return

    # Print payday-to-payday cycles
    print("\nPAYDAY TO PAYDAY")
    cycle_rows = cycle_report(cycles)
    for row in cycle_rows:
        status = "" if row["complete"] else " (so far)"
        print(f"  {row['label']:<12} wage {row['wage']:>9.2f}  bills {row['bills']:>8.2f}  random {row['random']:>8.2f}  spare {row['spare']:>9.2f}{status}")

    # Analyze spending patterns with rules
    analysis = analyse(cycles, answers=answers, rules=rules)

    # Check for yearly bills due
    due = []
    if all_txns:
        due = yearly_due(all_txns, answers, today=max(t.date for t in all_txns))
        if due:
            print()
            for line in yearly_lines(due):
                print(line)

    # Print six-month picture
    print()
    picture = six_month_picture(cycles, analysis, items=answers, categories=get_categories(conn))
    for line in format_picture(picture):
        print(line)

    # Print spending by category
    print()
    cat_result = category_spending(cycles, items=answers, categories=get_categories(conn), rules=rules)
    for line in format_categories(cat_result):
        print(line)

    # Print last cycle check
    print()
    for line in format_last_cycle(last_cycle_check(cycles, answers=answers, rules=rules)):
        print(line)

    # Print where did it go
    w = where_did_it_go(cycles, answers=answers, rules=rules, categories=get_categories(conn), items=answers)
    where_lines = format_where(w)
    if where_lines:
        print()
    for line in where_lines:
        print(line)

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

    # Save the wage and print the pay block
    set_value(conn, "pay", str(wage))
    for line in format_pay_block(pay_block(cycles, analysis, wage, categories=get_categories(conn), items=answers, yearly=due)):
        print(line)

    # Print subscriptions
    print()
    for line in format_subscriptions(find_subscriptions(all_txns, items=answers)):
        print(line)

    # Print the typed spends block if there are any
    spends = get_spends(conn)
    if spends:
        from fintrack.typed import format_spends, money_for_spending
        print()
        money = money_for_spending(cycles, analysis, wage)
        for line in format_spends(spends, money):
            print(line)


def _print_spends_block(conn, wage_payer, out):
    """Print the SO FAR THIS CYCLE block. Pay = the one typed last in run.py, else the last wage."""
    from fintrack.store import get_rules
    from fintrack.typed import format_spends, money_for_spending

    txns = load_txns(conn)
    txns.sort(key=lambda t: t.date)
    cycles = build_cycles(txns, payer=wage_payer)
    if not cycles:
        return
    analysis = analyse(cycles, answers=get_items(conn), rules=get_rules(conn))
    saved = get_value(conn, "pay")
    wage = float(saved) if saved else cycles[-1].wage
    for line in format_spends(get_spends(conn), money_for_spending(cycles, analysis, wage)):
        out(line)


def run_command(argv, ask=input, out=print, saved_file=None, db_path=None, in_dir=None, wage_payer=WAGE_PAYER, today=None) -> bool:
    """Handle command-line commands. Returns True if argv was recognized, False otherwise.

    Commands:
    - ["folder", <path>]: save a folder path for future runs
    - ["folder"]: show usage for folder command (when no path given)
    - ["fix"]: enter fix mode to change saved item classifications
    - ["cat", <number>]: show details of a category from the spending list
    - ["cat"]: show usage for cat command (when no number given)
    - ["show", <number>]: show payments behind a line in the WHERE DID IT GO list
    - ["show"]: show usage for show command (when no number given)
    - ["add", <amount>, <name>...]: add a typed spend
    - ["spends"]: show the current typed spends block
    - ["remove", <number>]: remove a typed spend by number
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

    if cmd == "cat":
        # Handle cat command
        if len(argv) < 2:
            # No number given, show usage
            out("Usage: run.py cat <number>   (the numbers are in the SPENDING BY CATEGORY list)")
            return True

        # Parse the number
        try:
            n = int(argv[1])
        except ValueError:
            out("Usage: run.py cat <number>   (the numbers are in the SPENDING BY CATEGORY list)")
            return True

        # Find in_dir and db_path
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

        # Open database, load transactions, build cycles, and get category details
        conn = open_db(db_path)
        txns = load_txns(conn)
        txns.sort(key=lambda t: t.date)
        cycles = build_cycles(txns, payer=wage_payer)

        # Get items, categories, and rules
        items = get_items(conn)
        categories_dict = get_categories(conn)
        from fintrack.store import get_rules
        rules = get_rules(conn)

        # Get category spending and format detail
        cat_result = category_spending(cycles, items=items, categories=categories_dict, rules=rules)
        for line in format_category_detail(cat_result, n):
            out(line)

        return True

    if cmd == "show":
        # Handle show command
        if len(argv) < 2:
            # No number given, show usage
            out("Usage: run.py show <number>   (the numbers are in the WHERE DID list)")
            return True

        # Parse the number
        try:
            n = int(argv[1])
        except ValueError:
            out("Usage: run.py show <number>   (the numbers are in the WHERE DID list)")
            return True

        # Find in_dir and db_path
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

        # Open database, load transactions, build cycles
        conn = open_db(db_path)
        txns = load_txns(conn)
        txns.sort(key=lambda t: t.date)
        cycles = build_cycles(txns, payer=wage_payer)

        # Get items, categories, and rules
        items = get_items(conn)
        categories_dict = get_categories(conn)
        from fintrack.store import get_rules
        rules = get_rules(conn)

        # Get where_did_it_go and show the line
        w = where_did_it_go(cycles, answers=items, rules=rules, categories=categories_dict, items=items)
        if w is None:
            out("Not enough finished paydays yet.")
            return True

        for line in show_lines(w, n):
            out(line)

        return True

    if cmd == "add":
        # Handle add command
        from fintrack.typed import parse_add
        from fintrack.categories import guess_category
        from fintrack.store import add_spend

        # Check usage before database check
        if len(argv) < 2:
            out("Usage: run.py add <amount> <name>   e.g. run.py add 12.50 Costa")
            return True

        parsed = parse_add(argv[1:])
        if parsed is None:
            out("Usage: run.py add <amount> <name>   e.g. run.py add 12.50 Costa")
            return True

        amount, name = parsed

        # Find in_dir and db_path
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

        # Guess category and add spend
        category = guess_category(name)
        if today is None:
            from datetime import date
            today = date.today()

        conn = open_db(db_path)
        add_spend(conn, today, amount, name, category)
        out(f"Added {amount:.2f} {name} ({category}) on {today:%d %b %Y}.")

        # Print the spends block
        _print_spends_block(conn, wage_payer, out)

        return True

    if cmd == "spends":
        # Handle spends command
        # Find in_dir and db_path
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

        # Load and display spends
        conn = open_db(db_path)
        _print_spends_block(conn, wage_payer, out)

        return True

    if cmd == "remove":
        # Handle remove command
        from fintrack.store import delete_spend

        # Check usage before database check
        if len(argv) < 2:
            out("Usage: run.py remove <number>   (the numbers are in the SO FAR list)")
            return True

        try:
            n = int(argv[1])
        except ValueError:
            out("Usage: run.py remove <number>   (the numbers are in the SO FAR list)")
            return True

        # Find in_dir and db_path
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

        # Get spends and remove the one at position n
        conn = open_db(db_path)
        spends = get_spends(conn)

        if n < 1 or n > len(spends):
            out(f"There is no typed spend {n}. Pick 1 to {len(spends)}.")
            return True

        # Remove the nth spend (1-indexed)
        spend_to_remove = spends[n - 1]
        delete_spend(conn, spend_to_remove["id"])
        out(f"Removed {spend_to_remove['amount']:.2f} {spend_to_remove['name']}.")

        # Print the spends block
        _print_spends_block(conn, wage_payer, out)

        return True

    # Unknown command
    return False


if __name__ == "__main__":
    if not run_command(sys.argv[1:]):
        main(in_dir=pick_folder(sys.argv[1:]))
