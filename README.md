# Analyse de rentabilité et de marge — SQL d'abord, Python pour orchestrer

Projet de data science orienté **analyse financière** : construire un entrepôt analytique sur un jeu de données
réel (AdventureWorks, Microsoft, licence MIT), décomposer la marge par effet Prix/Volume/Mix, identifier les
références et revendeurs qui détruisent de la valeur, et simuler des leviers correctifs.

> **Question business** : où se perd la marge, pourquoi, et que faire ?

## Ce que fait le projet

| Étape | Contenu |
|---|---|
| 1. Modèle en étoile | Staging → star schema (DuckDB) : `fact_sales`, 7 dimensions, 17 contrôles qualité |
| 2. KPIs | Ventes nettes, marge brute, taux de marge, remises — par canal, catégorie, territoire, type de revendeur |
| 3. Pont PVM | Décomposition Prix / Volume / Mix / Coût / Nouveaux / Arrêtés entre P0 et P1 |
| 4. Pareto / ABC | Concentration de la marge par référence et par revendeur, classes A/B/C/D |
| 5. Remises | Impact sur la marge : la remise aggrave-t-elle une perte existante, ou la crée-t-elle ? |
| 6. Simulations | Hausse de prix (avec élasticité), règles de remise, arrêt des ventes à perte |
| 7. Livrables | Tableau de bord HTML (4 onglets), 15 exports CSV (Power BI / Tableau), note de synthèse Word 2 pages |

## Démarrage rapide

```bash
pip install duckdb pandas numpy matplotlib
python scripts/download_data.py          # télécharge les CSV AdventureWorks (MIT) + vérifie les empreintes SHA-256
python -m profit build                   # entrepôt → contrôles → graphiques → dashboard → exports → note Word
pytest tests/                            # 116 tests + 20 mutants
```

`python -m profit build` écrit :
- `reports/dashboard.html` — tableau de bord HTML autonome (images intégrées, sans JavaScript)
- `reports/figures/*.png` — 11 graphiques matplotlib
- `reports/note_synthese.docx` — note de synthèse Word 2 pages (nécessite Node.js)
- `exports/*.csv` — modèle en étoile + tables d'analyse pré-calculées pour Power BI / Tableau
- `reports/results.json` — tous les chiffres en un seul fichier (aucun chiffre saisi à la main dans les livrables)

## Données

