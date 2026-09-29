-- =====================================================================================
-- 00_staging.sql : chargement brut des CSV AdventureWorksDW (séparateur « | », sans en-tête)
-- =====================================================================================
-- Les fichiers n'ont pas d'en-tête : le schéma est donc écrit explicitement ci-dessous (il reprend
-- le schéma AdventureWorksDW de Microsoft). Les colonnes inutiles à l'analyse (photos, descriptions
-- multilingues, coordonnées personnelles) sont chargées en texte puis ignorées plus loin.
-- ${RAW_DIR} est remplacé par le dossier des CSV au moment de l'exécution.
-- Dialecte : DuckDB (les requêtes des scripts suivants sont en SQL standard : CTE, fenêtres, agrégats).

CREATE OR REPLACE TABLE stg_fact_reseller_sales AS
SELECT * FROM read_csv('${RAW_DIR}/FactResellerSales.csv', delim='|', header=false, nullstr='', quote='', escape='',
  columns={
    'ProductKey':'INTEGER','OrderDateKey':'INTEGER','DueDateKey':'INTEGER','ShipDateKey':'INTEGER',
    'ResellerKey':'INTEGER','EmployeeKey':'INTEGER','PromotionKey':'INTEGER','CurrencyKey':'INTEGER',
    'SalesTerritoryKey':'INTEGER','SalesOrderNumber':'VARCHAR','SalesOrderLineNumber':'INTEGER',
    'RevisionNumber':'INTEGER','OrderQuantity':'INTEGER','UnitPrice':'DECIMAL(19,4)','ExtendedAmount':'DECIMAL(19,4)',
    'UnitPriceDiscountPct':'DOUBLE','DiscountAmount':'DECIMAL(19,4)','ProductStandardCost':'DECIMAL(19,4)',
    'TotalProductCost':'DECIMAL(19,4)','SalesAmount':'DECIMAL(19,4)','TaxAmt':'DECIMAL(19,4)','Freight':'DECIMAL(19,4)',
    'CarrierTrackingNumber':'VARCHAR','CustomerPONumber':'VARCHAR','OrderDate':'TIMESTAMP','DueDate':'TIMESTAMP','ShipDate':'TIMESTAMP'});

CREATE OR REPLACE TABLE stg_fact_internet_sales AS
SELECT * FROM read_csv('${RAW_DIR}/FactInternetSales.csv', delim='|', header=false, nullstr='', quote='', escape='',
  columns={
    'ProductKey':'INTEGER','OrderDateKey':'INTEGER','DueDateKey':'INTEGER','ShipDateKey':'INTEGER',
    'CustomerKey':'INTEGER','PromotionKey':'INTEGER','CurrencyKey':'INTEGER','SalesTerritoryKey':'INTEGER',
    'SalesOrderNumber':'VARCHAR','SalesOrderLineNumber':'INTEGER','RevisionNumber':'INTEGER','OrderQuantity':'INTEGER',
    'UnitPrice':'DECIMAL(19,4)','ExtendedAmount':'DECIMAL(19,4)','UnitPriceDiscountPct':'DOUBLE',
    'DiscountAmount':'DECIMAL(19,4)','ProductStandardCost':'DECIMAL(19,4)','TotalProductCost':'DECIMAL(19,4)',
    'SalesAmount':'DECIMAL(19,4)','TaxAmt':'DECIMAL(19,4)','Freight':'DECIMAL(19,4)','CarrierTrackingNumber':'VARCHAR',
    'CustomerPONumber':'VARCHAR','OrderDate':'TIMESTAMP','DueDate':'TIMESTAMP','ShipDate':'TIMESTAMP'});

