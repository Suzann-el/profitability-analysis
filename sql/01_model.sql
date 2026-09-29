-- =====================================================================================
-- 01_model.sql : modèle en étoile analytique (schéma en étoile) construit sur le staging
-- =====================================================================================
-- Grain de la table de faits : UNE LIGNE DE COMMANDE (commande x n° de ligne), pour les deux canaux
-- (Revendeurs = B2B, Internet = B2C) réunis dans fact_sales.
--
-- Choix de modélisation (à savoir défendre) :
--  * Montants en USD : vérifié au staging (le prix unitaire = prix catalogue quelle que soit la devise de la commande).
--  * Revenu = SalesAmount (net de remises). Taxes et frais de transport EXCLUS : ils sont refacturés/reversés,
--    ils ne font pas partie de la marge produit.
--  * Coût = coût standard du produit à la date de la vente (TotalProductCost). C'est un coût standard (matières, main-d'œuvre,
--    frais généraux affectés), donc la marge est une MARGE BRUTE standard, pas une marge de contribution.
--  * dim_product est historisée (SCD type 2 : 606 clés pour 504 références, une nouvelle clé à chaque changement de prix/coût).
--    Les analyses de produit se font donc par `sku` (référence stable), jamais par product_key.
--  * Les données personnelles (noms, e-mails, adresses, téléphones, dates de naissance) des clients ne sont PAS chargées.

CREATE OR REPLACE TABLE dim_date AS
SELECT DateKey AS date_key, FullDateAlternateKey AS date, CalendarYear AS year, CalendarQuarter AS quarter,
       MonthNumberOfYear AS month, EnglishMonthName AS month_name, FrenchMonthName AS month_name_fr,
       strftime(FullDateAlternateKey, '%Y-%m') AS year_month
FROM stg_dim_date;

CREATE OR REPLACE TABLE dim_product AS
SELECT CAST(p.ProductKey AS INTEGER) AS product_key,
       p.ProductAlternateKey AS sku,
       p.EnglishProductName AS product_name,
       p.ModelName AS model_name,
       c.EnglishProductCategoryName AS category,
       s.EnglishProductSubcategoryName AS subcategory,
       p.Color AS color, p.ProductLine AS product_line, p.Class AS class,
       TRY_CAST(p.StandardCost AS DECIMAL(19,4)) AS standard_cost,
       TRY_CAST(p.ListPrice AS DECIMAL(19,4)) AS list_price,
       TRY_CAST(p.DealerPrice AS DECIMAL(19,4)) AS dealer_price,
       (p.Status = 'Current') AS is_current_version
FROM stg_dim_product p
LEFT JOIN stg_dim_product_subcategory s ON s.ProductSubcategoryKey = TRY_CAST(p.ProductSubcategoryKey AS INTEGER)
LEFT JOIN stg_dim_product_category c ON c.ProductCategoryKey = s.ProductCategoryKey;

-- Une ligne par référence (sku) : attributs de la version la plus récente
CREATE OR REPLACE TABLE dim_sku AS
WITH ranked AS (
  SELECT *, ROW_NUMBER() OVER (PARTITION BY sku ORDER BY product_key DESC) AS rn FROM dim_product)
SELECT sku, product_name, model_name, category, subcategory, color, product_line, class
FROM ranked WHERE rn = 1;

CREATE OR REPLACE TABLE dim_territory AS
SELECT CAST(SalesTerritoryKey AS INTEGER) AS territory_key, SalesTerritoryRegion AS region,
       SalesTerritoryCountry AS country, SalesTerritoryGroup AS territory_group
FROM stg_dim_sales_territory;

CREATE OR REPLACE TABLE dim_geography AS
SELECT CAST(GeographyKey AS INTEGER) AS geography_key, City AS city, StateProvinceName AS state_province,
       EnglishCountryRegionName AS country, CAST(SalesTerritoryKey AS INTEGER) AS territory_key
FROM stg_dim_geography;

