"""Tableau de bord HTML autonome (un seul fichier, images intégrées) : 4 onglets, sans JavaScript.

Ce n'est PAS un fichier Power BI (.pbix) : il reprend la même structure de pages pour la lecture rapide et la démonstration ;
`powerbi/` explique comment reconstruire les pages dans Power BI à partir des exports CSV.
"""
from __future__ import annotations

import base64
import html
from pathlib import Path

import pandas as pd

from .charts import fr, musd


def _img(path: Path, alt: str) -> str:
    b64 = base64.b64encode(Path(path).read_bytes()).decode()
    return f'<figure><img alt="{html.escape(alt)}" src="data:image/png;base64,{b64}"><figcaption>{html.escape(alt)}</figcaption></figure>'


def _table(rows: list[dict], cols: list[tuple[str, str, callable]]) -> str:
    head = "".join(f"<th>{h}</th>" for _, h, _ in cols)
    body = ""
    for r in rows:
        tds = ""
        for key, _, f in cols:
            v = r.get(key)
            cls = ""
            if isinstance(v, (int, float)) and v is not None and key.endswith(("margin", "gross_margin", "margin_after", "margin_before", "delta")):
                cls = ' class="neg"' if v < 0 else ""
            tds += f"<td{cls}>{html.escape(str(f(v))) if v is not None else '—'}</td>"
        body += f"<tr>{tds}</tr>"
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def _card(label: str, value: str, sub: str = "", bad: bool = False) -> str:
    return f'<div class="card{" bad" if bad else ""}"><div class="lab">{label}</div><div class="val">{value}</div><div class="sub">{sub}</div></div>'


CSS = """
:root{--bg:#f6f7f9;--fg:#1b2430;--muted:#6b7686;--card:#fff;--line:#e3e7ee;--accent:#1d3557;--bad:#c1121f;--good:#2d6a4f}
@media (prefers-color-scheme:dark){:root{--bg:#12161c;--fg:#e8ecf1;--muted:#9aa5b5;--card:#1b222b;--line:#2b3441;--accent:#7aa2d6;--bad:#ff6b6b;--good:#6fcf97}}
*{box-sizing:border-box}body{margin:0;font:14px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;background:var(--bg);color:var(--fg)}
header{padding:18px 24px 6px}h1{font-size:20px;margin:0}.sub0{color:var(--muted);font-size:12.5px;margin-top:2px}
.tabs{display:flex;gap:4px;padding:0 24px;border-bottom:1px solid var(--line);flex-wrap:wrap}
.tabs label{padding:9px 14px;cursor:pointer;color:var(--muted);border-bottom:3px solid transparent;font-weight:600}
input[name=tab]{display:none}.page{display:none;padding:18px 24px 30px;max-width:1150px}
#t1:checked~.tabs label[for=t1],#t2:checked~.tabs label[for=t2],#t3:checked~.tabs label[for=t3],#t4:checked~.tabs label[for=t4]{color:var(--accent);border-color:var(--accent)}
#t1:checked~#p1,#t2:checked~#p2,#t3:checked~#p3,#t4:checked~#p4{display:block}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:12px;margin-bottom:16px}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 14px}.card.bad{border-color:var(--bad)}
.lab{font-size:11.5px;color:var(--muted);text-transform:uppercase;letter-spacing:.03em}.val{font-size:24px;font-weight:700}.sub{font-size:12px;color:var(--muted)}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(420px,1fr));gap:16px}
figure{margin:0;background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px}figure img{width:100%;height:auto;display:block;background:#fff;border-radius:6px}
figcaption{font-size:11.5px;color:var(--muted);margin-top:4px}
table{border-collapse:collapse;width:100%;background:var(--card);border:1px solid var(--line);border-radius:10px;overflow:hidden;font-size:12.5px;margin:6px 0 16px}
th,td{padding:6px 9px;text-align:right;border-bottom:1px solid var(--line)}th:first-child,td:first-child{text-align:left}th{background:var(--bg);font-weight:600}
td.neg{color:var(--bad);font-weight:600}.wrap{overflow-x:auto}h2{font-size:15px;margin:18px 0 6px}
.note{background:var(--card);border-left:4px solid var(--accent);padding:10px 14px;border-radius:6px;margin:10px 0;font-size:13px}
.note.warn{border-color:var(--bad)}footer{padding:14px 24px;color:var(--muted);font-size:12px;max-width:1150px}
"""


