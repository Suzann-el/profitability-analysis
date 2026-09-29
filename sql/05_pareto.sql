-- =====================================================================================
-- 05_pareto.sql : concentration de la marge (Pareto) et classes ABC sur P1
-- =====================================================================================
-- La marge nette contient des valeurs NÉGATIVES : la courbe cumulée dépasse 100 % avant de redescendre. On définit donc
-- les classes sur la marge POSITIVE cumulée :
--   A = les références qui font les 80 % premiers de la marge positive ; B = les 15 % suivants ; C = la traîne positive ;
--   D = références à marge négative (« destructrices de marge »).
-- Une référence est classée A/B/C d'après le cumul AVANT elle (celle qui franchit le seuil reste dans la classe).
-- Deux bases de cumul : cum_margin_pct_of_net (marge nette ; indéfinie si le total est négatif, ce qui est le cas des revendeurs)
-- et cum_margin_pct_of_positive (marge positive ; toujours définie, même base que les classes ABC).

-- name: create_pareto_sku
CREATE OR REPLACE TABLE pareto_sku AS
WITH p AS (
  SELECT f.sku, s.product_name, s.category, s.subcategory,
         SUM(f.quantity) AS units, SUM(f.net_sales) AS net_sales, SUM(f.gross_margin) AS gross_margin,
         SUM(CASE WHEN f.channel = 'Revendeurs' THEN f.gross_margin ELSE 0 END) AS margin_resellers,
         SUM(CASE WHEN f.channel = 'Internet' THEN f.gross_margin ELSE 0 END) AS margin_internet
  FROM sales_period f JOIN dim_sku s USING (sku) WHERE f.period = 'P1' GROUP BY 1, 2, 3, 4),
r AS (
  SELECT *, SUM(GREATEST(gross_margin, 0)) OVER () AS total_positive_margin,
         SUM(GREATEST(gross_margin, 0)) OVER (ORDER BY gross_margin DESC, sku ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) AS cum_before,
         SUM(gross_margin) OVER (ORDER BY gross_margin DESC, sku ROWS UNBOUNDED PRECEDING) AS cum_margin,
         SUM(gross_margin) OVER () AS total_margin,
         ROW_NUMBER() OVER (ORDER BY gross_margin DESC, sku) AS rank_margin, COUNT(*) OVER () AS n_items
  FROM p)
SELECT sku, product_name, category, subcategory, units, net_sales, gross_margin, margin_resellers, margin_internet,
       100.0 * gross_margin / NULLIF(net_sales, 0) AS margin_pct, rank_margin, n_items,
       100.0 * rank_margin / n_items AS pct_of_items,
       CASE WHEN total_margin > 0 THEN 100.0 * cum_margin / total_margin END AS cum_margin_pct_of_net,   -- NULL si la marge nette totale est <= 0
       100.0 * cum_margin / total_positive_margin AS cum_margin_pct_of_positive,
       CASE WHEN gross_margin < 0 THEN 'D'
            WHEN COALESCE(cum_before, 0) < 0.80 * total_positive_margin THEN 'A'
            WHEN COALESCE(cum_before, 0) < 0.95 * total_positive_margin THEN 'B' ELSE 'C' END AS abc_class
FROM r ORDER BY rank_margin;

-- name: create_pareto_reseller
CREATE OR REPLACE TABLE pareto_reseller AS
WITH p AS (
  SELECT f.reseller_key, r.reseller_name, r.business_type, r.country, SUM(f.net_sales) AS net_sales,
         SUM(f.gross_margin) AS gross_margin, SUM(f.discount_amount) AS discounts, COUNT(DISTINCT f.order_number) AS orders
  FROM sales_period f JOIN dim_reseller r USING (reseller_key) WHERE f.period = 'P1' AND f.channel = 'Revendeurs'
  GROUP BY 1, 2, 3, 4),
r AS (
  SELECT *, SUM(GREATEST(gross_margin, 0)) OVER () AS total_positive_margin,
         SUM(GREATEST(gross_margin, 0)) OVER (ORDER BY gross_margin DESC, reseller_key ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) AS cum_before,
         SUM(gross_margin) OVER (ORDER BY gross_margin DESC, reseller_key ROWS UNBOUNDED PRECEDING) AS cum_margin,
         SUM(gross_margin) OVER () AS total_margin,
         ROW_NUMBER() OVER (ORDER BY gross_margin DESC, reseller_key) AS rank_margin, COUNT(*) OVER () AS n_items
  FROM p)
SELECT reseller_key, reseller_name, business_type, country, orders, net_sales, gross_margin, discounts,
       100.0 * gross_margin / NULLIF(net_sales, 0) AS margin_pct, rank_margin, n_items,
       100.0 * rank_margin / n_items AS pct_of_items,
       CASE WHEN total_margin > 0 THEN 100.0 * cum_margin / total_margin END AS cum_margin_pct_of_net,   -- NULL si la marge nette totale est <= 0
       100.0 * cum_margin / total_positive_margin AS cum_margin_pct_of_positive,
       CASE WHEN gross_margin < 0 THEN 'D'
            WHEN COALESCE(cum_before, 0) < 0.80 * total_positive_margin THEN 'A'
            WHEN COALESCE(cum_before, 0) < 0.95 * total_positive_margin THEN 'B' ELSE 'C' END AS abc_class
FROM r ORDER BY rank_margin;

-- name: abc_sku_summary
SELECT abc_class, COUNT(*) AS skus, ROUND(100.0 * COUNT(*) / MAX(n_items), 1) AS pct_of_skus,
       ROUND(SUM(net_sales), 0) AS net_sales, ROUND(SUM(gross_margin), 0) AS gross_margin
FROM pareto_sku GROUP BY 1 ORDER BY 1;

-- name: abc_reseller_summary
SELECT abc_class, COUNT(*) AS resellers, ROUND(100.0 * COUNT(*) / MAX(n_items), 1) AS pct_of_resellers,
       ROUND(SUM(net_sales), 0) AS net_sales, ROUND(SUM(gross_margin), 0) AS gross_margin
FROM pareto_reseller GROUP BY 1 ORDER BY 1;

-- name: loss_making_sku_channel        -- (sku, canal) à marge négative sur P1 : base des simulations
SELECT f.sku, s.product_name, s.category, s.subcategory, f.channel, SUM(f.quantity) AS units, SUM(f.net_sales) AS net_sales,
       SUM(f.cogs) AS cogs, SUM(f.gross_margin) AS gross_margin, 100.0 * SUM(f.gross_margin) / SUM(f.net_sales) AS margin_pct
FROM sales_period f JOIN dim_sku s USING (sku) WHERE f.period = 'P1'
GROUP BY 1, 2, 3, 4, 5 HAVING SUM(f.gross_margin) < 0 ORDER BY gross_margin;
