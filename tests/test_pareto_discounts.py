"""Pareto / ABC, remises, structure de prix : invariants sur les vraies données + cas construits."""
from __future__ import annotations

import duckdb
import pandas as pd
import pytest

from profit.config import SQL_DIR
from profit.db import named_queries, render


# ------------------------------------------------------------------ Pareto / ABC
@pytest.mark.parametrize("table,key", [("pareto_sku", "sku"), ("pareto_reseller", "reseller_key")])
def test_pareto_invariants(wh, table, key):
    p = wh.con.execute(f"SELECT * FROM {table} ORDER BY rank_margin").fetchdf()
    m = p["gross_margin"].astype(float)
    assert p[key].is_unique and list(p["rank_margin"]) == list(range(1, len(p) + 1))
    assert m.is_monotonic_decreasing, "tri par marge décroissante"
    net, pos_total = m.sum(), m.clip(lower=0).sum()
    # base « marge positive » : toujours définie ; le cumul atteint 100 % à la dernière marge positive puis redescend jusqu'à net/positive
    cp = p["cum_margin_pct_of_positive"].astype(float)
    last_pos = int((m >= 0).sum()) - 1
    assert cp.iloc[last_pos] == pytest.approx(100.0) and cp.max() == pytest.approx(100.0)
    assert cp.iloc[-1] == pytest.approx(100 * net / pos_total)
    assert (m.iloc[: last_pos + 1] >= 0).all() and (m.iloc[last_pos + 1:] < 0).all()
    # base « marge nette » : indéfinie (NULL) quand la marge nette totale est négative, sinon finit à 100 %
    cn = p["cum_margin_pct_of_net"]
    if net > 0:
        assert cn.iloc[-1] == pytest.approx(100.0) and cn.max() > 100.0 and cn.idxmax() == last_pos
    else:
        assert cn.isna().all(), "une part de marge nette n'a pas de sens quand le total est négatif"
    assert set(p["abc_class"][m < 0]) == {"D"} and "D" not in set(p["abc_class"][m >= 0]), "D = exactement les marges négatives"


def test_reseller_net_margin_is_negative_so_net_base_is_undefined(wh):
    """Garde-fou de régression : c'est ce cas (total négatif) qui a révélé un cumul en % du total de signe inversé."""
    assert wh.con.execute("SELECT SUM(gross_margin) FROM pareto_reseller").fetchone()[0] < 0
    assert wh.con.execute("SELECT COUNT(cum_margin_pct_of_net) FROM pareto_reseller").fetchone()[0] == 0


@pytest.mark.parametrize("table", ["pareto_sku", "pareto_reseller"])
def test_abc_class_thresholds(wh, table):
    p = wh.con.execute(f"SELECT gross_margin::DOUBLE AS m, abc_class FROM {table} ORDER BY rank_margin").fetchdf()
    pos = p["m"].clip(lower=0)
    total_pos = pos.sum()
    before = pos.cumsum() - pos                              # cumul AVANT la ligne
    a, b = p["abc_class"].eq("A"), p["abc_class"].eq("B")
    assert (before[a] < 0.80 * total_pos).all() and (before[b] >= 0.80 * total_pos).all() and (before[b] < 0.95 * total_pos).all()
    assert (before[p["abc_class"].eq("C")] >= 0.95 * total_pos).all()
    assert pos[a].sum() >= 0.80 * total_pos, "la classe A couvre au moins 80 % de la marge positive"
    assert pos[a].sum() - pos[a].iloc[-1] < 0.80 * total_pos, "et elle est minimale (retirer sa dernière ligne passerait sous 80 %)"


def test_abc_summaries_sum_to_totals(wh):
    total = wh.query("kpi_summary")
    p1 = total[(total.period == "P1") & total.channel.isna()].iloc[0]
    s = wh.query("abc_sku_summary")
    assert s["gross_margin"].sum() == pytest.approx(p1["gross_margin"], abs=2) and s["net_sales"].sum() == pytest.approx(p1["net_sales"], abs=2)
    r = wh.query("abc_reseller_summary")
    res = total[(total.period == "P1") & (total.channel == "Revendeurs")].iloc[0]
    assert r["gross_margin"].sum() == pytest.approx(res["gross_margin"], abs=2)
    assert r["resellers"].sum() == wh.con.execute("SELECT COUNT(DISTINCT reseller_key) FROM sales_period WHERE period='P1' AND channel='Revendeurs'").fetchone()[0]


def test_loss_making_set_is_consistent(wh):
    l = wh.query("loss_making_sku_channel")
    assert (l["gross_margin"] < 0).all() and len(l) > 0
    check = wh.con.execute("""SELECT COUNT(*) FROM (SELECT sku, channel FROM sales_period WHERE period='P1' GROUP BY 1,2 HAVING SUM(gross_margin) < 0)""").fetchone()[0]
    assert check == len(l)
    assert l["gross_margin"].sum() == pytest.approx((l["net_sales"] - l["cogs"]).sum(), abs=1)


def test_sku_view_hides_losses_that_sku_channel_view_reveals(wh):
    """Le piège d'agrégation est réel : des (sku, canal) à perte appartiennent à des sku globalement rentables."""
    hidden = wh.con.execute("""
        SELECT COUNT(*) FROM (SELECT sku, channel FROM sales_period WHERE period='P1' GROUP BY 1,2 HAVING SUM(gross_margin) < 0) l
        JOIN pareto_sku p USING (sku) WHERE p.gross_margin > 0""").fetchone()[0]
    assert hidden > 0


