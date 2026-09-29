"""Test de mutation : injecte des bugs réalistes dans une COPIE du projet et vérifie que la suite de tests les détecte.

Usage : python scripts/mutation_check.py [--only N,N,...]
Un mutant « survit » si tous les tests passent malgré le bug : c'est un trou dans la suite de tests.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

MUTANTS = [
    # (fichier, ancien texte, nouveau texte, description)
    ("sql/04_pvm.sql", "m.q1 * m.margin0 / m.q0 - m.margin0 * tot.q1c / tot.q0c", "m.q1 * m.margin0 / m.q0 + m.margin0 * tot.q1c / tot.q0c", "PVM : signe de l'effet mix inversé"),
    ("sql/04_pvm.sql", "m.gross1 - m.q1 * m.gross0 / m.q0", "m.gross1 - m.q0 * m.gross0 / m.q0", "PVM : effet prix valorisé sur les quantités P0"),
    ("sql/04_pvm.sql", "-(m.cogs1 - m.q1 * m.cogs0 / m.q0)", "(m.cogs1 - m.q1 * m.cogs0 / m.q0)", "PVM : signe de l'effet coût inversé"),
    ("sql/04_pvm.sql", "(tot.q1c / tot.q0c - 1) * m.margin0", "(tot.q1c / tot.q0c) * m.margin0", "PVM : effet volume sans le « -1 »"),
    ("sql/04_pvm.sql", "WHEN m.q0 = 0 THEN m.margin1 ELSE 0 END AS new_effect", "WHEN m.q0 = 0 THEN m.net1 ELSE 0 END AS new_effect", "PVM : nouveaux produits = ventes au lieu de marge"),
    ("sql/04_pvm.sql", "WHEN m.q1 = 0 THEN -m.margin0 ELSE 0 END AS discontinued_effect", "WHEN m.q1 = 0 THEN m.margin0 ELSE 0 END AS discontinued_effect", "PVM : signe des produits arrêtés inversé"),
    ("sql/05_pareto.sql", "WHEN COALESCE(cum_before, 0) < 0.80 * total_positive_margin THEN 'A'", "WHEN COALESCE(cum_before, 0) < 0.90 * total_positive_margin THEN 'A'", "ABC : seuil de la classe A à 90 % au lieu de 80 %"),
    ("sql/05_pareto.sql", "CASE WHEN gross_margin < 0 THEN 'D'", "CASE WHEN gross_margin < -50000 THEN 'D'", "ABC : classe D trop restrictive"),
    ("sql/03_kpis.sql", "ROUND(100.0 * SUM(gross_margin) / SUM(net_sales), 2) AS margin_pct,\n       ROUND(SUM(gross_amount), 0)", "ROUND(100.0 * SUM(gross_margin) / SUM(cogs), 2) AS margin_pct,\n       ROUND(SUM(gross_amount), 0)", "KPI : taux de marge divisé par le coût"),
    ("sql/03_kpis.sql", "AND DATE '${P1_END}';", "AND DATE '${P1_END}' - INTERVAL 1 DAY;", "Fenêtre P1 : dernier jour exclu"),
    ("sql/01_model.sql", "u.gross_amount - u.cogs AS margin_before_discount", "u.net_sales - u.cogs AS margin_before_discount", "Modèle : marge avant remise = marge après remise"),
    ("sql/01_model.sql", "TotalProductCost, SalesAmount\n  FROM stg_fact_internet_sales", "TotalProductCost, ExtendedAmount\n  FROM stg_fact_internet_sales", "Modèle : revenu Internet pris brut avant remises"),
    ("sql/01_model.sql", "FROM ranked WHERE rn = 1;", "FROM ranked WHERE rn <= 2;", "Modèle : dim_sku avec doublons (fan-out des jointures)"),
    ("sql/06_discounts.sql", "WHEN margin_before_discount < 0 THEN '2 - déjà à perte avant remise'", "WHEN margin_before_discount < 500 THEN '2 - déjà à perte avant remise'", "Remises : population « déjà à perte » élargie"),
    ("sql/02_quality.sql", "WHERE ABS(net_sales - (gross_amount - discount_amount)) > 0.01;", "WHERE ABS(net_sales - (gross_amount - discount_amount)) > 1000000;", "Qualité : contrôle d'identité neutralisé"),
    ("src/profit/whatif.py", "- variable_cost_share * seg.cogs * (vol - 1)", "", "What-if : coût évité oublié dans la hausse de prix"),
    ("src/profit/whatif.py", "return seg.revenue / seg.cogs", "return seg.cogs / seg.revenue", "What-if : seuil de coût évitable inversé"),
    ("src/profit/whatif.py", 'removed = (d["discount_amount"] - cap * d["gross_amount"]).clip(lower=0)', 'removed = (cap * d["gross_amount"] - d["discount_amount"]).clip(lower=0)', "What-if : plafond de remise inversé"),
    ("src/profit/pvm.py", 'out["mix_effect"] = np.where(cont, w["quantity1"] * w["margin0"] / safe_q0 - w["margin0"] * ratio, 0.0)', 'out["mix_effect"] = np.where(cont, w["quantity1"] * w["margin0"] / safe_q0 + w["margin0"] * ratio, 0.0)', "PVM pandas : signe du mix inversé"),
    ("src/profit/results.py", '"net_sales_pct": 100 * (p1["Total"]["net_sales"] / p0["Total"]["net_sales"] - 1)', '"net_sales_pct": 100 * (p0["Total"]["net_sales"] / p1["Total"]["net_sales"] - 1)', "Résultats : croissance des ventes inversée"),
]


def run_mutant(i: int, spec: tuple) -> tuple[bool, str]:
    f, old, new, _ = spec
    with tempfile.TemporaryDirectory() as tmp:
        dst = Path(tmp) / "p"
        for d in ("src", "sql", "tests", "scripts"):
            shutil.copytree(ROOT / d, dst / d, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"))
        (dst / "data").mkdir()
        shutil.copy(ROOT / "data" / "manifest.json", dst / "data")
        os.symlink(ROOT / "data" / "raw", dst / "data" / "raw")
        shutil.copy(ROOT / "pyproject.toml", dst)
        text = (dst / f).read_text(encoding="utf-8")
        if old not in text:
            return False, "MOTIF INTROUVABLE (mutant invalide)"
        (dst / f).write_text(text.replace(old, new, 1), encoding="utf-8")
        r = subprocess.run([sys.executable, "-m", "pytest", "-x", "-q", "-p", "no:cacheprovider"], cwd=dst, capture_output=True, text=True,
                           env={**os.environ, "PYTHONPATH": str(dst / "src"), "PYTHONDONTWRITEBYTECODE": "1"})
        out = r.stdout + r.stderr
        killed = r.returncode != 0
        first = next((l for l in out.splitlines() if l.startswith(("FAILED", "ERROR"))), "")
        return killed, first[:110]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    a = ap.parse_args()
    only = {int(x) for x in a.only.split(",") if x} or set(range(1, len(MUTANTS) + 1))
    survivors = 0
    for i, spec in enumerate(MUTANTS, 1):
        if i not in only:
            continue
        killed, why = run_mutant(i, spec)
        status = "TUÉ     " if killed else "SURVIT  "
        if not killed:
            survivors += 1
        print(f"[{i:2d}] {status} {spec[3]}\n      -> {why}", flush=True)
    print(f"\n{len(only) - survivors}/{len(only)} mutants détectés ; {survivors} survivant(s)")
    return 1 if survivors else 0


if __name__ == "__main__":
    sys.exit(main())
