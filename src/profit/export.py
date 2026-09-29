"""Exports CSV pour Power BI / Tableau : modèle en étoile complet + tables d'analyse pré-calculées en SQL.

Aucune donnée personnelle (les colonnes nom / e-mail / adresse / téléphone / naissance ne sont jamais chargées).
"""
from __future__ import annotations

from pathlib import Path

from .db import Warehouse

TABLES = ["dim_date", "dim_product", "dim_sku", "dim_territory", "dim_customer", "dim_reseller", "dim_promotion", "dim_channel",
          "fact_sales", "pvm_lines", "pareto_sku", "pareto_reseller"]


def export_all(wh: Warehouse, out_dir: Path) -> dict[str, int]:
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    counts = {}
    for t in TABLES:
        wh.con.execute(f"COPY (SELECT * FROM {t}) TO '{(out / (t + '.csv')).as_posix()}' (HEADER, DELIMITER ',')")
        counts[t] = wh.con.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
    wh.query("kpi_monthly").to_csv(out / "kpi_monthly.csv", index=False)
    wh.query("pvm_bridge").to_csv(out / "pvm_bridge.csv", index=False)
    wh.query("kpi_by_calendar_year").to_csv(out / "kpi_by_calendar_year.csv", index=False)
    return counts
