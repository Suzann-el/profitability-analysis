"""Graphiques (matplotlib) pour le tableau de bord, la note et le README. Libellés en français."""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from .db import Warehouse  # noqa: E402

C_NET, C_RES, C_INT = "#1d3557", "#e76f51", "#2a9d8f"
C_POS, C_NEG, C_GREY = "#2d6a4f", "#c1121f", "#8d99ae"
plt.rcParams.update({"figure.dpi": 140, "font.size": 9, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.grid": True, "grid.alpha": 0.25, "axes.axisbelow": True, "axes.titleweight": "bold"})


def fr(x: float, nd: int = 1) -> str:
    return f"{x:,.{nd}f}".replace(",", " ").replace(".", ",")


def musd(x: float, nd: int = 1, sign: bool = False) -> str:
    s = fr(x / 1e6, nd)
    return (("+" if x > 0 else "") if sign else "") + s + " M$"


def _save(fig, path: Path):
    fig.tight_layout()
    fig.savefig(path, dpi=140, bbox_inches="tight")
    plt.close(fig)
    return path


# ------------------------------------------------------------------ 1. KPI par canal
def kpi_channels(res: dict, path: Path):
    k = res["kpi"]
    fig, ax = plt.subplots(1, 2, figsize=(9, 3.4))
    chans = ["Internet", "Revendeurs"]
    x = np.arange(2)
    for i, (p, lab, col) in enumerate((("P0", res["periods"]["p0"], C_GREY), ("P1", res["periods"]["p1"], C_NET))):
        m = [k[p][c]["gross_margin"] / 1e6 for c in chans]
        pc = [k[p][c]["margin_pct"] for c in chans]
        b = ax[0].bar(x + (i - .5) * .36, m, .36, color=col, label=lab)
        ax[0].bar_label(b, [fr(v, 2) for v in m], fontsize=8, padding=2)
        b2 = ax[1].bar(x + (i - .5) * .36, pc, .36, color=col, label=lab)
        ax[1].bar_label(b2, [fr(v, 1) + " %" for v in pc], fontsize=8, padding=2)
    for a, t in zip(ax, ("Marge brute (M$)", "Taux de marge brute (%)")):
        a.set_xticks(x, chans); a.set_title(t); a.axhline(0, color="black", lw=.8)
    ax[0].legend(frameon=False, fontsize=8)
    return _save(fig, path)


# ------------------------------------------------------------------ 2. Évolution mensuelle
def monthly(wh: Warehouse, path: Path, res: dict | None = None):
    m = wh.query("kpi_monthly")
    m = m[(m.year_month >= "2011-01") & (m.year_month <= "2013-11")]
    fig, ax = plt.subplots(1, 2, figsize=(10.5, 3.5))
    for ch, col in (("Revendeurs", C_RES), ("Internet", C_INT)):
        d = m[m.channel == ch]
        ax[0].plot(pd.to_datetime(d.year_month), d.net_sales / 1e6, color=col, label=ch, lw=1.8)
        ax[1].plot(pd.to_datetime(d.year_month), d.margin_pct.clip(lower=-15), color=col, label=ch, lw=1.8)
    worst = m[(m.channel == "Revendeurs")].nsmallest(1, "margin_pct").iloc[0]
    if worst.margin_pct < -15:                     # valeur aberrante : axe borné, point annoté
        ax[1].annotate(f"{worst.year_month} : {fr(worst.margin_pct, 0)} %\n(soldes Mountain-100, hors fenêtres P0/P1)",
                       (pd.to_datetime(worst.year_month), -15), (25, 12), textcoords="offset points", fontsize=7.5,
                       arrowprops=dict(arrowstyle="->"))
    for a in ax:
        a.axvspan(pd.Timestamp("2011-12-01"), pd.Timestamp("2012-11-30"), color=C_GREY, alpha=.13)
        a.axvspan(pd.Timestamp("2012-12-01"), pd.Timestamp("2013-11-30"), color=C_NET, alpha=.10)
        a.tick_params(axis="x", rotation=30)
    ax[0].set_title("Ventes nettes mensuelles (M$)"); ax[1].set_title("Taux de marge brute mensuel (%, axe borné à -15 %)")
    ax[1].axhline(0, color="black", lw=.8); ax[0].legend(frameon=False, loc="upper left")
    ax[0].text(pd.Timestamp("2012-02-01"), ax[0].get_ylim()[1] * .93, "P0", fontsize=8, color=C_GREY)
    ax[0].text(pd.Timestamp("2013-02-01"), ax[0].get_ylim()[1] * .93, "P1", fontsize=8, color=C_NET)
    return _save(fig, path)


# ------------------------------------------------------------------ 3-4. Waterfall du pont de marge
def _waterfall(ax, labels, values, title=""):
    """Cascade : première et dernière barres = totaux (depuis 0), les autres flottent. Étiquettes hors des barres."""
    n, cum = len(values), 0.0
    bottoms, heights, colors, tops, lows = [], [], [], [], []
    for i, v in enumerate(values):
        if i in (0, n - 1):
            lo, hi, col = min(0.0, v), max(0.0, v), C_NET
            cum = v if i == 0 else cum
        else:
            lo, hi, col = min(cum, cum + v), max(cum, cum + v), (C_POS if v >= 0 else C_NEG)
            cum += v
        bottoms.append(lo); heights.append(hi - lo); colors.append(col); tops.append(hi); lows.append(lo)
    ax.bar(range(n), heights, bottom=bottoms, color=colors, width=.62)
    span = (max(tops) - min(lows + [0.0])) or 1.0
    for i, v in enumerate(values):
        total = i in (0, n - 1)
        txt = musd(v, 2, sign=not total)
        if v >= 0 or not total:
            ax.text(i, tops[i] + span * .015, txt, ha="center", va="bottom", fontsize=7.5)
        else:                                            # total négatif : étiquette sous la barre
            ax.text(i, lows[i] - span * .015, txt, ha="center", va="top", fontsize=7.5)
    ax.set_ylim(min(lows + [0.0]) - span * (.12 if min(lows) < 0 else 0), max(tops) + span * .12)
    ax.set_xticks(range(n), labels, rotation=25, ha="right", fontsize=8)
    ax.set_title(title); ax.axhline(0, color="black", lw=.8)
    ax.yaxis.set_major_formatter(lambda v, _: fr(v / 1e6, 1))
    ax.set_ylabel("M$")


def waterfall_bridge(res: dict, path: Path):
    b = res["bridge"]
    fig, ax = plt.subplots(figsize=(9.5, 4))
    labels = [r["step"].replace("Marge P0", f"Marge\n{res['periods']['p0']}").replace("Marge P1", f"Marge\n{res['periods']['p1']}") for r in b]
    _waterfall(ax, labels, [r["value"] for r in b], title="Pont de marge brute : de P0 à P1 (prix / volume / mix)")
    return _save(fig, path)


def waterfall_channels(res: dict, path: Path):
    cols = [("margin_p0", "Marge P0"), ("volume", "Volume"), ("mix", "Mix"), ("price", "Prix"), ("discounts", "Remises"),
            ("cost", "Coût"), ("new_products", "Nouveaux"), ("discontinued", "Arrêtés"), ("margin_p1", "Marge P1")]
    fig, ax = plt.subplots(1, 2, figsize=(11, 3.8))
    for a, ch in zip(ax, ("Internet", "Revendeurs")):
        r = next(x for x in res["bridge_by_channel"] if x["channel"] == ch)
        _waterfall(a, [l for _, l in cols], [r[c] for c, _ in cols], title=ch)
    return _save(fig, path)


# ------------------------------------------------------------------ 5. Structure de prix
def price_structure(res: dict, path: Path):
    ps = [r for r in res["price_structure"] if r["category"] in ("Bikes", "Clothing", "Accessories", "Total")]
    ps.sort(key=lambda r: r["category"] == "Total")
    labels = [r["category"].replace("Total", "Ensemble") for r in ps]
    fig, ax = plt.subplots(1, 2, figsize=(9, 3.3))
    x = np.arange(len(ps))
    b = ax[0].bar(x, [r["reseller_price_pct_of_internet"] for r in ps], color=C_RES)
    ax[0].bar_label(b, [fr(r["reseller_price_pct_of_internet"], 0) + " %" for r in ps], fontsize=8)
    ax[0].set_title("Prix revendeur, en % du prix Internet\n(mêmes références)"); ax[0].set_ylim(0, 100)
    vals = [r["cogs_pct_of_reseller_price"] for r in ps]
    b = ax[1].bar(x, vals, color=[C_NEG if v > 100 else C_GREY for v in vals])
    ax[1].bar_label(b, [fr(v, 0) + " %" for v in vals], fontsize=8)
    ax[1].axhline(100, color="black", ls="--", lw=1); ax[1].text(-0.45, 111, "seuil de rentabilité (coût = prix)", ha="left", fontsize=8)
    ax[1].set_title("Coût standard, en % du prix revendeur"); ax[1].set_ylim(0, 125)
    for a in ax:
        a.set_xticks(x, labels)
    return _save(fig, path)


# ------------------------------------------------------------------ 6. Marge par sous-catégorie et canal
def subcategory_margin(res: dict, path: Path):
    df = pd.DataFrame(res["subcategories_p1"])
    piv = df.pivot_table(index="subcategory", columns="channel", values="gross_margin", aggfunc="sum").fillna(0)
    piv["abs"] = piv.abs().sum(axis=1)
    piv = piv.sort_values("abs", ascending=False).head(10).drop(columns="abs").sort_values("Revendeurs")
    fig, ax = plt.subplots(figsize=(8, 4))
    y = np.arange(len(piv))
    ax.barh(y + .2, piv["Revendeurs"] / 1e6, .4, color=C_RES, label="Revendeurs")
    ax.barh(y - .2, piv["Internet"] / 1e6, .4, color=C_INT, label="Internet")
    ax.set_yticks(y, piv.index); ax.axvline(0, color="black", lw=.8); ax.legend(frameon=False)
    ax.set_title("Marge brute par sous-catégorie et canal (M$) — les 10 plus importantes en valeur absolue")
    return _save(fig, path)


# ------------------------------------------------------------------ 7. Pareto
def pareto(wh: Warehouse, path: Path):
    p = wh.con.execute("SELECT * FROM pareto_sku ORDER BY rank_margin").fetchdf()
    colors = {"A": C_POS, "B": "#95d5b2", "C": C_GREY, "D": C_NEG}
    fig, ax = plt.subplots(figsize=(8.5, 4))
    ax.plot(p["pct_of_items"], p["cum_margin_pct_of_net"], color="black", lw=1.2, zorder=3)
    for cls, g in p.groupby("abc_class"):
        ax.scatter(g["pct_of_items"], g["cum_margin_pct_of_net"], s=14, color=colors[cls], zorder=4,
                   label=f"Classe {cls} : {len(g)} réf. ({fr(100 * len(g) / len(p), 0)} %)")
    peak = p["cum_margin_pct_of_net"].max()
    ax.axhline(100, color=C_GREY, ls="--", lw=1)
    ax.annotate(f"pic à {fr(peak, 0)} % : les références rentables\nfont plus que 100 % de la marge nette",
                (p.loc[p.cum_margin_pct_of_net.idxmax(), "pct_of_items"], peak), (35, 60), textcoords="offset points",
                arrowprops=dict(arrowstyle="->"), fontsize=8)
    ax.set_xlabel("Part des références, classées par marge décroissante (%)"); ax.set_ylabel("Marge cumulée / marge nette totale (%)")
    ax.set_title("Pareto de la marge brute par référence (P1)"); ax.legend(frameon=False, fontsize=8, loc="lower right")
    return _save(fig, path)


def reseller_abc(res: dict, path: Path):
    a = pd.DataFrame(res["abc_reseller"]).set_index("abc_class")
    fig, ax = plt.subplots(figsize=(6.5, 3.4))
    cols = {"A": C_POS, "B": "#95d5b2", "C": C_GREY, "D": C_NEG}
    b = ax.bar(a.index, a["gross_margin"] / 1e6, color=[cols[i] for i in a.index])
    for i, (idx, r) in enumerate(a.iterrows()):
        v = r["gross_margin"] / 1e6
        ax.text(i, v + (.04 if v > 0 else -.04), f"{int(r['resellers'])} revendeurs\n({fr(r['pct_of_resellers'], 0)} %)",
                ha="center", va="bottom" if v > 0 else "top", fontsize=8)
    ax.axhline(0, color="black", lw=.8); ax.set_title("Marge brute par classe de revendeurs (M$, P1)")
    ax.set_ylim(a["gross_margin"].min() / 1e6 * 1.35, a["gross_margin"].max() / 1e6 * 1.6)
    return _save(fig, path)


# ------------------------------------------------------------------ 8. Remises
def discounts(res: dict, path: Path):
    d = pd.DataFrame(res["discounts"]["by_promotion"]).head(6).iloc[::-1]
    fig, ax = plt.subplots(figsize=(8.5, 3.8))
    y = np.arange(len(d))
    ax.barh(y + .2, d["margin_before"] / 1e3, .4, color=C_GREY, label="Marge AVANT remise")
    ax.barh(y - .2, d["margin_after"] / 1e3, .4, color=C_NEG, label="Marge APRÈS remise")
    ax.set_yticks(y, [f"{n}\n({fr(100 * r / g, 0)} % de remise)" for n, r, g in zip(d["promotion_name"], d["discounts"], d["gross_amount"])], fontsize=7.5)
    ax.axvline(0, color="black", lw=.8); ax.set_xlabel("k$"); ax.legend(frameon=False, fontsize=8)
    ax.set_title("Les promotions qui pèsent le plus sont accordées sur des lignes déjà à perte (P1)")
    return _save(fig, path)


# ------------------------------------------------------------------ 9-10. Simulations
def whatif_price(res: dict, path: Path):
    g = res["whatif"]["price_grid"]
    Z = np.array(g["delta"]) / 1e6
    fig, ax = plt.subplots(figsize=(6.5, 3.4))
    im = ax.imshow(Z, cmap="Greens", aspect="auto", vmin=0, vmax=Z.max() * 1.7)
    ax.set_xticks(range(len(g["elasticities"])), [f"ε = {fr(e, 0)}" for e in g["elasticities"]])
    ax.set_yticks(range(len(g["x"])), [f"+{fr(100 * x, 0)} % de prix" for x in g["x"]])
    for i in range(Z.shape[0]):
        for j in range(Z.shape[1]):
            ax.text(j, i, fr(Z[i, j], 2), ha="center", va="center", fontsize=9)
    ax.grid(False); ax.set_title("Gain de marge (M$/an) — hausse de prix sur les (réf., canal) à perte", fontsize=9)
    return _save(fig, path)


def stop_selling(res: dict, path: Path):
    s = res["whatif"]["stop_selling"]; seg = res["whatif"]["segment"]
    v = np.linspace(0.6, 1.0, 81)
    delta = (v * seg["cogs"] - seg["revenue"]) / 1e6
    fig, ax = plt.subplots(figsize=(6.5, 3.4))
    ax.plot(v * 100, delta, color=C_NET, lw=2)
    ax.axhline(0, color="black", lw=.8); ax.axvline(s["break_even_share"] * 100, color=C_NEG, ls="--")
    ax.annotate(f"seuil : {fr(100 * s['break_even_share'], 1)} % du coût\ndoit être évitable", (s["break_even_share"] * 100, 0), (18, -75),
                textcoords="offset points", arrowprops=dict(arrowstyle="->"), fontsize=8)
    ax.set_xlabel("Part du coût standard réellement évitable (%)"); ax.set_ylabel("Variation de marge (M$)")
    ax.set_title("Arrêter de vendre à perte : rentable seulement au-delà du seuil", fontsize=9)
    return _save(fig, path)


def make_all(wh: Warehouse, res: dict, out_dir: Path) -> dict[str, Path]:
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    return {
        "kpi_channels": kpi_channels(res, out / "01_kpi_channels.png"),
        "monthly": monthly(wh, out / "02_monthly.png", res),
        "waterfall": waterfall_bridge(res, out / "03_waterfall_bridge.png"),
        "waterfall_channels": waterfall_channels(res, out / "04_waterfall_channels.png"),
        "price_structure": price_structure(res, out / "05_price_structure.png"),
        "subcategory": subcategory_margin(res, out / "06_margin_subcategory.png"),
        "pareto": pareto(wh, out / "07_pareto_sku.png"),
        "reseller_abc": reseller_abc(res, out / "08_reseller_abc.png"),
        "discounts": discounts(res, out / "09_discounts.png"),
        "whatif_price": whatif_price(res, out / "10_whatif_price.png"),
        "stop_selling": stop_selling(res, out / "11_stop_selling.png"),
    }
