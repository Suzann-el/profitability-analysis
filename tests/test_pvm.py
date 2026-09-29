"""Pont Prix/Volume/Mix : exemple calculé à la main, recoupement SQL <-> pandas, identité, propriétés sur données aléatoires."""
from __future__ import annotations

import numpy as np
import pandas as pd
import duckdb
import pytest

from profit.config import PARAMS, SQL_DIR
from profit.db import named_queries, render
from profit.pvm import EFFECTS, bridge, identity_gap, pvm_lines

P0, P1 = ("2020-01-01", "2020-12-31"), ("2021-01-01", "2021-12-31")
MINI = {"P0_START": P0[0], "P0_END": P0[1], "P1_START": P1[0], "P1_END": P1[1]}

# --- Exemple à la main (voir la dérivation dans le commentaire) --------------------------------------------------
#  A : P0 q=100, prix 10, coût 6 (m=4)       -> P1 q=120, prix 11, coût 6,5
#  B : P0 q=50,  prix 20, remise 1/u, coût 12 (m=7) -> P1 q=40, prix 20, remise 2/u, coût 12
#  C : nouveau en P1 (q=10, ventes 100, coût 90)      D : arrêté (P0 : q=20, ventes 200, coût 150)
#  Q0c=150, Q1c=160.  Volume = (160/150-1) x (400+350) = 50 ; Mix = (480-426,67)+(280-373,33) = -40
#  Prix = 120 + 0 ; Remises = -(0) - (80-40) = -40 ; Coût = -60 + 0 ; Nouveaux = 10 ; Arrêtés = -50 ; Δ = 790-800 = -10
ROWS = [  # sku, channel, date, quantity, gross, discount, net, cogs
    ("A", "X", "2020-06-01", 100, 1000, 0, 1000, 600), ("A", "X", "2021-06-01", 120, 1320, 0, 1320, 780),
    ("B", "X", "2020-06-01", 50, 1000, 50, 950, 600), ("B", "X", "2021-06-01", 40, 800, 80, 720, 480),
    ("C", "X", "2021-06-01", 10, 100, 0, 100, 90), ("D", "X", "2020-06-01", 20, 200, 0, 200, 150),
]
EXPECTED = {"volume_effect": 50.0, "mix_effect": -40.0, "price_effect": 120.0, "discount_effect": -40.0,
            "cost_effect": -60.0, "new_effect": 10.0, "discontinued_effect": -50.0}


def _mini_fact():
    return pd.DataFrame(ROWS, columns=["sku", "channel", "order_date", "quantity", "gross_amount", "discount_amount", "net_sales", "cogs"])


def _mini_sql():
    con = duckdb.connect()
    f = _mini_fact()
    f["order_date"] = pd.to_datetime(f["order_date"]).dt.date
    con.register("f_df", f)
    con.execute("CREATE TABLE fact_sales AS SELECT * FROM f_df")
    con.execute("CREATE TABLE dim_sku AS SELECT DISTINCT sku, 'Cat' AS category FROM f_df")
    q = named_queries(SQL_DIR / "03_kpis.sql")["create_sales_period"]
    con.execute(render(q, MINI))
    con.execute(render(named_queries(SQL_DIR / "04_pvm.sql")["create_pvm_lines"], MINI))
    return con


def test_handworked_example_pandas():
    b = bridge(pvm_lines(_mini_fact(), P0, P1))
    for k, v in EXPECTED.items():
        assert b[k] == pytest.approx(v, abs=1e-9), k
    assert (b["margin0"], b["margin1"]) == (800, 790)


def test_handworked_example_sql():
    con = _mini_sql()
    got = con.execute("SELECT " + ",".join(f"SUM({e})" for e in EFFECTS) + ", SUM(margin0), SUM(margin1) FROM pvm_lines").fetchone()
    for e, v in zip(EFFECTS, got):
        assert v == pytest.approx(EXPECTED[e], abs=1e-9), e
    assert got[-2:] == (800, 790)


def test_sql_bridge_query_on_handworked_example():
    con = _mini_sql()
    rows = con.execute(render(named_queries(SQL_DIR / "04_pvm.sql")["pvm_bridge"], MINI)).fetchall()
    br = {r[0]: r[2] for r in rows}                      # (étape, ordre, valeur)
    assert br["Marge P0"] == 800 and br["Marge P1"] == 790 and br["Volume"] == 50 and br["Mix produits/canaux"] == -40
    assert br["Prix catalogue"] == 120 and br["Remises"] == -40 and br["Coût standard"] == -60
    assert br["Nouveaux produits"] == 10 and br["Produits arrêtés"] == -50


