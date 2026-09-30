import shutil

import pytest

import run
from fintrack.common import analyse
from fintrack.cycles import build_cycles
from fintrack.left import format_left, parse_money, what_is_left
from tests.conftest import DATA
from tests.synth import PAYER, synth_txns

FAKE = ("statement_2024_08.pdf", "statement_2024_09.pdf", "statement_2024_10.pdf")
ACME = "ACME MOTORS PLC"


@pytest.mark.parametrize("text,want", [
    ("2450", 2450.0), ("2,450.50", 2450.5), ("£2450", 2450.0), (" 2 450 ", 2450.0),
    ("GBP 2450", 2450.0), ("", None), ("abc", None), ("0", None), ("-5", None),
])
def test_parse_money(text, want):
    assert parse_money(text) == want


def analysis():
    return analyse(build_cycles(synth_txns(), payer=PAYER))


def test_what_is_left():
    r = what_is_left(2500, analysis())
    assert r["wage"] == 2500
    assert r["common"] == pytest.approx(817.16, abs=0.006)
    assert r["spare_after_common"] == pytest.approx(1682.84, abs=0.006)
    assert r["random"] == pytest.approx(27.17, abs=0.006)
    assert r["left"] == pytest.approx(1655.68, abs=0.006)


def test_format_left_text():
    text = format_left(2500, analysis())
    assert "IF YOUR PAY IS 2,500.00" in text
    for want in ("Common per cycle", "817.16", "Spare after common", "1,682.84",
                 "Typical random spending", "27.17", "Left after typical month", "1,655.68",
                 "last 6 complete cycles"):
        assert want in text, want
    assert all(ord(c) < 128 for c in text)


def test_format_left_no_history():
    assert "Not enough finished paydays" in format_left(2500, analyse([]))


def setup(tmp_path):
    inbox = tmp_path / "statements"
    inbox.mkdir()
    for n in FAKE:
        shutil.copy(DATA / n, inbox / n)
    return inbox, tmp_path / "output"


def answers(*replies):
    it = iter(replies)
    prompts = []

    def ask(prompt):
        prompts.append(prompt)
        r = next(it)
        if isinstance(r, Exception):
            raise r
        return r
    ask.prompts = prompts
    return ask


def test_run_shows_cycles_common_and_asks_for_pay(tmp_path, capsys):
    inbox, out = setup(tmp_path)
    ask = answers("2500")
    run.main(in_dir=inbox, out_dir=out, ask=ask, wage_payer=ACME)
    text = capsys.readouterr().out
    assert "PAYDAY TO PAYDAY" in text and "(so far)" in text
    assert "COMMON" in text and "ONE-OFFS" in text
    assert "IF YOUR PAY IS 2,500.00" in text and "Left after typical month" in text
    assert len(ask.prompts) == 1 and "2,462.62" in ask.prompts[0]   # last wage offered
    assert (out / "cycles.csv").exists() and (out / "common.csv").exists()
    assert all(ord(c) < 128 for c in text)


def test_enter_uses_last_wage(tmp_path, capsys):
    inbox, out = setup(tmp_path)
    run.main(in_dir=inbox, out_dir=out, ask=answers(""), wage_payer=ACME)
    assert "IF YOUR PAY IS 2,462.62" in capsys.readouterr().out


def test_bad_answer_asks_again(tmp_path, capsys):
    inbox, out = setup(tmp_path)
    run.main(in_dir=inbox, out_dir=out, ask=answers("abc", "2000"), wage_payer=ACME)
    text = capsys.readouterr().out
    assert "could not read" in text and "IF YOUR PAY IS 2,000.00" in text


def test_no_keyboard_available_skips_question(tmp_path, capsys):
    inbox, out = setup(tmp_path)
    run.main(in_dir=inbox, out_dir=out, ask=answers(EOFError()), wage_payer=ACME)
    text = capsys.readouterr().out
    assert "skipping" in text and "IF YOUR PAY IS" not in text


def test_no_wage_found_skips_everything(tmp_path, capsys):
    inbox, out = setup(tmp_path)

    def never(prompt):
        raise AssertionError("must not ask when there is no wage")
    run.main(in_dir=inbox, out_dir=out, ask=never)          # default payer VERTU is not in the fake data
    text = capsys.readouterr().out
    assert "No wage from VERTU MOTORS PLC found" in text
    assert "PAYDAY TO PAYDAY" not in text
