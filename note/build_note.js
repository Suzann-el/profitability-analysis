// Génère reports/note_synthese.docx (2 pages A4) à partir de reports/results.json.
// AUCUN chiffre n'est saisi ici : tout vient de results.json (donc du SQL). Le texte des recommandations est écrit à la main,
// ses valeurs sont injectées ; si les données changent, relire le texte (les tests vérifient les chiffres, pas la prose).
const fs = require("fs");
const path = require("path");
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell, WidthType, ShadingType, AlignmentType,
  ImageRun, BorderStyle, Footer, PageNumber, LevelFormat, VerticalAlign,
} = require("docx");

const ROOT = path.resolve(__dirname, "..");
const R = JSON.parse(fs.readFileSync(path.join(ROOT, "reports", "results.json"), "utf8"));
const OUT = path.join(ROOT, "reports", "note_synthese.docx");
const REQUIRED = ["kpi", "growth", "bridge", "bridge_by_channel", "loss_making", "discounts", "whatif", "pricing_vs_cost", "coverage", "top_cost_increases",
  "abc_sku", "abc_reseller", "price_structure", "subcategories_p1", "periods"];
const missing = REQUIRED.filter((k) => !(k in R));
if (missing.length) { console.error("results.json obsolète ou incomplet (clés manquantes : " + missing.join(", ") + ") : relancer `python -m profit build`."); process.exit(1); }

// ---------- formats français
const NB = "\u00A0";
const fr = (x, nd = 1) => {
  const neg = x < 0, s = Math.abs(x).toFixed(nd);
  const [i, d] = s.split(".");
  const int = i.replace(/\B(?=(\d{3})+(?!\d))/g, NB);
  return (neg ? "\u2212" : "") + int + (d ? "," + d : "");
};
const musd = (x, nd = 2, sign = false) => (sign && x > 0 ? "+" : "") + fr(x / 1e6, nd) + NB + "M$";
const usd = (x) => fr(x, 0) + NB + "$";
const pct = (x, nd = 1) => fr(x, nd) + NB + "%";

// ---------- données utiles
const P1 = R.kpi.P1, P0 = R.kpi.P0, G = R.growth, LM = R.loss_making, D = R.discounts, W = R.whatif, PV = R.pricing_vs_cost;
const bridge = Object.fromEntries(R.bridge.map((r) => [r.step, r.value]));
const chan = (c) => R.bridge_by_channel.find((r) => r.channel === c);
const touring = R.subcategories_p1.find((r) => r.subcategory === "Touring Bikes" && r.channel === "Revendeurs");
const ps = R.price_structure.find((r) => r.category === "Total");
const psBikes = R.price_structure.find((r) => r.category === "Bikes");
const resAbcD = R.abc_reseller.find((r) => r.abc_class === "D");
const resTot = R.abc_reseller.reduce((s, r) => s + r.resellers, 0);
const grid = (x, e) => W.price_grid.delta[W.price_grid.x.indexOf(x)][W.price_grid.elasticities.indexOf(e)];
const rules = Object.fromEntries(W.discount_rules.map((r, i) => [i, r]));
const worstCost = R.top_cost_increases.reduce((a, b) => (b.unit_cost_increase_pct > a.unit_cost_increase_pct ? b : a));
const stop80 = W.stop_selling.delta[W.stop_selling.variable_shares.indexOf(0.8)];
const preDiscRes = D.summary.resellers_margin_before;
const resShare = 100 * P1.Revendeurs.net_sales / P1.Total.net_sales;
const lastRes = R.coverage.find((c) => c.channel === "Revendeurs").last_order.slice(0, 10).split("-").reverse().join("/");
const abcA = R.abc_sku.find((r) => r.abc_class === "A"), abcD = R.abc_sku.find((r) => r.abc_class === "D");
const nSku = R.abc_sku.reduce((t, r) => t + r.skus, 0);

// ---------- helpers docx
const W_TOT = 10206;                       // largeur utile A4 (marges 850)
const NAVY = "1D3557", GREY = "5B6675", RED = "C1121F", LIGHT = "EEF2F7";
const run = (t, o = {}) => new TextRun({ text: t, font: "Calibri", size: 19, ...o });
const P = (children, o = {}) => new Paragraph({ spacing: { after: 70, line: 250 }, ...o, children: Array.isArray(children) ? children : [run(children)] });
const H = (t) => new Paragraph({ spacing: { before: 140, after: 60 }, border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: NAVY, space: 1 } },
  children: [run(t, { bold: true, size: 23, color: NAVY })] });
