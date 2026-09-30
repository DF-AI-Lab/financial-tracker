import json
from datetime import date
from pathlib import Path

import pytest

from fintrack.models import Txn

DATA = Path(__file__).parent / "data"


def load_expected(name="expected.json"):
    return json.loads((DATA / name).read_text())["statements"]


def to_txn(d):
    return Txn(date.fromisoformat(d["date"]), d["type"], d["description"],
               d["detail"], d["amount"], d["balance"])


@pytest.fixture(scope="session")
def expected():
    return load_expected()


@pytest.fixture(scope="session")
def all_expected_txns(expected):
    return [to_txn(t) for st in expected for t in st["transactions"]]


@pytest.fixture(scope="session")
def real_style_txns():
    return [to_txn(t) for st in load_expected("expected_real_style.json") for t in st["transactions"]]
