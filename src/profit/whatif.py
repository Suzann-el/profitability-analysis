"""Simulations « et si ». Fonctions pures, testables, avec hypothèses EXPLICITES en paramètres.

Trois leviers, tous appliqués à un ensemble de lignes défini par l'analyse (ex. les (sku, canal) à marge négative) :
  1. hausse de prix (avec élasticité de la demande) ;
  2. règles de remise (plafond, ou « pas de remise sous le coût ») ;
  3. arrêt des ventes à perte (dépend de la part du coût réellement évitable).

Ce sont des SCÉNARIOS, pas des prévisions : l'élasticité et la part de coût variable ne sont pas dans les données.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class Segment:
    """Agrégats d'un ensemble de lignes : ventes nettes (revenue) et coût standard des ventes (cogs)."""
    revenue: float
    cogs: float

    @property
    def margin(self) -> float:
        return self.revenue - self.cogs


# ------------------------------------------------------------------ 1. hausse de prix
def price_change(seg: Segment, x: float, elasticity: float, variable_cost_share: float = 1.0) -> float:
    """Variation de marge (de contribution si variable_cost_share < 1) après une hausse de prix de x.

    Volumes : (1 + e·x), plancher à 0. Prix unitaire : (1 + x). Coût unitaire inchangé ; seule la part `v` du coût
    est évitée quand les volumes baissent :
        ΔM = R·[(1+e·x)(1+x) - 1] - v·C·e·x           (avec e·x >= -1)
    """
    vol = max(0.0, 1.0 + elasticity * x)
    return seg.revenue * (vol * (1 + x) - 1) - variable_cost_share * seg.cogs * (vol - 1)


def break_even_elasticity(seg: Segment, x: float, variable_cost_share: float = 1.0) -> float | None:
    """Élasticité la plus négative que la hausse x tolère avant de détruire de la marge (ΔM = 0).

    None = aucune limite : la hausse améliore la marge quelle que soit l'élasticité (cas typique d'un ensemble vendu à perte).
    """
    denom = seg.revenue * (1 + x) - variable_cost_share * seg.cogs
    if denom <= 0:
        return None
    e = -seg.revenue / denom
    return e if e * x >= -1 else None


def price_grid(seg: Segment, xs, elasticities, variable_cost_share: float = 1.0) -> pd.DataFrame:
    return pd.DataFrame({e: [price_change(seg, x, e, variable_cost_share) for x in xs] for e in elasticities},
                        index=pd.Index(list(xs), name="hausse_prix"))


# ------------------------------------------------------------------ 2. règles de remise
def discount_rule(lines: pd.DataFrame, rule: str, cap: float | None = None, lost_volume_share: float = 0.0) -> dict:
    """Retire tout ou partie de la remise sur les lignes visées ; une part `lost_volume_share` des unités visées est perdue.

    rule='no_discount_below_cost' : pas de remise sur les lignes dont la marge AVANT remise est déjà négative.
    rule='cap'                    : remise plafonnée à `cap` (ex. 0,10) du montant brut, sur toutes les lignes.
    Colonnes requises : gross_amount, discount_amount, margin_before_discount, gross_margin.
    """
    d = lines[lines["discount_amount"] > 0].copy()
    if rule == "no_discount_below_cost":
        d = d[d["margin_before_discount"] < 0]
        removed = d["discount_amount"]
    elif rule == "cap":
        if cap is None:
            raise ValueError("cap requis pour rule='cap'")
        removed = (d["discount_amount"] - cap * d["gross_amount"]).clip(lower=0)
        d = d[removed > 0]
        removed = removed[removed > 0]
    else:
        raise ValueError(f"règle inconnue : {rule}")
    margin_now = float(d["gross_margin"].sum())
    margin_after = (1 - lost_volume_share) * (margin_now + float(removed.sum()))
    return {"rule": rule, "lines": int(len(d)), "discount_removed": float(removed.sum()),
            "margin_delta": margin_after - margin_now, "lost_volume_share": lost_volume_share}


# ------------------------------------------------------------------ 3. arrêt des ventes à perte
def stop_selling(seg: Segment, variable_cost_share: float) -> float:
    """Variation de marge de contribution si on cesse de vendre : on perd le revenu R, on évite la part v du coût.
        ΔM = v·C - R    (> 0 seulement si une part suffisante du coût est évitable)"""
    return variable_cost_share * seg.cogs - seg.revenue


def break_even_variable_share(seg: Segment) -> float:
    """Part minimale du coût standard qui doit être évitable pour que l'arrêt soit rentable : R / C."""
    return seg.revenue / seg.cogs