const B = (parts) => new Paragraph({ numbering: { reference: "bul", level: 0 }, spacing: { after: 50, line: 245 }, children: parts });
const bold = (t) => run(t, { bold: true });
const paras = (t, o) => (Array.isArray(t) ? t : [t]).map((x) => new Paragraph({ alignment: o.align, spacing: { after: 0 }, children: [run(x, { size: 17, ...(o.run || {}) })] }));
const cell = (children, w, o = {}) => new TableCell({
  width: { size: w, type: WidthType.DXA }, verticalAlign: VerticalAlign.CENTER,
  margins: { top: 45, bottom: 45, left: 90, right: 90 },
  shading: o.fill ? { type: ShadingType.CLEAR, fill: o.fill, color: "auto" } : undefined,
  borders: Object.fromEntries(["top", "bottom", "left", "right"].map((k) => [k, { style: BorderStyle.SINGLE, size: 4, color: "D5DBE5" }])),
  children: paras(children, o),
});
const table = (widths, header, rows, aligns) => new Table({
  width: { size: widths.reduce((a, b) => a + b, 0), type: WidthType.DXA }, columnWidths: widths,
  rows: [new TableRow({ tableHeader: true, children: header.map((h, i) => cell(h, widths[i], { fill: NAVY, align: (aligns || [])[i] ?? (i ? AlignmentType.RIGHT : AlignmentType.LEFT), run: { bold: true, color: "FFFFFF" } })) }),
    ...rows.map((r) => new TableRow({ children: r.map((c, i) => cell(c.t ?? c, widths[i], { align: (aligns || [])[i] ?? (i ? AlignmentType.RIGHT : AlignmentType.LEFT), run: c.neg ? { color: RED, bold: true } : {} })) }))],
});
const pngSize = (p) => { const b = fs.readFileSync(p); return { w: b.readUInt32BE(16), h: b.readUInt32BE(20) }; };
const image = (name, widthPx) => {
  const p = path.join(ROOT, "reports", "figures", name), s = pngSize(p);
  return new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 40 },
    children: [new ImageRun({ type: "png", data: fs.readFileSync(p), transformation: { width: widthPx, height: Math.round((widthPx * s.h) / s.w) },
      altText: { title: name, description: name, name } })] });
};
const box = (parts, color = NAVY) => new Table({
  width: { size: W_TOT, type: WidthType.DXA }, columnWidths: [W_TOT],
  rows: [new TableRow({ children: [new TableCell({ width: { size: W_TOT, type: WidthType.DXA }, margins: { top: 80, bottom: 80, left: 140, right: 140 },
    shading: { type: ShadingType.CLEAR, fill: "F3F5F9", color: "auto" },
    borders: { top: { style: BorderStyle.NONE, size: 0, color: "FFFFFF" }, bottom: { style: BorderStyle.NONE, size: 0, color: "FFFFFF" }, right: { style: BorderStyle.NONE, size: 0, color: "FFFFFF" },
      left: { style: BorderStyle.SINGLE, size: 24, color } },
    children: [new Paragraph({ spacing: { after: 0, line: 245 }, children: parts })] })] })],
});

// ---------- contenu
const kpiRows = ["Internet", "Revendeurs", "Total"].map((c) => {
  const a = P1[c], b = P0[c];
  return [c === "Total" ? "Ensemble" : c, musd(a.net_sales, 1), pct(100 * (a.net_sales / b.net_sales - 1), 0).replace(/^/, a.net_sales > b.net_sales ? "+" : ""),
    { t: musd(a.gross_margin), neg: a.gross_margin < 0 }, pct(b.margin_pct) + "  \u2192  " + pct(a.margin_pct)];
});
const kids = [];
kids.push(new Paragraph({ spacing: { after: 30 }, children: [run("Rentabilité et marge : où la marge se perd, et comment la récupérer", { bold: true, size: 32, color: NAVY })] }));
kids.push(P([run(`Note de synthèse · AdventureWorks (jeu de démonstration Microsoft) · ${R.periods.p1} comparés aux ${R.periods.p0} · marge brute = ventes nettes de remises − coût standard · USD`, { size: 16, color: GREY })], { spacing: { after: 90 } }));

