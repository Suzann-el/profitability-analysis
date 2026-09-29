-- =====================================================================================
-- 06_discounts.sql : effet des remises sur la marge (P1)
-- =====================================================================================
-- Attention à l'interprétation : dans ce jeu de données, la plupart des remises revendeurs sont des règles de VOLUME
-- (paliers de quantité) ou des soldes de fin de vie. La remise est donc décidée en fonction de la quantité : comparer
-- « volume avec / sans remise » mesurerait la règle, pas un effet causal de la remise sur la demande.

-- name: disc_by_promotion
SELECT p.promotion_type, p.promotion_name, COUNT(*) AS lines, SUM(f.quantity) AS units,
       ROUND(SUM(f.gross_amount), 0) AS gross_amount, ROUND(SUM(f.discount_amount), 0) AS discounts,
       ROUND(100.0 * SUM(f.discount_amount) / SUM(f.gross_amount), 1) AS discount_pct_of_gross,
       ROUND(SUM(f.margin_before_discount), 0) AS margin_before, ROUND(SUM(f.gross_margin), 0) AS margin_after,
       ROUND(100.0 * SUM(f.gross_margin) / SUM(f.net_sales), 1) AS margin_pct_after
FROM sales_period f JOIN dim_promotion p USING (promotion_key)
WHERE f.period = 'P1' AND f.promotion_key <> 1 GROUP BY 1, 2 ORDER BY discounts DESC;

-- name: disc_depth_buckets
SELECT CASE WHEN discount_pct = 0 THEN '0 %' WHEN discount_pct <= 0.05 THEN '0-5 %' WHEN discount_pct <= 0.10 THEN '5-10 %'
            WHEN discount_pct <= 0.20 THEN '10-20 %' ELSE '> 20 %' END AS depth,
       COUNT(*) AS lines, ROUND(AVG(quantity), 1) AS avg_units_per_line, ROUND(SUM(discount_amount), 0) AS discounts,
       ROUND(SUM(margin_before_discount), 0) AS margin_before, ROUND(SUM(gross_margin), 0) AS margin_after,
       ROUND(100.0 * SUM(gross_margin) / SUM(net_sales), 1) AS margin_pct_after
FROM sales_period WHERE period = 'P1' AND channel = 'Revendeurs' GROUP BY 1 ORDER BY MIN(discount_pct);

-- name: disc_turning_lines_negative
-- Trois populations de lignes remisées : (1) la remise fait basculer une ligne rentable en perte ;
-- (2) la ligne était déjà à perte AVANT remise ; (3) la ligne reste rentable après remise.
SELECT CASE WHEN margin_before_discount >= 0 AND gross_margin < 0 THEN '1 - la remise crée la perte'
            WHEN margin_before_discount < 0 THEN '2 - déjà à perte avant remise'
            ELSE '3 - reste rentable après remise' END AS population,
       COUNT(*) AS lines, ROUND(SUM(discount_amount), 0) AS discounts, ROUND(SUM(gross_margin), 0) AS margin_after
FROM sales_period WHERE period = 'P1' AND discount_amount > 0 GROUP BY 1 ORDER BY 1;

-- name: disc_summary
SELECT ROUND(SUM(discount_amount), 0) AS discounts, ROUND(SUM(gross_amount), 0) AS gross_amount,
       ROUND(100.0 * SUM(discount_amount) / SUM(gross_amount), 2) AS discount_pct_of_gross,
       ROUND(SUM(CASE WHEN channel = 'Revendeurs' THEN margin_before_discount END), 0) AS resellers_margin_before,
       ROUND(SUM(CASE WHEN channel = 'Revendeurs' THEN gross_margin END), 0) AS resellers_margin_after,
       ROUND(100.0 * SUM(CASE WHEN channel = 'Revendeurs' THEN margin_before_discount END)
             / SUM(CASE WHEN channel = 'Revendeurs' THEN gross_amount END), 2) AS resellers_margin_pct_before_discount
FROM sales_period WHERE period = 'P1';

-- name: disc_lines_p1               -- lignes revendeurs remisées de P1 (base des simulations de règles de remise)
SELECT sales_line_id, sku, promotion_key, quantity, gross_amount, discount_amount, discount_pct, net_sales, cogs,
       margin_before_discount, gross_margin
FROM sales_period WHERE period = 'P1' AND channel = 'Revendeurs' AND discount_amount > 0;
