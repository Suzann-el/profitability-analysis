-- =====================================================================================
-- 03_kpis.sql : indicateurs de rentabilité. Périodes de référence (paramètres injectés) :
--   P1 = ${P1_START} → ${P1_END}   (12 derniers mois comparables : déc. → nov.)
--   P0 = ${P0_START} → ${P0_END}   (12 mois précédents)
-- Pourquoi déc.→nov. ? Les ventes Revendeurs s'arrêtent le 29/11/2013 alors qu'Internet va jusqu'en janvier 2014 :
-- comparer des années civiles 2012 et 2013 serait faux pour les revendeurs. Deux fenêtres de 12 mois alignées
-- sur les données disponibles des DEUX canaux évitent ce biais.
-- Définitions : marge brute = ventes nettes de remises - coût standard des ventes (cogs). Taux de marge = marge / ventes nettes.
-- =====================================================================================

-- name: create_sales_period
CREATE OR REPLACE VIEW sales_period AS
SELECT f.*, CASE WHEN f.order_date BETWEEN DATE '${P0_START}' AND DATE '${P0_END}' THEN 'P0'
                 WHEN f.order_date BETWEEN DATE '${P1_START}' AND DATE '${P1_END}' THEN 'P1' END AS period
FROM fact_sales f
WHERE f.order_date BETWEEN DATE '${P0_START}' AND DATE '${P1_END}';

-- name: kpi_summary
SELECT period, channel,
       ROUND(SUM(net_sales), 0) AS net_sales, ROUND(SUM(cogs), 0) AS cogs, ROUND(SUM(gross_margin), 0) AS gross_margin,
       ROUND(100.0 * SUM(gross_margin) / SUM(net_sales), 2) AS margin_pct,
       ROUND(SUM(gross_amount), 0) AS gross_amount, ROUND(SUM(discount_amount), 0) AS discounts,
       ROUND(100.0 * SUM(discount_amount) / SUM(gross_amount), 2) AS discount_pct_of_gross,
       SUM(quantity) AS units, COUNT(DISTINCT order_number) AS orders, COUNT(*) AS lines,
       ROUND(100.0 * AVG(is_below_cost::INT), 1) AS pct_lines_below_cost,
       ROUND(SUM(CASE WHEN is_below_cost THEN gross_margin END), 0) AS loss_on_below_cost_lines
FROM sales_period GROUP BY ROLLUP (period, channel) HAVING period IS NOT NULL ORDER BY period, channel NULLS FIRST;

-- name: kpi_by_category
SELECT period, s.category, channel,
       ROUND(SUM(net_sales), 0) AS net_sales, ROUND(SUM(gross_margin), 0) AS gross_margin,
       ROUND(100.0 * SUM(gross_margin) / SUM(net_sales), 2) AS margin_pct, SUM(quantity) AS units
FROM sales_period f JOIN dim_sku s USING (sku) GROUP BY 1, 2, 3 ORDER BY 1, 2, 3;

-- name: kpi_by_subcategory
SELECT s.category, s.subcategory, channel,
       ROUND(SUM(net_sales), 0) AS net_sales, ROUND(SUM(gross_margin), 0) AS gross_margin,
       ROUND(100.0 * SUM(gross_margin) / SUM(net_sales), 2) AS margin_pct, SUM(quantity) AS units
FROM sales_period f JOIN dim_sku s USING (sku) WHERE period = 'P1' GROUP BY 1, 2, 3 ORDER BY gross_margin;

-- name: kpi_by_territory
SELECT t.territory_group, t.country, t.region, channel,
       ROUND(SUM(net_sales), 0) AS net_sales, ROUND(SUM(gross_margin), 0) AS gross_margin,
       ROUND(100.0 * SUM(gross_margin) / SUM(net_sales), 2) AS margin_pct
FROM sales_period f JOIN dim_territory t USING (territory_key) WHERE period = 'P1' GROUP BY 1, 2, 3, 4 ORDER BY gross_margin;

-- name: kpi_by_reseller_type
SELECT r.business_type, COUNT(DISTINCT f.reseller_key) AS resellers,
       ROUND(SUM(net_sales), 0) AS net_sales, ROUND(SUM(gross_margin), 0) AS gross_margin,
       ROUND(100.0 * SUM(gross_margin) / SUM(net_sales), 2) AS margin_pct,
       ROUND(100.0 * SUM(discount_amount) / SUM(gross_amount), 2) AS discount_pct_of_gross
FROM sales_period f JOIN dim_reseller r USING (reseller_key) WHERE period = 'P1' GROUP BY 1 ORDER BY net_sales DESC;

-- name: kpi_monthly
SELECT d.year_month, channel, ROUND(SUM(net_sales), 0) AS net_sales, ROUND(SUM(gross_margin), 0) AS gross_margin,
       ROUND(100.0 * SUM(gross_margin) / SUM(net_sales), 2) AS margin_pct
FROM fact_sales f JOIN dim_date d USING (date_key) GROUP BY 1, 2 ORDER BY 1, 2;

-- name: kpi_by_calendar_year        -- « partial » signale les années incomplètes pour un canal
SELECT d.year, channel, ROUND(SUM(net_sales), 0) AS net_sales, ROUND(SUM(gross_margin), 0) AS gross_margin,
       ROUND(100.0 * SUM(gross_margin) / SUM(net_sales), 2) AS margin_pct,
       COUNT(DISTINCT d.month) AS months_with_sales, (COUNT(DISTINCT d.month) < 12) AS partial
FROM fact_sales f JOIN dim_date d USING (date_key) GROUP BY 1, 2 ORDER BY 1, 2;

-- name: kpi_price_structure         -- même SKU vendu dans les deux canaux : le prix revendeur couvre-t-il le coût ?
WITH per AS (
  SELECT sku, channel, SUM(quantity) AS q, SUM(net_sales) / SUM(quantity) AS price, SUM(cogs) / SUM(quantity) AS unit_cogs
  FROM sales_period WHERE period = 'P1' GROUP BY 1, 2),
both_ch AS (
  SELECT r.sku, r.q AS q_res, r.price AS p_res, i.price AS p_int, r.unit_cogs AS c
  FROM per r JOIN per i ON i.sku = r.sku AND r.channel = 'Revendeurs' AND i.channel = 'Internet')
SELECT s.category, COUNT(*) AS skus,
       ROUND(100.0 * SUM(p_res * q_res) / SUM(p_int * q_res), 1) AS reseller_price_pct_of_internet,
       ROUND(100.0 * SUM(c * q_res) / SUM(p_res * q_res), 1) AS cogs_pct_of_reseller_price
FROM both_ch b JOIN dim_sku s USING (sku) GROUP BY ROLLUP (s.category) ORDER BY s.category NULLS LAST;