def build(res: dict, figs: dict[str, Path], out_path: Path) -> Path:
    k, per = res["kpi"], res["periods"]
    t1, t0 = k["P1"]["Total"], k["P0"]["Total"]
    g, pv = res["growth"], res["pricing_vs_cost"]
    lm, dsc, wi = res["loss_making"], res["discounts"], res["whatif"]

    cards = "".join([
        _card("Ventes nettes", musd(t1["net_sales"]), f"{'+' if g['net_sales_pct'] > 0 else ''}{fr(g['net_sales_pct'], 0)} % vs P0"),
        _card("Marge brute", musd(t1["gross_margin"], 2), f"{fr(t1['margin_pct'], 1)} % des ventes (P0 : {fr(t0['margin_pct'], 1)} %)"),
        _card("Marge revendeurs", musd(k["P1"]["Revendeurs"]["gross_margin"], 2), f"{fr(k['P1']['Revendeurs']['margin_pct'], 1)} % — {fr(100 * k['P1']['Revendeurs']['net_sales'] / t1['net_sales'], 0)} % du CA",
              bad=k["P1"]["Revendeurs"]["gross_margin"] < 0),
        _card("Marge Internet", musd(k["P1"]["Internet"]["gross_margin"], 2), f"{fr(k['P1']['Internet']['margin_pct'], 1)} % — {fr(g['internet_share_of_margin_pct'], 0)} % de la marge totale"),
        _card("Lignes vendues sous le coût", f"{fr(t1['pct_lines_below_cost'], 1)} %", f"perte de {musd(-t1['loss_on_below_cost_lines'], 2)} (P0 : {fr(t0['pct_lines_below_cost'], 1)} %)", bad=True),
        _card("Remises", f"{fr(t1['discount_pct_of_gross'], 2)} %", f"du brut = {musd(t1['discounts'], 2)}"),
    ])
    ch_rows = [{"c": c, **{f"{p}_{m}": k[p][c][m] for p in ("P0", "P1") for m in ("net_sales", "gross_margin", "margin_pct")}} for c in ("Internet", "Revendeurs", "Total")]
    ch_tbl = _table(ch_rows, [("c", "Canal", str), ("P0_net_sales", "Ventes P0", lambda v: musd(v)), ("P1_net_sales", "Ventes P1", lambda v: musd(v)),
                              ("P0_gross_margin", "Marge P0", lambda v: musd(v, 2)), ("P1_gross_margin", "Marge P1", lambda v: musd(v, 2)),
                              ("P0_margin_pct", "Taux P0", lambda v: fr(v, 1) + " %"), ("P1_margin_pct", "Taux P1", lambda v: fr(v, 1) + " %")])
    cat_tbl = _table(res["categories_p1"], [("category", "Catégorie", str), ("channel", "Canal", str), ("net_sales", "Ventes", lambda v: musd(v, 2)),
                                            ("gross_margin", "Marge", lambda v: musd(v, 2)), ("margin_pct", "Taux", lambda v: fr(v, 1) + " %")])

    br = res["bridge"]
    bridge_tbl = _table([{"step": r["step"], "value": r["value"]} for r in br], [("step", "Étape", str), ("value", "Montant", lambda v: musd(v, 2))])
    chan_bridge = _table(res["bridge_by_channel"], [("channel", "Canal", str), ("margin_p0", "Marge P0", lambda v: musd(v, 2)), ("volume", "Volume", lambda v: musd(v, 2)),
                         ("mix", "Mix", lambda v: musd(v, 2)), ("price", "Prix", lambda v: musd(v, 2)), ("discounts", "Remises", lambda v: musd(v, 2)),
                         ("cost", "Coût", lambda v: musd(v, 2)), ("new_products", "Nouveaux", lambda v: musd(v, 2)),
                         ("discontinued", "Arrêtés", lambda v: musd(v, 2)), ("margin_p1", "Marge P1", lambda v: musd(v, 2))])
    worst = _table(res["worst_skus"], [("product_name", "Référence", str), ("net_sales", "Ventes", lambda v: musd(v, 2)), ("gross_margin", "Marge totale", lambda v: musd(v, 2)),
                                       ("margin_resellers", "dont revendeurs", lambda v: musd(v, 2)), ("margin_internet", "dont Internet", lambda v: musd(v, 2))])
    promo = _table(dsc["by_promotion"][:6], [("promotion_name", "Promotion", str), ("discounts", "Remises", lambda v: musd(v, 3)),
                                             ("margin_before", "Marge avant", lambda v: musd(v, 2)), ("margin_after", "Marge après", lambda v: musd(v, 2))])
    sim = wi["price_grid"]
    grid = "<table><thead><tr><th>Hausse de prix</th>" + "".join(f"<th>ε = {fr(e, 0)}</th>" for e in sim["elasticities"]) + "</tr></thead><tbody>" + "".join(
        f"<tr><td>+{fr(100 * x, 0)} %</td>" + "".join(f"<td>{musd(v, 2)}</td>" for v in row) + "</tr>" for x, row in zip(sim["x"], sim["delta"])) + "</tbody></table>"
    stop = wi["stop_selling"]
    stop_tbl = "<table><thead><tr><th>Part du coût évitable</th>" + "".join(f"<th>{fr(100 * v, 0)} %</th>" for v in stop["variable_shares"]) + "</tr></thead><tbody><tr><td>Variation de marge</td>" + "".join(
        f'<td class="{"neg" if d < 0 else ""}">{musd(d, 2, sign=True)}</td>' for d in stop["delta"]) + "</tr></tbody></table>"

    html_doc = f"""<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Rentabilité et marge — tableau de bord</title><style>{CSS}</style></head><body>
<header><h1>Rentabilité et marge — tableau de bord</h1>
<div class="sub0">AdventureWorks (jeu de démonstration Microsoft) · P1 = {per['p1']} · P0 = {per['p0']} · marge brute = ventes nettes de remises − coût standard · montants en USD</div></header>
<input type="radio" name="tab" id="t1" checked><input type="radio" name="tab" id="t2"><input type="radio" name="tab" id="t3"><input type="radio" name="tab" id="t4">
<div class="tabs"><label for="t1">1 · Vue d'ensemble</label><label for="t2">2 · Pont de marge</label><label for="t3">3 · Produits &amp; revendeurs</label><label for="t4">4 · Remises &amp; simulations</label></div>

<section class="page" id="p1"><div class="cards">{cards}</div>
<div class="grid">{_img(figs['kpi_channels'], 'Marge brute et taux de marge par canal')}{_img(figs['monthly'], 'Évolution mensuelle')}</div>
<h2>Par canal</h2><div class="wrap">{ch_tbl}</div><h2>Par catégorie et canal (P1)</h2><div class="wrap">{cat_tbl}</div>
<div class="note warn"><b>Lecture.</b> Internet ({fr(g['internet_share_of_sales_pct'], 0)} % des ventes) génère {fr(g['internet_share_of_margin_pct'], 0)} % de la marge brute : les revendeurs, qui font le reste des ventes, sont à marge négative.</div></section>

<section class="page" id="p2">{_img(figs['waterfall'], 'Pont de marge brute P0 → P1')}<div class="grid"><div class="wrap">{bridge_tbl}</div>
<div class="note"><b>Comment lire.</b> Les hausses de prix catalogue ({musd(pv['bridge_price'], 2, sign=True)}) sont presque entièrement absorbées par la hausse du coût standard
({musd(pv['bridge_cost'], 2, sign=True)}). Les « nouveaux produits » (références absentes de P0) apportent {musd(next(r['value'] for r in br if r['step']=='Nouveaux produits'), 2, sign=True)} au total,
mais les revendeurs y perdent {musd(-next(r['new_products'] for r in res['bridge_by_channel'] if r['channel']=='Revendeurs'), 2)} (gamme Touring).</div></div>
{_img(figs['waterfall_channels'], 'Pont par canal')}<h2>Détail par canal</h2><div class="wrap">{chan_bridge}</div></section>

<section class="page" id="p3"><div class="grid">{_img(figs['pareto'], 'Pareto de la marge par référence')}{_img(figs['reseller_abc'], 'Classes ABC de revendeurs')}</div>
<div class="grid">{_img(figs['subcategory'], 'Marge par sous-catégorie et canal')}{_img(figs['price_structure'], 'Structure des prix')}</div>
<h2>Les 10 références les moins rentables (tous canaux)</h2><div class="wrap">{worst}</div>
<div class="note warn"><b>Piège d'agrégation.</b> Au niveau référence, certains vélos semblent rentables parce que la marge Internet compense la perte chez les revendeurs.
Au niveau (référence, canal), {lm['n']} lignes perdent {musd(-lm['margin'], 2)} sur {musd(lm['revenue'])} de ventes ({fr(lm['share_of_total_revenue_pct'], 0)} % du chiffre d'affaires), dont {fr(lm['bikes_share_of_loss_pct'], 0)} % sur les vélos.</div></section>

<section class="page" id="p4">{_img(figs['discounts'], 'Remises : marge avant / après')}
<div class="grid"><div><h2>Promotions les plus coûteuses (P1)</h2><div class="wrap">{promo}</div></div>
<div class="note"><b>Remises.</b> {fr(dsc['already_below_cost_pct'], 0)} % des remises ({musd(dsc['already_below_cost_discounts'], 2)}) sont accordées sur des lignes <i>déjà</i> à perte avant remise ;
les promotions de lancement Touring représentent {fr(dsc['new_product_promos_pct'], 0)} % des remises. La remise ne crée la perte que sur {next(p['lines'] for p in dsc['populations'] if p['population'].startswith('1'))} lignes :
le problème est le prix de base, pas la remise.</div></div>
<h2>Simulation : hausse de prix sur les {lm['n']} lignes à perte (gain de marge par an)</h2><div class="grid"><div class="wrap">{grid}</div>{_img(figs['whatif_price'], 'Gain de marge selon hausse et élasticité')}</div>
<h2>Simulation : arrêter de vendre à perte</h2><div class="grid"><div class="wrap">{stop_tbl}</div>{_img(figs['stop_selling'], 'Arrêt des ventes à perte')}</div>
<div class="note warn"><b>Garde-fou.</b> Arrêter ces ventes ne devient rentable que si au moins {fr(100 * stop['break_even_share'], 1)} % du coût standard est réellement évitable ; en dessous, on détruit de la marge de contribution.
Relever le prix, lui, améliore la marge quelle que soit l'élasticité testée.</div></section>
<footer>Données : AdventureWorksDW (Microsoft, licence MIT), jeu fictif de démonstration. Un canal à marge négative est atypique d'une entreprise réelle : ce résultat reflète la construction du jeu
(prix revendeur = 60 % du prix catalogue, coûts standard de 55 à 62 %). Les simulations sont des scénarios, pas des prévisions. Généré par <code>python -m profit build</code>.</footer></body></html>"""
    out = Path(out_path)
    out.write_text(html_doc, encoding="utf-8")
    return out
