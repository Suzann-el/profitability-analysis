"""Implémentation de RÉFÉRENCE du pont Prix/Volume/Mix en pandas, indépendante du SQL (`sql/04_pvm.sql`).

Sert à recouper le SQL ligne par ligne dans les tests : deux implémentations écrites séparément qui doivent
donner les mêmes chiffres. Mêmes définitions que le SQL (voir l'en-tête de 04_pvm.sql).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

EFFECTS = ["volume_effect", "mix_effect", "price_effect", "discount_effect", "cost_effect", "new_effect", "discontinued_effect"]


def pvm_lines(fact: pd.DataFrame, p0: tuple[str, str], p1: tuple[str, str]) -> pd.DataFrame:
    """`fact` : colonnes sku, channel, order_date, quantity, gross_amount, discount_amount, net_sales, cogs."""
    f = fact.copy()
    f["order_date"] = pd.to_datetime(f["order_date"])

    def agg(bounds):
        m = f[(f["order_date"] >= bounds[0]) & (f["order_date"] <= bounds[1])]
        return m.groupby(["sku", "channel"])[["quantity", "gross_amount", "discount_amount", "net_sales", "cogs"]].sum()

    a, b = agg(p0), agg(p1)
    w = a.add_suffix("0").join(b.add_suffix("1"), how="outer").fillna(0.0)
    w["margin0"] = w["net_sales0"] - w["cogs0"]
    w["margin1"] = w["net_sales1"] - w["cogs1"]
    cont = (w["quantity0"] > 0) & (w["quantity1"] > 0)
    q0c, q1c = w.loc[cont, "quantity0"].sum(), w.loc[cont, "quantity1"].sum()
    ratio = q1c / q0c
    safe_q0 = w["quantity0"].where(w["quantity0"] > 0, np.nan)

    out = pd.DataFrame(index=w.index)
    out["q0"], out["q1"], out["margin0"], out["margin1"] = w["quantity0"], w["quantity1"], w["margin0"], w["margin1"]
    out["delta_margin"] = w["margin1"] - w["margin0"]
    out["volume_effect"] = np.where(cont, (ratio - 1) * w["margin0"], 0.0)
    out["mix_effect"] = np.where(cont, w["quantity1"] * w["margin0"] / safe_q0 - w["margin0"] * ratio, 0.0)
    out["price_effect"] = np.where(cont, w["gross_amount1"] - w["quantity1"] * w["gross_amount0"] / safe_q0, 0.0)
    out["discount_effect"] = np.where(cont, -(w["discount_amount1"] - w["quantity1"] * w["discount_amount0"] / safe_q0), 0.0)
    out["cost_effect"] = np.where(cont, -(w["cogs1"] - w["quantity1"] * w["cogs0"] / safe_q0), 0.0)
    out["new_effect"] = np.where(w["quantity0"] == 0, w["margin1"], 0.0)
    out["discontinued_effect"] = np.where(w["quantity1"] == 0, -w["margin0"], 0.0)
    return out.reset_index()


def bridge(lines: pd.DataFrame) -> pd.Series:
    """Pont agrégé : marge P0 + effets = marge P1."""
    s = lines[EFFECTS].sum()
    s["margin0"], s["margin1"] = lines["margin0"].sum(), lines["margin1"].sum()
    return s


def identity_gap(lines: pd.DataFrame) -> float:
    """Écart absolu entre (marge P1 - marge P0) et la somme des effets ; doit être ~0 (arrondis flottants)."""
    return float(abs((lines["margin1"] - lines["margin0"]).sum() - lines[EFFECTS].sum().sum()))
