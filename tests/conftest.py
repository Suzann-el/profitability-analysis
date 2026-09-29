from __future__ import annotations

import json
from pathlib import Path

import pytest

from profit.config import RAW_DIR
from profit.db import Warehouse

RAW_OK = (RAW_DIR / "FactResellerSales.csv").exists()
needs_data = pytest.mark.skipif(not RAW_OK, reason="CSV AdventureWorksDW absents : lancer `python scripts/download_data.py`")


@pytest.fixture(scope="session")
def wh():
    if not RAW_OK:
        pytest.skip("CSV AdventureWorksDW absents : lancer `python scripts/download_data.py`")
    return Warehouse.build()


@pytest.fixture(scope="session")
def fact(wh):
    df = wh.con.execute("SELECT sku, channel, order_date, quantity, gross_amount, discount_amount, net_sales, cogs FROM fact_sales").fetchdf()
    for c in ("gross_amount", "discount_amount", "net_sales", "cogs"):
        df[c] = df[c].astype(float)
    return df


@pytest.fixture(scope="session")
def results(wh):
    from profit.results import collect
    return collect(wh)