def test_identity_holds_on_handworked_example():
    assert identity_gap(pvm_lines(_mini_fact(), P0, P1)) < 1e-9


@pytest.mark.parametrize("seed", range(25))
def test_identity_on_random_data(seed):
    """Propriété : quelles que soient les données, marge P1 - marge P0 = somme des effets."""
    rng = np.random.default_rng(seed)
    rows = []
    for sku in range(rng.integers(3, 12)):
        for ch in ("X", "Y"):
            for per, year in ((0, 2020), (1, 2021)):
                if rng.random() < 0.8:
                    q = int(rng.integers(1, 200)); L = rng.uniform(5, 100); d = rng.uniform(0, .3) * L * (rng.random() < .3); c = rng.uniform(3, 110)
                    rows.append((f"S{sku}", ch, f"{year}-05-01", q, q * L, q * d, q * (L - d), q * c))
    if not rows:
        return
    f = pd.DataFrame(rows, columns=["sku", "channel", "order_date", "quantity", "gross_amount", "discount_amount", "net_sales", "cogs"])
    lines = pvm_lines(f, P0, P1)
    if ((lines.q0 > 0) & (lines.q1 > 0)).any():
        assert identity_gap(lines) < 1e-6


def test_partition_new_discontinued_continuing(wh):
    l = wh.con.execute("SELECT * FROM pvm_lines").fetchdf()
    cont = (l.q0 > 0) & (l.q1 > 0)
    new, disc = l.q0 == 0, l.q1 == 0
    assert not (new & disc).any() and (cont | new | disc).all()
    assert (l.loc[~new, "new_effect"] == 0).all() and (l.loc[~disc, "discontinued_effect"] == 0).all()
    for e in ("volume_effect", "mix_effect", "price_effect", "discount_effect", "cost_effect"):
        assert (l.loc[~cont, e] == 0).all(), f"{e} doit être nul hors lignes continues"


def test_line_level_identity_real_data(wh):
    l = wh.con.execute("SELECT * FROM pvm_lines").fetchdf()
    gap = (l.delta_margin - l[EFFECTS].sum(axis=1)).abs().max()
    assert gap < 0.01, "chaque ligne doit vérifier l'identité (écart = arrondis 4 décimales de la source)"


def test_bridge_identity_real_data(wh):
    l = wh.con.execute("SELECT * FROM pvm_lines").fetchdf()
    assert identity_gap(l) < 1.0


def test_sql_matches_independent_pandas_implementation(wh, fact):
    ref = pvm_lines(fact, (PARAMS["P0_START"], PARAMS["P0_END"]), (PARAMS["P1_START"], PARAMS["P1_END"])).set_index(["sku", "channel"]).sort_index()
    sql = wh.con.execute("SELECT * FROM pvm_lines").fetchdf().set_index(["sku", "channel"]).sort_index()
    assert sql.index.equals(ref.index)
    for e in EFFECTS + ["margin0", "margin1"]:
        np.testing.assert_allclose(sql[e].astype(float), ref[e], atol=1e-6, err_msg=e)


def test_bridge_endpoints_match_kpis(wh):
    b = {r.step: r.value for r in wh.query("pvm_bridge").itertuples()}
    k = wh.query("kpi_summary")
    tot = k[k.channel.isna()].set_index("period")["gross_margin"]
    assert b["Marge P0"] == pytest.approx(tot["P0"], abs=1) and b["Marge P1"] == pytest.approx(tot["P1"], abs=1)


def test_by_channel_and_category_sum_to_total(wh):
    tot = {r.step: r.value for r in wh.query("pvm_bridge").itertuples()}
    ch, ca = wh.query("pvm_by_channel"), wh.query("pvm_by_category")
    for df in (ch, ca):
        assert df["margin_p1"].sum() == pytest.approx(tot["Marge P1"], abs=2)
        assert df["price"].sum() == pytest.approx(tot["Prix catalogue"], abs=2)
        assert df["cost"].sum() == pytest.approx(tot["Coût standard"], abs=2)
