"""Intégrité des données : empreintes, contrôles qualité, et surtout PREUVE que les contrôles détectent bien les corruptions."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from profit.config import PARAMS, RAW_DIR
from profit.db import Warehouse, named_queries, render
from conftest import needs_data
from profit.config import SQL_DIR


@needs_data
def test_raw_files_match_manifest():
    import hashlib
    manifest = json.loads((Path(__file__).resolve().parents[1] / "data" / "manifest.json").read_text())
    for table, meta in manifest.items():
        h = hashlib.sha256((RAW_DIR / f"{table}.csv").read_bytes()).hexdigest()
        assert h == meta["sha256"], f"{table}.csv a changé par rapport au manifest"


def test_all_quality_checks_pass(wh):
    chk = wh.checks()
    assert len(chk) >= 15
    assert (chk["violations"] <= 0.005).all(), chk[chk["violations"] > 0.005]


# Chaque corruption doit être détectée par AU MOINS le contrôle indiqué (transaction annulée après chaque essai).
CORRUPTIONS = [
    ("net_sales altéré",      "UPDATE fact_sales SET net_sales = net_sales + 5 WHERE sales_line_id = (SELECT MIN(sales_line_id) FROM fact_sales)", "chk_net_identity"),
    ("net_sales vs staging",  "UPDATE fact_sales SET net_sales = net_sales + 5, gross_amount = gross_amount + 5 WHERE sales_line_id = (SELECT MIN(sales_line_id) FROM fact_sales)", "chk_net_sales_reconcile_staging"),
    ("ligne supprimée",       "DELETE FROM fact_sales WHERE sales_line_id = (SELECT MIN(sales_line_id) FROM fact_sales)", "chk_fact_rows_equal_staging"),
    ("ligne dupliquée",       "INSERT INTO fact_sales SELECT * FROM fact_sales LIMIT 1", "chk_fact_grain_unique"),
    ("sku orphelin",          "UPDATE fact_sales SET sku = NULL WHERE sales_line_id = (SELECT MIN(sales_line_id) FROM fact_sales)", "chk_orphan_products"),
    ("coût incohérent",       "UPDATE fact_sales SET cogs = cogs * 2 WHERE sales_line_id = (SELECT MIN(sales_line_id) FROM fact_sales)", "chk_cogs_identity"),
    ("remise incohérente",    "UPDATE fact_sales SET discount_amount = discount_amount + 3 WHERE sales_line_id = (SELECT MIN(sales_line_id) FROM fact_sales)", "chk_discount_identity"),
    ("brut incohérent",       "UPDATE fact_sales SET gross_amount = gross_amount * 3 WHERE sales_line_id = (SELECT MIN(sales_line_id) FROM fact_sales)", "chk_gross_amount_identity"),
    ("territoire orphelin",   "UPDATE fact_sales SET territory_key = 999 WHERE sales_line_id = (SELECT MIN(sales_line_id) FROM fact_sales)", "chk_orphan_territories"),
    ("date hors dimension",   "UPDATE fact_sales SET date_key = 19000101 WHERE sales_line_id = (SELECT MIN(sales_line_id) FROM fact_sales)", "chk_orphan_dates"),
    ("clé canal incohérente", "UPDATE fact_sales SET customer_key = 1 WHERE channel = 'Revendeurs' AND sales_line_id = (SELECT MIN(sales_line_id) FROM fact_sales WHERE channel = 'Revendeurs')", "chk_channel_keys"),
    ("quantité négative",     "UPDATE fact_sales SET quantity = -1 WHERE sales_line_id = (SELECT MIN(sales_line_id) FROM fact_sales)", "chk_positive_quantities_and_costs"),
]


@pytest.mark.parametrize("label,sql,expected_check", CORRUPTIONS, ids=[c[0] for c in CORRUPTIONS])
def test_quality_checks_detect_corruption(wh, label, sql, expected_check):
    wh.con.execute("BEGIN TRANSACTION")
    try:
        wh.con.execute(sql)
        chk = wh.checks().set_index("check")["violations"]
        assert chk[expected_check] > 0.005, f"{expected_check} n'a pas détecté « {label} »"
    finally:
        wh.con.execute("ROLLBACK")
    assert (wh.checks()["violations"] <= 0.005).all(), "le ROLLBACK n'a pas restauré l'état sain"


def test_windows_are_12_months_and_within_available_data(wh):
    d = wh.con.execute("SELECT period, MIN(order_date), MAX(order_date), COUNT(DISTINCT strftime(order_date, '%Y-%m')) FROM sales_period GROUP BY 1 ORDER BY 1").fetchall()
    assert [r[0] for r in d] == ["P0", "P1"]
    assert all(r[3] == 12 for r in d), "chaque fenêtre doit couvrir 12 mois distincts"
    assert d[0][1] >= date.fromisoformat(PARAMS["P0_START"]) and d[1][2] <= date.fromisoformat(PARAMS["P1_END"])
    # les deux canaux ont des ventes chaque mois de chaque fenêtre (sinon la comparaison serait biaisée)
    n = wh.con.execute("SELECT COUNT(*) FROM (SELECT period, strftime(order_date,'%Y-%m') m FROM sales_period GROUP BY 1,2 HAVING COUNT(DISTINCT channel) < 2)").fetchone()[0]
    assert n == 0


def test_reseller_data_ends_inside_p1(wh):
    last = wh.con.execute("SELECT MAX(order_date) FROM fact_sales WHERE channel = 'Revendeurs'").fetchone()[0]
    assert last <= date.fromisoformat(PARAMS["P1_END"]), "P1 dépasse la dernière vente revendeurs : comparaison biaisée"


def test_sku_is_the_stable_product_identifier(wh):
    n_keys, n_sku = wh.con.execute("SELECT COUNT(*), COUNT(DISTINCT sku) FROM dim_product").fetchone()
    assert n_keys > n_sku, "dim_product doit être historisée (plusieurs clés par sku)"
    assert wh.con.execute("SELECT COUNT(*) FROM dim_sku").fetchone()[0] == n_sku


def test_render_rejects_unresolved_parameters():
    with pytest.raises(KeyError):
        render("SELECT '${INCONNU}'", {"P0_START": "2020-01-01"})
    assert render("SELECT '${A}'", {"A": "x"}) == "SELECT 'x'"


def test_named_queries_parser_strips_comments(tmp_path):
    f = tmp_path / "q.sql"
    f.write_text("-- en-tête\n\n-- name: q1 (commentaire)\n-- ligne de doc\nSELECT 1;\n\n-- name: q2\nSELECT 2 -- fin\n;\n")
    q = named_queries(f)
    assert list(q) == ["q1", "q2"] and q["q1"] == "SELECT 1" and "ligne de doc" not in q["q1"]


def test_build_fails_clearly_when_data_missing(tmp_path):
    with pytest.raises(FileNotFoundError, match="download_data"):
        Warehouse.build(tmp_path)


def test_no_personal_columns_in_model(wh):
    forbidden = ("email", "phone", "first_name", "last_name", "birth", "address", "name_style")
    for t in ("dim_customer", "dim_reseller"):
        cols = [c[0].lower() for c in wh.con.execute(f"DESCRIBE {t}").fetchall()]
        assert not [c for c in cols if any(f in c for f in forbidden)], (t, cols)
    cols = [c[0].lower() for c in wh.con.execute("DESCRIBE dim_customer").fetchall()]
    assert cols == ["customer_key", "city", "state_province", "country"]