CREATE OR REPLACE TABLE stg_dim_product AS
SELECT * FROM read_csv('${RAW_DIR}/DimProduct.csv', delim='|', header=false, nullstr='', quote='', escape='', all_varchar=true,
  columns={
    'ProductKey':'VARCHAR','ProductAlternateKey':'VARCHAR','ProductSubcategoryKey':'VARCHAR','WeightUnitMeasureCode':'VARCHAR',
    'SizeUnitMeasureCode':'VARCHAR','EnglishProductName':'VARCHAR','SpanishProductName':'VARCHAR','FrenchProductName':'VARCHAR',
    'StandardCost':'VARCHAR','FinishedGoodsFlag':'VARCHAR','Color':'VARCHAR','SafetyStockLevel':'VARCHAR','ReorderPoint':'VARCHAR',
    'ListPrice':'VARCHAR','Size':'VARCHAR','SizeRange':'VARCHAR','Weight':'VARCHAR','DaysToManufacture':'VARCHAR',
    'ProductLine':'VARCHAR','DealerPrice':'VARCHAR','Class':'VARCHAR','Style':'VARCHAR','ModelName':'VARCHAR','LargePhoto':'VARCHAR',
    'EnglishDescription':'VARCHAR','FrenchDescription':'VARCHAR','ChineseDescription':'VARCHAR','ArabicDescription':'VARCHAR',
    'HebrewDescription':'VARCHAR','ThaiDescription':'VARCHAR','GermanDescription':'VARCHAR','JapaneseDescription':'VARCHAR',
    'TurkishDescription':'VARCHAR','StartDate':'VARCHAR','EndDate':'VARCHAR','Status':'VARCHAR'});

CREATE OR REPLACE TABLE stg_dim_product_subcategory AS
SELECT * FROM read_csv('${RAW_DIR}/DimProductSubcategory.csv', delim='|', header=false, nullstr='', quote='', escape='',
  columns={'ProductSubcategoryKey':'INTEGER','ProductSubcategoryAlternateKey':'INTEGER','EnglishProductSubcategoryName':'VARCHAR',
           'SpanishProductSubcategoryName':'VARCHAR','FrenchProductSubcategoryName':'VARCHAR','ProductCategoryKey':'INTEGER'});

CREATE OR REPLACE TABLE stg_dim_product_category AS
SELECT * FROM read_csv('${RAW_DIR}/DimProductCategory.csv', delim='|', header=false, nullstr='', quote='', escape='',
  columns={'ProductCategoryKey':'INTEGER','ProductCategoryAlternateKey':'INTEGER','EnglishProductCategoryName':'VARCHAR',
           'SpanishProductCategoryName':'VARCHAR','FrenchProductCategoryName':'VARCHAR'});

CREATE OR REPLACE TABLE stg_dim_date AS
SELECT * FROM read_csv('${RAW_DIR}/DimDate.csv', delim='|', header=false, nullstr='', quote='', escape='',
  columns={'DateKey':'INTEGER','FullDateAlternateKey':'DATE','DayNumberOfWeek':'INTEGER','EnglishDayNameOfWeek':'VARCHAR',
           'SpanishDayNameOfWeek':'VARCHAR','FrenchDayNameOfWeek':'VARCHAR','DayNumberOfMonth':'INTEGER','DayNumberOfYear':'INTEGER',
           'WeekNumberOfYear':'INTEGER','EnglishMonthName':'VARCHAR','SpanishMonthName':'VARCHAR','FrenchMonthName':'VARCHAR',
           'MonthNumberOfYear':'INTEGER','CalendarQuarter':'INTEGER','CalendarYear':'INTEGER','CalendarSemester':'INTEGER',
           'FiscalQuarter':'INTEGER','FiscalYear':'INTEGER','FiscalSemester':'INTEGER'});

CREATE OR REPLACE TABLE stg_dim_reseller AS
SELECT * FROM read_csv('${RAW_DIR}/DimReseller.csv', delim='|', header=false, nullstr='', quote='', escape='', all_varchar=true,
  columns={'ResellerKey':'VARCHAR','GeographyKey':'VARCHAR','ResellerAlternateKey':'VARCHAR','Phone':'VARCHAR','BusinessType':'VARCHAR',
           'ResellerName':'VARCHAR','NumberEmployees':'VARCHAR','OrderFrequency':'VARCHAR','OrderMonth':'VARCHAR','FirstOrderYear':'VARCHAR',
           'LastOrderYear':'VARCHAR','ProductLine':'VARCHAR','AddressLine1':'VARCHAR','AddressLine2':'VARCHAR','AnnualSales':'VARCHAR',
           'BankName':'VARCHAR','MinPaymentType':'VARCHAR','MinPaymentAmount':'VARCHAR','AnnualRevenue':'VARCHAR','YearOpened':'VARCHAR'});