CREATE OR REPLACE TABLE dim_customer AS      -- B2C (Internet) ; aucune donnée personnelle
SELECT CAST(c.CustomerKey AS INTEGER) AS customer_key, g.city, g.state_province, g.country
FROM stg_dim_customer c LEFT JOIN dim_geography g ON g.geography_key = TRY_CAST(c.GeographyKey AS INTEGER);

CREATE OR REPLACE TABLE dim_reseller AS      -- B2B (Revendeurs)
SELECT CAST(r.ResellerKey AS INTEGER) AS reseller_key, r.ResellerName AS reseller_name, r.BusinessType AS business_type,
       r.ProductLine AS product_line, TRY_CAST(r.NumberEmployees AS INTEGER) AS number_employees,
       r.OrderFrequency AS order_frequency, TRY_CAST(r.YearOpened AS INTEGER) AS year_opened,
       g.city, g.state_province, g.country
FROM stg_dim_reseller r LEFT JOIN dim_geography g ON g.geography_key = TRY_CAST(r.GeographyKey AS INTEGER);

CREATE OR REPLACE TABLE dim_promotion AS
SELECT CAST(PromotionKey AS INTEGER) AS promotion_key, EnglishPromotionName AS promotion_name,
       ROUND(CAST(DiscountPct AS DOUBLE), 4) AS discount_pct, EnglishPromotionType AS promotion_type,
       EnglishPromotionCategory AS promotion_category, TRY_CAST(MinQty AS INTEGER) AS min_qty, TRY_CAST(MaxQty AS INTEGER) AS max_qty
FROM stg_dim_promotion;

CREATE OR REPLACE TABLE dim_channel AS
SELECT * FROM (VALUES (1, 'Revendeurs'), (2, 'Internet')) AS t(channel_key, channel);

-- -------------------------------------------------------------------------------------
-- Table de faits unifiée
-- -------------------------------------------------------------------------------------
CREATE OR REPLACE TABLE fact_sales AS
WITH u AS (
  SELECT 'Revendeurs' AS channel, SalesOrderNumber AS order_number, SalesOrderLineNumber AS order_line, ProductKey AS product_key,
         ResellerKey AS reseller_key, CAST(NULL AS INTEGER) AS customer_key, SalesTerritoryKey AS territory_key,
         PromotionKey AS promotion_key, CAST(OrderDate AS DATE) AS order_date, OrderQuantity AS quantity,
         UnitPrice AS unit_price, ExtendedAmount AS gross_amount, UnitPriceDiscountPct AS discount_pct, DiscountAmount AS discount_amount,
         ProductStandardCost AS unit_cogs, TotalProductCost AS cogs, SalesAmount AS net_sales
  FROM stg_fact_reseller_sales
  UNION ALL
  SELECT 'Internet', SalesOrderNumber, SalesOrderLineNumber, ProductKey,
         CAST(NULL AS INTEGER), CustomerKey, SalesTerritoryKey, PromotionKey, CAST(OrderDate AS DATE), OrderQuantity,
         UnitPrice, ExtendedAmount, UnitPriceDiscountPct, DiscountAmount, ProductStandardCost, TotalProductCost, SalesAmount
  FROM stg_fact_internet_sales)
SELECT u.channel || '|' || u.order_number || '|' || u.order_line AS sales_line_id,
       u.channel, u.order_number, u.order_line, u.order_date, CAST(strftime(u.order_date, '%Y%m%d') AS INTEGER) AS date_key,
       u.product_key, p.sku, u.reseller_key, u.customer_key, u.territory_key, u.promotion_key,
       u.quantity, u.unit_price, u.gross_amount, u.discount_pct, u.discount_amount, u.net_sales,
       u.unit_cogs, u.cogs,
       u.net_sales - u.cogs AS gross_margin,                 -- marge brute après remises
       u.gross_amount - u.cogs AS margin_before_discount,   -- marge brute avant remises
       (u.net_sales < u.cogs) AS is_below_cost
FROM u LEFT JOIN dim_product p ON p.product_key = u.product_key;