kids.push(box([bold("L'essentiel. "), run(
  `Les ventes progressent de ${pct(G.net_sales_pct, 0)} (${musd(P1.Total.net_sales, 1)}) mais la marge brute ne gagne que ${musd(G.margin_delta)} (${musd(P1.Total.gross_margin)}, ${pct(P1.Total.margin_pct)} des ventes). ` +
  `Internet (${pct(G.internet_share_of_sales_pct, 0)} des ventes) réalise ${pct(G.internet_share_of_margin_pct, 0)} de la marge : le canal revendeurs, lui, passe de ${musd(P0.Revendeurs.gross_margin)} à ${musd(P1.Revendeurs.gross_margin)}. ` +
  `Le problème n'est pas la remise (${pct(P1.Total.discount_pct_of_gross, 2)} du brut) mais le prix de base : le prix revendeur vaut ${pct(ps.reseller_price_pct_of_internet, 0)} du prix Internet et le coût standard représente ${pct(psBikes.cogs_pct_of_reseller_price, 0)} de ce prix sur les vélos.`)]));
kids.push(P("", { spacing: { after: 40 } }));
kids.push(table([2300, 1700, 1700, 2000, 2506], ["Canal", "Ventes P1", "Évol. ventes", "Marge brute P1", "Taux de marge P0 → P1"], kpiRows));

kids.push(H("Ce que montrent les données"));
kids.push(B([bold("Les hausses de prix sont absorbées par les coûts. "), run(
  `Le prix catalogue ajoute ${musd(bridge["Prix catalogue"], 2, true)} mais le coût standard retire ${musd(-bridge["Coût standard"], 2)}. Chez les revendeurs l'écart prix − coût est de ${musd(PV.resellers_gap, 2)} ` +
  `(${pct(-PV.resellers_gap_pct_of_sales)} de leur CA) ; côté Internet il reste positif (${musd(PV.internet_gap, 2, true)}).`)]));
kids.push(B([bold("La perte se concentre sur quelques lignes. "), run(
  `${LM.n} couples (référence, canal), tous chez les revendeurs, perdent ${musd(-LM.margin)} sur ${musd(LM.revenue, 1)} de ventes (${pct(LM.share_of_total_revenue_pct, 0)} du CA), dont ${pct(LM.bikes_share_of_loss_pct, 0)} sur les vélos. ` +
  `La gamme Touring vendue aux revendeurs perd ${musd(-touring.gross_margin)} (${pct(touring.margin_pct)}) ; ${resAbcD.resellers} revendeurs sur ${resTot} (${pct(resAbcD.pct_of_resellers, 0)}) sont déficitaires.`)]));
kids.push(B([bold("La remise aggrave, elle ne cause pas. "), run(
  `Elle pèse ${musd(D.summary.discounts)}, mais ${pct(D.already_below_cost_pct, 0)} va à des lignes déjà à perte avant remise et les promotions de lancement Touring en absorbent ${pct(D.new_product_promos_pct, 0)}. ` +
  `Sans aucune remise, les revendeurs resteraient à ${musd(preDiscRes)}.`)]));
kids.push(B([bold("Piège d'agrégation. "), run("Au niveau de la référence seule, certains vélos paraissent rentables car la marge Internet compense la perte chez les revendeurs : l'analyse doit se faire par (référence, canal).")]));
kids.push(image("03_waterfall_bridge.png", 610));
kids.push(image("05_price_structure.png", 520));

// ---- page 2
kids.push(new Paragraph({ pageBreakBefore: true, spacing: { after: 0 }, children: [] }));
kids.push(H("Recommandations chiffrées"));
const recW = [3300, 2500, 4406];
const recRows = [
  [{ t: `1. Relever le prix net des ${LM.n} lignes (référence, canal) vendues à perte, en priorité vélos Touring et Route chez les revendeurs (${pct(LM.bikes_share_of_loss_pct, 0)} de la perte).` },
   { t: [`+5 % de prix : ${musd(grid(0.05, 0), 2, true)}/an`, `+10 % de prix : ${musd(grid(0.1, 0), 2, true)}/an`] },
   { t: `Volumes constants. Reste positif pour toute élasticité de 0 à −3 (perdre une vente déficitaire réduit la perte). Avec 80 % seulement du coût évitable et ε = −3, +5 % donne encore ${musd(W.price_sensitivity_v80_e3_x5, 2, true)}.` }],
  [{ t: "2. Interdire toute remise sur une ligne dont la marge avant remise est négative ; réexaminer les promotions de lancement Touring." },
   { t: `≥ ${musd(rules[0].margin_delta, 2, true)}/an` },
   { t: `${usd(rules[0].discount_removed)} de remises sur ${fr(rules[0].lines, 0)} lignes. Borne basse : aucune perte de volume supposée. Recoupe la reco. 1 (mêmes lignes).` }],
  [{ t: "3. Indexer le prix revendeur sur le coût standard (clause de révision périodique)." },
   { t: `Jusqu'à ${musd(-PV.resellers_gap, 2, true)}/an` },
   { t: `Écart prix − coût observé sur P1 (${pct(-PV.resellers_gap_pct_of_sales)} du CA revendeurs) : c'est ce que l'indexation aurait évité. Coûts unitaires jusqu'à +${fr(worstCost.unit_cost_increase_pct, 1)} % (${worstCost.product_name}). Recoupe la reco. 1.` }],
  [{ t: `4. Prioriser la croissance Internet (${pct(P1.Internet.margin_pct, 0)} de marge brute).` },
   { t: `+10 % de CA : ${musd(W.internet_plus10_margin, 2, true)}` },
   { t: "Avant coûts d'acquisition, logistique et retours, absents des données : à valider avec le contrôle de gestion avant de réallouer un budget. Indépendante des recos 1 à 3." }],
];
kids.push(table(recW, ["Action", "Gain estimé", "Hypothèses et limites"], recRows, [AlignmentType.LEFT, AlignmentType.CENTER, AlignmentType.LEFT]));
kids.push(P([run("Les recommandations 1, 2 et 3 agissent sur les mêmes lignes déficitaires : leurs gains ne s'additionnent pas.", { size: 17, color: GREY, italics: true })], { spacing: { before: 50, after: 90 } }));