CREATE OR REPLACE TABLE stg_dim_customer AS
SELECT * FROM read_csv('${RAW_DIR}/DimCustomer.csv', delim='|', header=false, nullstr='', quote='', escape='', all_varchar=true,
  columns={'CustomerKey':'VARCHAR','GeographyKey':'VARCHAR','CustomerAlternateKey':'VARCHAR','Title':'VARCHAR','FirstName':'VARCHAR',
           'MiddleName':'VARCHAR','LastName':'VARCHAR','NameStyle':'VARCHAR','BirthDate':'VARCHAR','MaritalStatus':'VARCHAR','Suffix':'VARCHAR',
           'Gender':'VARCHAR','EmailAddress':'VARCHAR','YearlyIncome':'VARCHAR','TotalChildren':'VARCHAR','NumberChildrenAtHome':'VARCHAR',
           'EnglishEducation':'VARCHAR','SpanishEducation':'VARCHAR','FrenchEducation':'VARCHAR','EnglishOccupation':'VARCHAR',
           'SpanishOccupation':'VARCHAR','FrenchOccupation':'VARCHAR','HouseOwnerFlag':'VARCHAR','NumberCarsOwned':'VARCHAR',
           'AddressLine1':'VARCHAR','AddressLine2':'VARCHAR','Phone':'VARCHAR','DateFirstPurchase':'VARCHAR','CommuteDistance':'VARCHAR'});

CREATE OR REPLACE TABLE stg_dim_geography AS
SELECT * FROM read_csv('${RAW_DIR}/DimGeography.csv', delim='|', header=false, nullstr='', quote='', escape='', all_varchar=true,
  columns={'GeographyKey':'VARCHAR','City':'VARCHAR','StateProvinceCode':'VARCHAR','StateProvinceName':'VARCHAR','CountryRegionCode':'VARCHAR',
           'EnglishCountryRegionName':'VARCHAR','SpanishCountryRegionName':'VARCHAR','FrenchCountryRegionName':'VARCHAR','PostalCode':'VARCHAR',
           'SalesTerritoryKey':'VARCHAR','IpAddressLocator':'VARCHAR'});

CREATE OR REPLACE TABLE stg_dim_sales_territory AS
SELECT * FROM read_csv('${RAW_DIR}/DimSalesTerritory.csv', delim='|', header=false, nullstr='', quote='', escape='', all_varchar=true,
  columns={'SalesTerritoryKey':'VARCHAR','SalesTerritoryAlternateKey':'VARCHAR','SalesTerritoryRegion':'VARCHAR',
           'SalesTerritoryCountry':'VARCHAR','SalesTerritoryGroup':'VARCHAR','SalesTerritoryImage':'VARCHAR'});

CREATE OR REPLACE TABLE stg_dim_promotion AS
SELECT * FROM read_csv('${RAW_DIR}/DimPromotion.csv', delim='|', header=false, nullstr='', quote='', escape='', all_varchar=true,
  columns={'PromotionKey':'VARCHAR','PromotionAlternateKey':'VARCHAR','EnglishPromotionName':'VARCHAR','SpanishPromotionName':'VARCHAR',
           'FrenchPromotionName':'VARCHAR','DiscountPct':'VARCHAR','EnglishPromotionType':'VARCHAR','SpanishPromotionType':'VARCHAR',
           'FrenchPromotionType':'VARCHAR','EnglishPromotionCategory':'VARCHAR','SpanishPromotionCategory':'VARCHAR',
           'FrenchPromotionCategory':'VARCHAR','StartDate':'VARCHAR','EndDate':'VARCHAR','MinQty':'VARCHAR','MaxQty':'VARCHAR'});

CREATE OR REPLACE TABLE stg_dim_currency AS
SELECT * FROM read_csv('${RAW_DIR}/DimCurrency.csv', delim='|', header=false, nullstr='', quote='', escape='',
  columns={'CurrencyKey':'INTEGER','CurrencyAlternateKey':'VARCHAR','CurrencyName':'VARCHAR'});
