-- =====================================================================================
-- 02_quality.sql : contrôles de qualité et de réconciliation. Chaque requête retourne un nombre de VIOLATIONS
-- (0 attendu), sauf mention contraire. Exécutés par `python -m profit build` et par la suite de tests.
-- =====================================================================================

-- name: chk_fact_rows_equal_staging
SELECT ABS((SELECT count(*) FROM fact_sales) - ((SELECT count(*) FROM stg_fact_reseller_sales) + (SELECT count(*) FROM stg_fact_internet_sales))) AS violations;

-- name: chk_fact_grain_unique
SELECT count(*) - count(DISTINCT sales_line_id) AS violations FROM fact_sales;

-- name: chk_net_sales_reconcile_staging
SELECT ABS((SELECT sum(net_sales) FROM fact_sales) - ((SELECT sum(SalesAmount) FROM stg_fact_reseller_sales) + (SELECT sum(SalesAmount) FROM stg_fact_internet_sales)))::DOUBLE AS violations;

-- name: chk_cogs_reconcile_staging
SELECT ABS((SELECT sum(cogs) FROM fact_sales) - ((SELECT sum(TotalProductCost) FROM stg_fact_reseller_sales) + (SELECT sum(TotalProductCost) FROM stg_fact_internet_sales)))::DOUBLE AS violations;

-- name: chk_orphan_products
SELECT count(*) AS violations FROM fact_sales WHERE sku IS NULL;

-- name: chk_orphan_sku_category
SELECT count(*) AS violations FROM fact_sales f LEFT JOIN dim_sku s USING (sku) WHERE s.category IS NULL;

-- name: chk_orphan_dates
SELECT count(*) AS violations FROM fact_sales f LEFT JOIN dim_date d ON d.date_key = f.date_key WHERE d.date_key IS NULL;

-- name: chk_orphan_territories
SELECT count(*) AS violations FROM fact_sales f LEFT JOIN dim_territory t USING (territory_key) WHERE t.territory_key IS NULL;

-- name: chk_orphan_promotions
SELECT count(*) AS violations FROM fact_sales f LEFT JOIN dim_promotion p USING (promotion_key) WHERE p.promotion_key IS NULL;

-- name: chk_channel_keys
SELECT count(*) AS violations FROM fact_sales
WHERE (channel = 'Revendeurs' AND (reseller_key IS NULL OR customer_key IS NOT NULL))
   OR (channel = 'Internet' AND (customer_key IS NULL OR reseller_key IS NOT NULL));

-- name: chk_orphan_resellers_customers
SELECT (SELECT count(*) FROM fact_sales f LEFT JOIN dim_reseller r USING (reseller_key) WHERE f.channel = 'Revendeurs' AND r.reseller_key IS NULL)
     + (SELECT count(*) FROM fact_sales f LEFT JOIN dim_customer c USING (customer_key) WHERE f.channel = 'Internet' AND c.customer_key IS NULL) AS violations;

-- name: chk_gross_amount_identity          -- brut = quantité x prix unitaire
SELECT count(*) AS violations FROM fact_sales WHERE ABS(gross_amount - quantity * unit_price) > 0.01;

-- name: chk_net_identity                   -- net = brut - remise
SELECT count(*) AS violations FROM fact_sales WHERE ABS(net_sales - (gross_amount - discount_amount)) > 0.01;

-- name: chk_cogs_identity                  -- coût = quantité x coût unitaire
SELECT count(*) AS violations FROM fact_sales WHERE ABS(cogs - quantity * unit_cogs) > 0.01;

-- name: chk_discount_identity              -- remise = brut x taux
SELECT count(*) AS violations FROM fact_sales WHERE ABS(discount_amount - gross_amount * discount_pct) > 0.01;

-- name: chk_positive_quantities_and_costs
SELECT count(*) AS violations FROM fact_sales WHERE quantity <= 0 OR unit_cogs <= 0 OR unit_price <= 0;

-- name: chk_sku_has_unique_category         -- un sku ne change pas de catégorie entre ses versions
SELECT count(*) AS violations FROM (SELECT sku FROM dim_product WHERE category IS NOT NULL GROUP BY sku HAVING count(DISTINCT category) > 1);

-- name: info_period_coverage                -- INFO (pas une violation) : couverture temporelle par canal
SELECT channel, min(order_date) AS first_order, max(order_date) AS last_order, count(*) AS lines FROM fact_sales GROUP BY channel ORDER BY channel;
