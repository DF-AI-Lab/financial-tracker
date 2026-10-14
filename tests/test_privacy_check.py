"""v3 move-in privacy check (14 Oct 2026). Fake data only."""
import sqlite3

from tools.privacy_check import hide, scan


def test_scan_finds_bank_details_and_hides_digits(tmp_path):
    conn = sqlite3.connect(tmp_path / "t.db")
    conn.execute("CREATE TABLE payments (description TEXT, detail TEXT)")
    conn.execute("INSERT INTO payments VALUES ('SAM PARKER', '40-12-34 12345678')")
    conn.execute("INSERT INTO payments VALUES ('TESCO STORES 2041', '')")
    found = scan(conn)
    assert found["sort code"]["count"] == 1 and found["8-digit number (account number?)"]["count"] == 1
    assert "40-12-34" not in str(found) and "##-##-##" in str(found)
    assert hide("ref 12345678") == "ref ########"


def test_fake_statements_are_clear(tmp_path):
    import shutil
    import run
    from tests.conftest import DATA
    inbox = tmp_path / "statements"
    inbox.mkdir()
    for n in ("statement_2024_08.pdf", "statement_2024_09.pdf", "statement_2024_10.pdf"):
        shutil.copy(DATA / n, inbox / n)
    run.main(in_dir=inbox, out_dir=tmp_path / "output", ask=lambda p: "2500", wage_payer="ACME MOTORS PLC",
             ask_items=lambda p: "")
    found = scan(sqlite3.connect(tmp_path / "tracker.db"))
    assert "sort code" not in found and "IBAN" not in found and "postcode" not in found
