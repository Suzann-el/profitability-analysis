"""Livrables : cohérence du JSON, graphiques, tableau de bord (autonome), exports (sans données personnelles), note Word."""
from __future__ import annotations

import csv
import json
import re
import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest

from profit import charts, dashboard, export
from profit.charts import fr, musd

ROOT = Path(__file__).resolve().parents[1]


# ------------------------------------------------------------------ résultats
def test_results_are_consistent(results):
    k, b = results["kpi"], {r["step"]: r["value"] for r in results["bridge"]}
    assert b["Marge P0"] == pytest.approx(k["P0"]["Total"]["gross_margin"], abs=1)
    assert b["Marge P1"] == pytest.approx(k["P1"]["Total"]["gross_margin"], abs=1)
    steps = ["Volume", "Mix produits/canaux", "Prix catalogue", "Remises", "Coût standard", "Nouveaux produits", "Produits arrêtés"]
    assert b["Marge P0"] + sum(b[s] for s in steps) == pytest.approx(b["Marge P1"], abs=8), "le pont se referme (arrondis à l'unité sur 9 étapes)"
    for p in ("P0", "P1"):
        assert k[p]["Internet"]["gross_margin"] + k[p]["Revendeurs"]["gross_margin"] == pytest.approx(k[p]["Total"]["gross_margin"], abs=2)
    g = results["growth"]
    assert g["net_sales_pct"] == pytest.approx(100 * (k["P1"]["Total"]["net_sales"] / k["P0"]["Total"]["net_sales"] - 1))


def test_results_whatif_matches_definitions(results):
    w, lm = results["whatif"], results["loss_making"]
    assert w["segment"]["margin"] == pytest.approx(lm["margin"], abs=1) and lm["margin"] < 0
    assert w["stop_selling"]["break_even_share"] == pytest.approx(w["segment"]["revenue"] / w["segment"]["cogs"])
    # ε = 0, +5 % de prix -> gain = 5 % du revenu ciblé
    x = w["price_grid"]["x"].index(0.05)
    assert w["price_grid"]["delta"][x][0] == pytest.approx(0.05 * w["segment"]["revenue"])
    assert all(v is None for v in w["price_break_even_elasticity"].values()), "ensemble à perte : aucune élasticité critique"


def test_results_json_is_serializable(results):
    json.loads(json.dumps(results, default=float))


# ------------------------------------------------------------------ graphiques + tableau de bord
@pytest.fixture(scope="module")
def built(wh, results, tmp_path_factory):
    d = tmp_path_factory.mktemp("out")
    figs = charts.make_all(wh, results, d / "figures")
    html = dashboard.build(results, figs, d / "dashboard.html")
    return figs, html


def test_all_figures_are_written_and_nonempty(built):
    figs, _ = built
    assert len(figs) == 11
    for name, p in figs.items():
        assert p.exists() and p.stat().st_size > 8_000, name
        assert p.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_dashboard_is_self_contained_with_four_tabs(built, results):
    _, html = built
    t = html.read_text(encoding="utf-8")
    assert len(re.findall(r'<input type="radio" name="tab"', t)) == 4 and t.count("<section class=\"page\"") == 4
    assert not re.findall(r'(?:src|href)="https?://', t), "aucune ressource externe"
    assert not re.findall(r"<script", t), "sans JavaScript"
    assert t.count("data:image/png;base64,") == 11
    p1 = results["kpi"]["P1"]["Total"]
    assert musd(p1["gross_margin"], 2) in t and fr(p1["margin_pct"], 1) in t, "chiffres clés du JSON présents"
    assert musd(results["loss_making"]["margin"] * -1, 2) in t


def test_fr_formatting():
    assert fr(1234567.891, 1) == "1 234 567,9" and fr(-2.5, 1) == "-2,5" and musd(1_990_108, 2) == "1,99 M$"
    assert musd(2_380_714, 2, sign=True) == "+2,38 M$" and musd(-673_727, 2, sign=True) == "-0,67 M$"


# ------------------------------------------------------------------ exports
def test_export_row_counts_and_no_personal_data(wh, tmp_path):
    counts = export.export_all(wh, tmp_path)
    assert counts["fact_sales"] == wh.con.execute("SELECT COUNT(*) FROM fact_sales").fetchone()[0]
    for f in tmp_path.glob("*.csv"):
        header = next(csv.reader(open(f, encoding="utf-8")))
        low = [h.lower() for h in header]
        assert not [h for h in low if any(bad in h for bad in ("email", "phone", "first", "last_name", "birth", "address", "yearlyincome"))], (f.name, header)
    assert {"fact_sales.csv", "dim_product.csv", "pvm_lines.csv", "pareto_sku.csv", "kpi_monthly.csv", "pvm_bridge.csv"} <= {f.name for f in tmp_path.glob("*.csv")}


def test_exported_fact_reconciles_with_model(wh, tmp_path):
    export.export_all(wh, tmp_path)
    import duckdb
    n, s, c = duckdb.connect().execute(f"SELECT COUNT(*), SUM(net_sales), SUM(cogs) FROM read_csv_auto('{(tmp_path / 'fact_sales.csv').as_posix()}')").fetchone()
    n0, s0, c0 = wh.con.execute("SELECT COUNT(*), SUM(net_sales), SUM(cogs) FROM fact_sales").fetchone()
    assert (n, float(s), float(c)) == (n0, pytest.approx(float(s0), abs=1), pytest.approx(float(c0), abs=1))


# ------------------------------------------------------------------ note Word
NODE = shutil.which("node")


@pytest.mark.skipif(not NODE or not (ROOT / "reports" / "results.json").exists() or not (ROOT / "reports" / "figures" / "03_waterfall_bridge.png").exists(),
                    reason="Node ou artefacts de build absents (lancer `python -m profit build`)")
def test_note_contains_the_numbers_of_results_json():
    subprocess.run([NODE, str(ROOT / "note" / "build_note.js")], cwd=ROOT / "note", check=True, capture_output=True)
    res = json.loads((ROOT / "reports" / "results.json").read_text())
    with zipfile.ZipFile(ROOT / "reports" / "note_synthese.docx") as z:
        xml = z.read("word/document.xml").decode("utf-8")
    text = re.sub(r"<[^>]+>", "", xml).replace("\u00a0", " ").replace("\u2212", "-")
    p1 = res["kpi"]["P1"]
    assert fr(p1["Total"]["gross_margin"] / 1e6, 2) in text and fr(p1["Revendeurs"]["gross_margin"] / 1e6, 2) in text
    assert fr(res["whatif"]["stop_selling"]["break_even_share"] * 100, 1) in text
    assert str(res["loss_making"]["n"]) in text
    for reco in ("1. Relever", "2. Interdire", "3. Indexer", "4. Prioriser"):
        assert reco in text


def test_note_script_refuses_stale_results(tmp_path):
    if not NODE:
        pytest.skip("Node absent")
    proj = tmp_path / "p"; (proj / "note").mkdir(parents=True); (proj / "reports").mkdir()
    shutil.copy(ROOT / "note" / "build_note.js", proj / "note")
    (proj / "reports" / "results.json").write_text(json.dumps({"kpi": {}}))
    env_path = subprocess.run(["npm", "root", "-g"], capture_output=True, text=True).stdout.strip()
    r = subprocess.run([NODE, str(proj / "note" / "build_note.js")], capture_output=True, text=True, env={"NODE_PATH": env_path, "PATH": "/usr/bin:/bin"})
    assert r.returncode != 0 and "obsolète" in r.stderr
