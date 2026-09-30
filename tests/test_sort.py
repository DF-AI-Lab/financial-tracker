from collections import defaultdict

import pytest

from fintrack.sort import bills_summary, classify, monthly_report


def test_classify(all_expected_txns):
    r = classify(all_expected_txns)
    assert set(r) == {"income", "bills", "random"}
    assert all(t.amount > 0 for t in r["income"])
    assert all(t.amount < 0 and t.type in ("DD", "SO") for t in r["bills"])
    assert all(t.amount < 0 and t.type not in ("DD", "SO") for t in r["random"])
    assert len(r["income"]) + len(r["bills"]) + len(r["random"]) == len(all_expected_txns)


def test_refund_counts_as_income_not_a_bill(all_expected_txns):
    r = classify(all_expected_txns)
    assert any(t.description == "INT'L 0093267280" for t in r["income"])


def test_bills_summary(all_expected_txns):
    s = bills_summary(all_expected_txns)
    assert s["GYM CLUB - MEMBERSHIP"] == {"months": 3, "average": 50.00}
    assert s["WATER BOARD - WATER"] == {"months": 3, "average": 15.75}
    assert s["TV LICENCE - LICENCE"] == {"months": 3, "average": 13.25}
    assert s["SKY DIGITAL - SKY"] == {"months": 3, "average": 46.50}
    assert s["PHONE CO - MOBILE"] == {"months": 3, "average": 40.11}
    assert s["SAM PARKER - RENT"] == {"months": 3, "average": 550.00}
    assert s["SAM PARKER - BILLS"] == {"months": 1, "average": 150.00}
    assert s["COUNCIL TAX - CITY COUNCIL"] == {"months": 1, "average": 161.00}
    assert s["ENERGY CO - ENERGY"] == {"months": 1, "average": 157.12}
    assert not any("Food and bil" in k or "TACO" in k for k in s), "card/bill-payment spending is not a bill"


def test_monthly_report(all_expected_txns):
    want = defaultdict(lambda: {"income": 0.0, "bills": 0.0, "random": 0.0})
    for t in all_expected_txns:
        m = t.date.strftime("%Y-%m")
        if t.amount > 0:
            want[m]["income"] += t.amount
        elif t.type in ("DD", "SO"):
            want[m]["bills"] += -t.amount
        else:
            want[m]["random"] += -t.amount
    got = monthly_report(all_expected_txns)
    assert set(got) == set(want)
    for m, w in want.items():
        for k in ("income", "bills", "random"):
            assert got[m][k] == pytest.approx(w[k], abs=0.005), f"{m} {k}"
        assert got[m]["spare"] == pytest.approx(w["income"] - w["bills"] - w["random"], abs=0.005)