# ------------------------------------------------------------------ Remises
def test_margin_before_minus_after_equals_discount(wh):
    bad = wh.con.execute("SELECT COUNT(*) FROM fact_sales WHERE ABS((margin_before_discount - gross_margin) - discount_amount) > 0.01").fetchone()[0]
    assert bad == 0


def test_discount_populations_partition_all_discounted_lines(wh):
    pop = wh.query("disc_turning_lines_negative")
    n_lines = wh.con.execute("SELECT COUNT(*) FROM sales_period WHERE period='P1' AND discount_amount > 0").fetchone()[0]
    tot = wh.con.execute("SELECT SUM(discount_amount) FROM sales_period WHERE period='P1' AND discount_amount > 0").fetchone()[0]
    assert pop["lines"].sum() == n_lines and pop["discounts"].sum() == pytest.approx(float(tot), abs=2)
    assert len(pop) == 3


def test_discount_populations_definitions(wh):
    d = wh.con.execute("SELECT margin_before_discount::DOUBLE mb, gross_margin::DOUBLE ma FROM sales_period WHERE period='P1' AND discount_amount > 0").fetchdf()
    pop = wh.query("disc_turning_lines_negative").set_index("population")["lines"]
    assert pop["1 - la remise crée la perte"] == ((d.mb >= 0) & (d.ma < 0)).sum()
    assert pop["2 - déjà à perte avant remise"] == (d.mb < 0).sum()
    assert pop["3 - reste rentable après remise"] == ((d.mb >= 0) & (d.ma >= 0)).sum()


def test_promotion_table_totals(wh):
    p = wh.query("disc_by_promotion")
    s = wh.query("disc_summary").iloc[0]
    assert p["discounts"].sum() == pytest.approx(s["discounts"], abs=2), "toutes les remises passent par une promotion (hors promo 1 = aucune)"
    assert (p["margin_before"] - p["margin_after"]).sum() == pytest.approx(p["discounts"].sum(), abs=2)


def test_depth_buckets_cover_all_reseller_lines(wh):
    b = wh.query("disc_depth_buckets")
    n = wh.con.execute("SELECT COUNT(*) FROM sales_period WHERE period='P1' AND channel='Revendeurs'").fetchone()[0]
    assert b["lines"].sum() == n
    assert b["depth"].tolist() == ["0 %", "0-5 %", "5-10 %", "10-20 %", "> 20 %"]


def test_internet_has_no_discounts(wh):
    assert wh.con.execute("SELECT COALESCE(SUM(discount_amount), 0) FROM fact_sales WHERE channel = 'Internet'").fetchone()[0] == 0


# ------------------------------------------------------------------ KPI : cohérence
def test_kpi_summary_totals_are_sum_of_channels(wh):
    k = wh.query("kpi_summary")
    for p in ("P0", "P1"):
        d = k[k.period == p]
        tot, parts = d[d.channel.isna()].iloc[0], d[d.channel.notna()]
        for c in ("net_sales", "cogs", "gross_margin", "units", "lines"):
            assert tot[c] == pytest.approx(parts[c].sum(), abs=2), (p, c)
        assert tot["gross_margin"] == pytest.approx(tot["net_sales"] - tot["cogs"], abs=2)
        assert tot["margin_pct"] == pytest.approx(100 * tot["gross_margin"] / tot["net_sales"], abs=0.01)


def test_kpi_categories_sum_to_total(wh):
    c = wh.query("kpi_by_category")
    k = wh.query("kpi_summary")
    for p in ("P0", "P1"):
        assert c[c.period == p]["gross_margin"].sum() == pytest.approx(k[(k.period == p) & k.channel.isna()].iloc[0]["gross_margin"], abs=3)


def test_price_structure_ratios(wh):
    ps = wh.query("kpi_price_structure").set_index(wh.query("kpi_price_structure")["category"].fillna("Total"))
    assert 50 < ps.loc["Total", "reseller_price_pct_of_internet"] < 70
    ref = wh.con.execute("""
        WITH per AS (SELECT sku, channel, SUM(quantity) q, SUM(net_sales)/SUM(quantity) p, SUM(cogs)/SUM(quantity) c FROM sales_period WHERE period='P1' GROUP BY 1,2)
        SELECT 100.0*SUM(r.c*r.q)/SUM(r.p*r.q) FROM per r JOIN per i ON i.sku=r.sku AND r.channel='Revendeurs' AND i.channel='Internet'""").fetchone()[0]
    assert ps.loc["Total", "cogs_pct_of_reseller_price"] == pytest.approx(ref, abs=0.06)


def test_calendar_year_flags_partial_years(wh):
    y = wh.query("kpi_by_calendar_year")
    r = y[(y.channel == "Revendeurs") & (y.year == 2013)].iloc[0]
    assert bool(r["partial"]) and r["months_with_sales"] == 11, "les ventes revendeurs 2013 s'arrêtent en novembre"
    assert not bool(y[(y.channel == "Internet") & (y.year == 2012)].iloc[0]["partial"])
