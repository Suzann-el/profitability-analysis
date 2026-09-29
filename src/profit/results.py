"""Assemble TOUS les chiffres du projet (tableau de bord, note, README) dans un seul dictionnaire / JSON.

Aucun chiffre n'est écrit à la main dans les livrables : ils viennent tous d'ici, donc des requêtes SQL.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from . import whatif as wi
from .config import P0_LABEL, P1_LABEL, PARAMS
from .db import Warehouse

PRICE_STEPS = (0.03, 0.05, 0.08, 0.10)
ELASTICITIES = (0.0, -1.0, -2.0, -3.0)
VARIABLE_SHARES = (1.0, 0.95, 0.90, 0.80)


def _f(v):
    return None if v is None or (isinstance(v, float) and np.isnan(v)) else float(v)


def _records(df: pd.DataFrame) -> list[dict]:
    return json.loads(df.to_json(orient="records", date_format="iso"))


def collect(wh: Warehouse) -> dict:
    k = wh.query("kpi_summary")
    k["channel"] = k["channel"].fillna("Total")
    kpi = {p: {r.channel: {c: _f(getattr(r, c)) for c in k.columns if c not in ("period", "channel")} for r in g.itertuples()}
           for p, g in k.groupby("period")}
    p1, p0 = kpi["P1"], kpi["P0"]
    res = {"periods": {"p0": P0_LABEL, "p1": P1_LABEL, **{k_.lower(): v for k_, v in PARAMS.items()}}, "kpi": kpi}
    res["growth"] = {"net_sales_pct": 100 * (p1["Total"]["net_sales"] / p0["Total"]["net_sales"] - 1),
                     "margin_delta": p1["Total"]["gross_margin"] - p0["Total"]["gross_margin"],
                     "internet_share_of_sales_pct": 100 * p1["Internet"]["net_sales"] / p1["Total"]["net_sales"],
                     "internet_share_of_margin_pct": 100 * p1["Internet"]["gross_margin"] / p1["Total"]["gross_margin"]}

    res["coverage"] = _records(wh.query("info_period_coverage"))

    bridge = wh.query("pvm_bridge")
    res["bridge"] = _records(bridge[["step", "value"]])
    res["bridge_by_channel"] = _records(wh.query("pvm_by_channel"))
    res["top_cost_increases"] = _records(wh.query("pvm_top_cost_increases"))
    res["bridge_by_category"] = _records(wh.query("pvm_by_category"))

    cat = wh.query("kpi_by_category")
    res["categories_p1"] = _records(cat[cat.period == "P1"].drop(columns="period"))
    res["subcategories_p1"] = _records(wh.query("kpi_by_subcategory"))
    res["territories_p1"] = _records(wh.query("kpi_by_territory"))
    res["reseller_types_p1"] = _records(wh.query("kpi_by_reseller_type"))
    res["calendar_years"] = _records(wh.query("kpi_by_calendar_year"))
    ps = wh.query("kpi_price_structure")
    res["price_structure"] = _records(ps.assign(category=ps["category"].fillna("Total")))

    for name, key in (("abc_sku_summary", "abc_sku"), ("abc_reseller_summary", "abc_reseller")):
        res[key] = _records(wh.query(name))
    pareto = wh.con.execute("SELECT * FROM pareto_sku ORDER BY rank_margin").fetchdf()
    res["pareto"] = {"n_skus": int(len(pareto)),
                     "peak_cum_margin_pct": float(pareto["cum_margin_pct_of_net"].max()),
                     "class_a_pct_of_skus": float(100 * (pareto.abc_class == "A").mean())}
    res["worst_skus"] = _records(pareto.sort_values("gross_margin").head(10)[
        ["sku", "product_name", "category", "net_sales", "gross_margin", "margin_resellers", "margin_internet"]])

    loss = wh.query("loss_making_sku_channel")
    seg = wi.Segment(float(loss.net_sales.sum()), float(loss.cogs.sum()))
    by_cat = loss.groupby("category").agg(n=("sku", "count"), margin=("gross_margin", "sum"), revenue=("net_sales", "sum")).reset_index()
    bikes = loss[loss.category == "Bikes"]
    res["loss_making"] = {"n": int(len(loss)), "revenue": seg.revenue, "cogs": seg.cogs, "margin": seg.margin,
                          "share_of_total_revenue_pct": 100 * seg.revenue / p1["Total"]["net_sales"],
                          "bikes_margin": float(bikes.gross_margin.sum()), "bikes_share_of_loss_pct": 100 * float(bikes.gross_margin.sum()) / seg.margin,
                          "by_category": _records(by_cat), "top": _records(loss.head(8)[["sku", "product_name", "channel", "units", "net_sales", "gross_margin", "margin_pct"]])}

    d_prom = wh.query("disc_by_promotion")
    d_tot = float(wh.query("disc_summary").discounts.iloc[0])
    new_prod = d_prom[d_prom.promotion_type == "New Product"]
    turning = wh.query("disc_turning_lines_negative")
    below = turning[turning.population.str.startswith("2")].iloc[0]
    res["discounts"] = {"summary": _records(wh.query("disc_summary"))[0], "by_promotion": _records(d_prom),
                        "depth": _records(wh.query("disc_depth_buckets")), "populations": _records(turning),
                        "new_product_promos": float(new_prod.discounts.sum()), "new_product_promos_pct": 100 * float(new_prod.discounts.sum()) / d_tot,
                        "new_product_promos_margin_before": float(new_prod.margin_before.sum()), "new_product_promos_margin_after": float(new_prod.margin_after.sum()),
                        "already_below_cost_discounts": float(below.discounts), "already_below_cost_pct": 100 * float(below.discounts) / d_tot,
                        "already_below_cost_lines": int(below.lines)}

    # ------------------------------------------------------------------ simulations
    grid = wi.price_grid(seg, PRICE_STEPS, ELASTICITIES)
    dl = wh.query("disc_lines_p1")
    res["whatif"] = {
        "segment": {"revenue": seg.revenue, "cogs": seg.cogs, "margin": seg.margin},
        "price_grid": {"x": list(PRICE_STEPS), "elasticities": list(ELASTICITIES), "delta": grid.values.tolist()},
        "price_break_even_elasticity": {str(x): wi.break_even_elasticity(seg, x) for x in PRICE_STEPS},
        "price_sensitivity_v80_e3_x5": wi.price_change(seg, 0.05, -3.0, 0.8),
        "stop_selling": {"variable_shares": list(VARIABLE_SHARES), "delta": [wi.stop_selling(seg, v) for v in VARIABLE_SHARES],
                         "break_even_share": wi.break_even_variable_share(seg)},
        "discount_rules": [wi.discount_rule(dl, "no_discount_below_cost"), wi.discount_rule(dl, "cap", cap=0.10), wi.discount_rule(dl, "cap", cap=0.05)],
        "internet_plus10_margin": 0.10 * p1["Internet"]["net_sales"] * p1["Internet"]["margin_pct"] / 100,
    }
    br = {r["step"]: r["value"] for r in res["bridge"]}
    resel = next(r for r in res["bridge_by_channel"] if r["channel"] == "Revendeurs")
    inet = next(r for r in res["bridge_by_channel"] if r["channel"] == "Internet")
    res["pricing_vs_cost"] = {
        "resellers_price": resel["price"], "resellers_cost": resel["cost"], "resellers_gap": resel["price"] + resel["cost"],
        "resellers_gap_pct_of_sales": 100 * (resel["price"] + resel["cost"]) / p1["Revendeurs"]["net_sales"],
        "internet_price": inet["price"], "internet_cost": inet["cost"], "internet_gap": inet["price"] + inet["cost"],
        "bridge_price": br["Prix catalogue"], "bridge_cost": br["Coût standard"]}
    return res


def save(res: dict, path: Path) -> None:
    Path(path).write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
