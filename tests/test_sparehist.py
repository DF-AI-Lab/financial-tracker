"""Spare cash (pay - bills) of the last finished month and the average over the 6-month window."""
from datetime import date

import pytest

from fintrack.common import analyse
from fintrack.cycles import build_cycles
from fintrack.models import Txn
from fintrack.sparehist import spare_history

PAY = "NEW JOB LTD"


def month(m, wage, rent, phone, shop):
    return [Txn(date(2026, m, 28), "CR", PAY, "", wage),
            Txn(date(2026, m, 28), "SO", "LANDLORD", "RENT", -rent),
            Txn(date(2026, m + 1, 2), "DD", "PHONE CO", "", -phone),
            Txn(date(2026, m + 1, 10), "VIS", f"SHOP {m}", "", -shop)]


def test_last_month_and_average():
    tx = (month(1, 2000, 600, 100, 50) + month(2, 2100, 600, 100, 60) + month(3, 2200, 600, 270, 70)
          + [Txn(date(2026, 4, 28), "CR", PAY, "", 2300.0)])
    cs = build_cycles(tx, payer=PAY)
    h = spare_history(cs, analyse(cs))
    assert h["months"] == 3
    assert h["last"] == pytest.approx(2200 - 600 - 270)               # 1,330 (shop spends are not bills)
    assert h["avg"] == pytest.approx(((2000 - 700) + (2100 - 700) + 1330) / 3)


def test_no_finished_month():
    cs = build_cycles([Txn(date(2026, 1, 28), "CR", PAY, "", 2000.0)], payer=PAY)
    assert spare_history(cs, analyse(cs)) is None