kids.push(box([bold("Garde-fou : ne pas arrêter les ventes à perte sans avoir mesuré le coût évitable. "), run(
  `Cesser ces ventes ne devient rentable que si au moins ${pct(100 * W.stop_selling.break_even_share)} du coût standard disparaît avec le volume ; à ${pct(100 * W.stop_selling.variable_shares[W.stop_selling.variable_shares.indexOf(0.8)], 0)}, on détruirait ${musd(-stop80)} de marge de contribution. ` +
  `Relever le prix est la voie robuste.`)], RED));

kids.push(H("Concentration de la marge"));
kids.push(P([run(`${abcA.skus} références sur ${nSku} (${pct(abcA.pct_of_skus, 0)}, classe A) produisent 80 % de la marge positive ; les ${abcD.skus} références de classe D (${pct(abcD.pct_of_skus, 0)}) la réduisent de ${musd(-abcD.gross_margin)}, un chiffre qui sous-estime le problème car il compense les canaux entre eux.`)]));
kids.push(image("07_pareto_sku.png", 470));
kids.push(H("Limites de l'analyse"));
kids.push(B([bold("Marge brute au coût standard. "), run("Le coût standard inclut des frais généraux affectés ; ce n'est pas une marge de contribution. Ni acquisition client, ni logistique, ni retours ne sont dans les données.")]));
kids.push(B([bold("Données de démonstration. "), run(`Un canal à ${pct(resShare, 0)} des ventes et à marge négative est atypique d'une entreprise réelle : il reflète la construction du jeu (prix revendeur = ${pct(ps.reseller_price_pct_of_internet, 0)} du prix Internet, coûts standard proches de ce prix). Sur un cas réel, valider d'abord l'affectation des coûts avec le contrôle de gestion.`)]));
kids.push(B([bold("Scénarios, pas prévisions. "), run("L'élasticité n'est pas estimable ici (prix presque fixes, remises pilotées par des règles de volume) : les simulations exposent les hypothèses et les bornes.")]));
kids.push(B([bold("Périodes. "), run(`Deux fenêtres de 12 mois (déc. → nov.) alignées sur la dernière date des ventes revendeurs (${lastRes}) ; le pont raisonne par (référence, canal) car les références changent de version à chaque révision de prix ou de coût.`)]));

const doc = new Document({
  creator: "Analyse de rentabilité", title: "Rentabilité et marge — note de synthèse",
  numbering: { config: [{ reference: "bul", levels: [{ level: 0, format: LevelFormat.BULLET, text: "\u2022", alignment: AlignmentType.LEFT,
    style: { paragraph: { indent: { left: 360, hanging: 260 } } } }] }] },
  styles: { default: { document: { run: { font: "Calibri", size: 19 } } } },
  sections: [{
    properties: { page: { size: { width: 11906, height: 16838 }, margin: { top: 760, bottom: 760, left: 850, right: 850 } } },
    footers: { default: new Footer({ children: [new Paragraph({ alignment: AlignmentType.CENTER, children: [
      run("Données : AdventureWorksDW (Microsoft, licence MIT) · page ", { size: 15, color: GREY }), new TextRun({ children: [PageNumber.CURRENT], font: "Calibri", size: 15, color: GREY })] })] }) },
    children: kids.filter(Boolean),
  }],
});
Packer.toBuffer(doc).then((buf) => { fs.writeFileSync(OUT, buf); console.log("Note Word générée :", OUT); });
