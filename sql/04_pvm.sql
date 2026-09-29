-- =====================================================================================
-- 04_pvm.sql : pont de marge Prix / Volume / Mix (PVM) entre P0 et P1
-- =====================================================================================
-- Unité d'analyse : (sku, canal). Le canal fait partie de la maille pour que l'effet de mix capte aussi le
-- basculement entre canaux (un vélo vendu sur Internet ne rapporte pas la même marge que chez un revendeur).
--
-- Pour chaque ligne (sku, canal) : q = unités, L = brut/unité (prix catalogue au moment de la vente), D = remise/unité,
-- C = coût standard/unité, m = marge unitaire = L - D - C. Sur les lignes « continues » (vendues en P0 ET en P1) :
--   Volume   = (Q1c/Q0c - 1) x m0 x q0        croissance des volumes AU MIX CONSTANT (Q = total des unités continues)
--   Mix      = (q1 - q0 x Q1c/Q0c) x m0       écart à la croissance proportionnelle, valorisé à la marge unitaire P0
--   Prix     = q1 x (L1 - L0)                 variation du prix catalogue
--   Remises  = -q1 x (D1 - D0)                variation de la remise unitaire
--   Coût     = -q1 x (C1 - C0)                variation du coût standard unitaire
-- Lignes non continues : « Nouveaux » = marge P1 des lignes absentes en P0 ; « Arrêtés » = -marge P0 des lignes absentes en P1.
-- Identité exacte (vérifiée par les tests) : Marge P1 - Marge P0 = Volume + Mix + Prix + Remises + Coût + Nouveaux + Arrêtés.

-- name: create_pvm_lines
CREATE OR REPLACE TABLE pvm_lines AS
WITH agg AS (
  SELECT sku, channel, period, CAST(SUM(quantity) AS DOUBLE) AS q, CAST(SUM(gross_amount) AS DOUBLE) AS gross,
         CAST(SUM(discount_amount) AS DOUBLE) AS disc, CAST(SUM(net_sales) AS DOUBLE) AS net, CAST(SUM(cogs) AS DOUBLE) AS cogs
  FROM sales_period GROUP BY 1, 2, 3),
w AS (
  SELECT COALESCE(a.sku, b.sku) AS sku, COALESCE(a.channel, b.channel) AS channel,
         COALESCE(a.q, 0) AS q0, COALESCE(b.q, 0) AS q1,
         COALESCE(a.gross, 0) AS gross0, COALESCE(b.gross, 0) AS gross1,
         COALESCE(a.disc, 0) AS disc0, COALESCE(b.disc, 0) AS disc1,
         COALESCE(a.net, 0) AS net0, COALESCE(b.net, 0) AS net1,
         COALESCE(a.cogs, 0) AS cogs0, COALESCE(b.cogs, 0) AS cogs1
  FROM (SELECT * FROM agg WHERE period = 'P0') a
  FULL OUTER JOIN (SELECT * FROM agg WHERE period = 'P1') b ON a.sku = b.sku AND a.channel = b.channel),
m AS (SELECT *, net0 - cogs0 AS margin0, net1 - cogs1 AS margin1 FROM w),
tot AS (SELECT SUM(q0) AS q0c, SUM(q1) AS q1c FROM m WHERE q0 > 0 AND q1 > 0)
SELECT m.sku, m.channel, m.q0, m.q1, m.net0, m.net1, m.margin0, m.margin1, m.margin1 - m.margin0 AS delta_margin,
       CASE WHEN m.q0 > 0 THEN m.cogs0 / m.q0 END AS unit_cogs0, CASE WHEN m.q1 > 0 THEN m.cogs1 / m.q1 END AS unit_cogs1,
       CASE WHEN m.q0 > 0 AND m.q1 > 0 THEN (tot.q1c / tot.q0c - 1) * m.margin0 ELSE 0 END AS volume_effect,
       CASE WHEN m.q0 > 0 AND m.q1 > 0 THEN m.q1 * m.margin0 / m.q0 - m.margin0 * tot.q1c / tot.q0c ELSE 0 END AS mix_effect,
       CASE WHEN m.q0 > 0 AND m.q1 > 0 THEN m.gross1 - m.q1 * m.gross0 / m.q0 ELSE 0 END AS price_effect,
       CASE WHEN m.q0 > 0 AND m.q1 > 0 THEN -(m.disc1 - m.q1 * m.disc0 / m.q0) ELSE 0 END AS discount_effect,
       CASE WHEN m.q0 > 0 AND m.q1 > 0 THEN -(m.cogs1 - m.q1 * m.cogs0 / m.q0) ELSE 0 END AS cost_effect,
       CASE WHEN m.q0 = 0 THEN m.margin1 ELSE 0 END AS new_effect,
       CASE WHEN m.q1 = 0 THEN -m.margin0 ELSE 0 END AS discontinued_effect