**AdventureWorks Data Warehouse** (Microsoft, [licence MIT](https://github.com/microsoft/sql-server-samples/blob/master/LICENSE)).
Jeu de démonstration fictif : ventes B2B (Revendeurs) et B2C (Internet) de matériel sportif, décembre 2010 – janvier 2014.

```bash
python scripts/download_data.py   # télécharge depuis GitHub, vérifie les empreintes SHA-256
```

> Un canal à marge négative sur un jeu de démonstration est atypique d'une entreprise réelle : c'est une
> caractéristique de la construction du jeu (prix revendeur ≈ 60 % du prix Internet, coûts standards proches
> de ce prix). Les méthodes et le code sont valables ; les conclusions business sont illustratives.

## Résultats (12 mois à nov. 2013 vs 12 mois à nov. 2012)

| Indicateur | Valeur |
|---|---|
| Ventes nettes | 51,3 M$ (+52 % vs P0) |
| Marge brute totale | 5,58 M$ (10,9 % des ventes) |
| Marge Internet | +6,25 M$ (41,4 %) — 29 % des ventes, 112 % de la marge |
| Marge Revendeurs | **−0,67 M$** (−1,9 %) — 71 % des ventes |
| Pont de marge | Prix +2,38 M$, Coût −2,57 M$, Nouveaux produits Revendeurs −1,10 M$ |
| Lignes à perte | 71 (référence × canal), −2,09 M$ sur 23,7 M$ de CA (46 % du total), 93 % sur Bikes |
| Remises | 90 % vont à des lignes déjà à perte avant remise — la remise aggrave, elle ne cause pas |
| Simulation +5 % de prix | +1,19 M$/an, positif quelle que soit l'élasticité (0 à −3) |
| Seuil « arrêt des ventes » | 91,9 % du coût standard doit être évitable — bien au-delà du raisonnable |

**Pareto** : 34 références (17 %) produisent 80 % de la marge positive ; 39 références (20 %, classe D) la réduisent de 0,57 M$.

**ABC revendeurs** : 52 revendeurs (10 %) génèrent toute la marge positive ; 297 (60 %) sont déficitaires.

## Structure

```
sql/
  00_staging.sql     chargement brut des CSV (schéma explicite, séparateur |)
  01_model.sql       modèle en étoile : fact_sales + 7 dimensions
  02_quality.sql     17 contrôles qualité nommés (chk_*)
  03_kpis.sql        KPIs paramétrés par fenêtre P0/P1
  04_pvm.sql         pont Prix/Volume/Mix (pvm_lines, pvm_bridge)
  05_pareto.sql      Pareto de la marge, classes ABC (référence et revendeur)
  06_discounts.sql   analyse des remises (populations, profondeur, promotions)
src/profit/
  db.py              Warehouse : build(), query(), checks() — SQL d'abord
  pvm.py             pont PVM en pandas (implémentation indépendante pour recoupement)
  whatif.py          simulations prix / remise / arrêt des ventes (fonctions pures)
  results.py         collecte tous les chiffres depuis le SQL → results.json
  charts.py          11 graphiques matplotlib (libellés en français)
  dashboard.py       tableau de bord HTML autonome (4 onglets, CSS-only)
  export.py          exports CSV pour Power BI / Tableau
  cli.py             `python -m profit build`
scripts/
  download_data.py   téléchargement + vérification SHA-256 des CSV AdventureWorks
  mutation_check.py  20 mutants injectés, 20/20 détectés par la suite de tests
tests/
  test_data_integrity.py   empreintes, contrôles qualité, 12 corruptions détectées par mutation
  test_pvm.py              exemple calculé à la main, recoupement SQL ↔ pandas, 25 seeds aléatoires
  test_pareto_discounts.py invariants ABC, populations de remises, cohérence des KPIs
  test_whatif.py           propriétés mathématiques des simulations, 20 seeds aléatoires
  test_outputs.py          JSON, graphiques, dashboard autonome, exports sans données personnelles, note Word
```

## Choix méthodologiques (à savoir défendre en entretien)

- **SQL d'abord** : toute la logique métier (PVM, Pareto, remises) est en SQL DuckDB, lisible et auditable.
  Python orchestre, ne recalcule pas.
- **Deux implémentations du pont PVM** : SQL (`04_pvm.sql`) et pandas (`pvm.py`), écrites séparément,
  recoupées ligne par ligne dans les tests. L'identité (Marge P1 − Marge P0 = somme des effets) est vérifiée
  sur 25 jeux de données aléatoires.
- **Marge par (référence, canal)** : agréger au niveau référence masque les pertes du canal revendeur
  compensées par le canal Internet — le piège d'agrégation est testé explicitement.
- **SCD type 2** : `dim_product` a 606 clés pour 504 références (une nouvelle clé à chaque révision de prix
  ou coût). Toutes les analyses utilisent `sku` (référence stable), jamais `product_key`.
- **Deux fenêtres de 12 mois** (déc. → nov.) alignées sur la dernière date des ventes Revendeurs (29/11/2013) :
  comparer des années civiles 2012 et 2013 biaiserait la comparaison (canal Revendeurs incomplet en 2013).
- **Marge brute au coût standard** : le coût inclut des frais généraux affectés ; ce n'est pas une marge
  de contribution. Mentionné explicitement dans les limites de chaque livrable.
- **Simulations avec hypothèses explicites** : l'élasticité et la part de coût évitable ne sont pas dans
  les données — les simulations exposent les bornes, pas des prévisions.
- **20 mutants, 20/20 détectés** : bugs injectés dans le SQL et le Python (signe du mix PVM inversé,
  seuil ABC à 90 % au lieu de 80 %, coût évité oublié dans la hausse de prix, etc.) — tous détectés.

## Présenter ce projet en entretien

> Analyse de rentabilité sur AdventureWorks (données réelles Microsoft, licence MIT) : entrepôt DuckDB,
> pont PVM décomposant +2 M$ de variation de marge en 7 effets, Pareto montrant que 20 % des références
> détruisent de la valeur, et simulations montrant qu'une hausse de prix de 5 % sur les lignes déficitaires
> rapporte +1,19 M$/an quelle que soit l'élasticité. Tableau de bord HTML autonome, exports Power BI,
> note Word 2 pages. 116 tests, 20/20 mutants détectés.
