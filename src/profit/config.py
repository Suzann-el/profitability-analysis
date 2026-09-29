"""Fenêtres d'analyse et chemins. Une seule source de vérité pour les périodes P0 / P1."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SQL_DIR = ROOT / "sql"
RAW_DIR = ROOT / "data" / "raw"
EXPORT_DIR = ROOT / "exports"
REPORT_DIR = ROOT / "reports"

# 12 mois glissants alignés sur la dernière date disponible des DEUX canaux (revendeurs : 29/11/2013).
PARAMS = {
    "P0_START": "2011-12-01", "P0_END": "2012-11-30",
    "P1_START": "2012-12-01", "P1_END": "2013-11-30",
}
P0_LABEL, P1_LABEL = "12 mois à nov. 2012", "12 mois à nov. 2013"