FROM m CROSS JOIN tot;

-- name: pvm_bridge
SELECT step, ord, ROUND(value, 0) AS value FROM (
  SELECT 'Marge P0' AS step, 0 AS ord, SUM(margin0) AS value FROM pvm_lines
  UNION ALL SELECT 'Volume', 1, SUM(volume_effect) FROM pvm_lines
  UNION ALL SELECT 'Mix produits/canaux', 2, SUM(mix_effect) FROM pvm_lines
  UNION ALL SELECT 'Prix catalogue', 3, SUM(price_effect) FROM pvm_lines
  UNION ALL SELECT 'Remises', 4, SUM(discount_effect) FROM pvm_lines
  UNION ALL SELECT 'Coût standard', 5, SUM(cost_effect) FROM pvm_lines
  UNION ALL SELECT 'Nouveaux produits', 6, SUM(new_effect) FROM pvm_lines
  UNION ALL SELECT 'Produits arrêtés', 7, SUM(discontinued_effect) FROM pvm_lines
  UNION ALL SELECT 'Marge P1', 8, SUM(margin1) FROM pvm_lines) ORDER BY ord;

-- name: pvm_by_channel
SELECT channel, ROUND(SUM(margin0), 0) AS margin_p0, ROUND(SUM(volume_effect), 0) AS volume, ROUND(SUM(mix_effect), 0) AS mix,
       ROUND(SUM(price_effect), 0) AS price, ROUND(SUM(discount_effect), 0) AS discounts, ROUND(SUM(cost_effect), 0) AS cost,
       ROUND(SUM(new_effect), 0) AS new_products, ROUND(SUM(discontinued_effect), 0) AS discontinued, ROUND(SUM(margin1), 0) AS margin_p1
FROM pvm_lines GROUP BY 1 ORDER BY 1;

-- name: pvm_by_category
SELECT s.category, ROUND(SUM(margin0), 0) AS margin_p0, ROUND(SUM(volume_effect), 0) AS volume, ROUND(SUM(mix_effect), 0) AS mix,
       ROUND(SUM(price_effect), 0) AS price, ROUND(SUM(discount_effect), 0) AS discounts, ROUND(SUM(cost_effect), 0) AS cost,
       ROUND(SUM(new_effect), 0) AS new_products, ROUND(SUM(discontinued_effect), 0) AS discontinued, ROUND(SUM(margin1), 0) AS margin_p1
FROM pvm_lines p JOIN dim_sku s USING (sku) GROUP BY 1 ORDER BY 1;

-- name: pvm_top_cost_increases      -- plus fortes hausses de coût unitaire (lignes continues) : ce qui alimente l'effet coût
SELECT s.product_name, p.channel, p.q1 AS units_p1, ROUND(p.cost_effect, 0) AS cost_effect,
       ROUND(100.0 * (p.unit_cogs1 / p.unit_cogs0 - 1), 1) AS unit_cost_increase_pct
FROM pvm_lines p JOIN dim_sku s USING (sku) WHERE p.q0 > 0 AND p.q1 > 0 ORDER BY p.cost_effect LIMIT 10;
