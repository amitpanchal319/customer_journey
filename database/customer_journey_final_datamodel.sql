-- ============================================================================
--  CUSTOMER JOURNEY TOOL — FINAL DATA MODEL
--  Database  : Unicorn  |  Schema : public
--  Built for : Libas (Shopify = Online, EBO = Offline)
--
--  OBJECTS CREATED (your existing views/tables are NEVER modified):
--
--    Utility Functions (2)
--      fn_clean_combo()        — strips leading junk chars from combo key
--      fn_size_group()         — maps "sizeNew" to Adult/Kids/Footwear/OneSize
--
--    Materialized Views — Layer 3 Master (1)
--      cust_master_profile     — ONE ROW PER CUSTOMER, all metrics, all filters
--                                95% of frontend queries hit ONLY this view
--
--    Materialized Views — Analytics (2)
--      cust_monthly_cohort_mv  — cohort retention grid, MoM new vs repeat
--      store_summary_mv        — per-store repeat, retention, LTV, migration
--
--  YOUR EXISTING OBJECTS (read-only, never touched):
--      cust_email_ph_master        item_master
--      cust_details_view           cust_ebo_salescombo_view
--      cust_osdcombo_view          cust_rtcombo_view
--
--  FRONTEND QUERY PATTERN:
--      All filter screens  → SELECT … FROM cust_master_profile WHERE <indexed_col> = $1
--      Cohort screen       → SELECT … FROM cust_monthly_cohort_mv
--      Store screen        → SELECT … FROM store_summary_mv
--      Customer timeline   → SELECT … FROM cust_ebo_salescombo_view / cust_osdcombo_view
--                            WHERE combo = $1  (point lookup, fast)
--
--  RFM THRESHOLDS (calibrated from your real data — 1.6M customers):
--      Monetary  : <1400 | 1400-2500 | 2500-5000 | 5000-15000 | >15000
--      Frequency : 1 | 2 | 3-4 | 5-9 | 10+   (64% are 1-order customers)
--      Recency   : >365d | 181-365d | 91-180d | 31-90d | <=30d
--
--  DAILY REFRESH ORDER (pg_cron):
--      02:00 AM IST → cust_master_profile
--      02:30 AM IST → cust_monthly_cohort_mv + store_summary_mv
-- ============================================================================


-- ============================================================================
-- SECTION 1 : UTILITY FUNCTIONS
-- ============================================================================

-- ----------------------------------------------------------------------------
-- fn_clean_combo
-- Strips leading junk characters that appear in source data
-- e.g.  -user@gmail.com-9999  →  user@gmail.com-9999
--       !user@gmail.com-9999  →  user@gmail.com-9999
-- Uses LTRIM (not REGEXP) for compatibility with all PostgreSQL collations
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.fn_clean_combo(p_combo TEXT)
RETURNS TEXT
LANGUAGE sql
IMMUTABLE
PARALLEL SAFE
AS $$
    SELECT LTRIM(TRIM(p_combo), '-!''`~+')
$$;


-- ----------------------------------------------------------------------------
-- fn_size_group
-- Normalises item_master."sizeNew" into broad groups for frontend filter
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.fn_size_group(p_size TEXT)
RETURNS TEXT
LANGUAGE sql
IMMUTABLE
PARALLEL SAFE
AS $$
    SELECT CASE
        WHEN p_size IN ('XS','S','M','L','XL','2XL','3XL','4XL','5XL','6XL','6Xl')
             THEN 'Adult Standard'
        WHEN p_size LIKE '%Y'
             THEN 'Kids'
        WHEN p_size IN ('1','2','3','4','5','6','7','8','9','10')
             THEN 'Footwear'
        WHEN p_size = 'One Size'
             THEN 'One Size'
        ELSE 'Other'
    END
$$;


-- ============================================================================
-- SECTION 2 : cust_master_profile
-- The single source of truth for the Customer Journey Tool frontend.
-- One row per customer. All filters are pre-computed indexed columns.
-- No runtime joins required for any filter screen.
-- ============================================================================

DROP MATERIALIZED VIEW IF EXISTS public.cust_master_profile CASCADE;

CREATE MATERIALIZED VIEW public.cust_master_profile AS

-- ── Step A: Clean and aggregate EBO transactions ─────────────────────────────
WITH ebo_base AS (
    SELECT
        public.fn_clean_combo(combo)            AS combo,
        invoice_date,
        invoice_associate_name,
        barcode,
        nob,
        nsq,
        order_amount,
        rt_qty,
        rt_amount
    FROM public.cust_ebo_salescombo_view
    WHERE combo IS NOT NULL
      AND combo <> ''
      AND order_amount >= 0
),

ebo_agg AS (
    SELECT
        combo,

        -- Volume
        SUM(nob)                                                AS total_ebo_bills,
        SUM(nsq)                                                AS total_ebo_skus,
        COUNT(DISTINCT invoice_date)                            AS ebo_visit_days,

        -- Revenue
        SUM(order_amount)                                       AS total_ebo_spend,
        ROUND(AVG(order_amount)::NUMERIC, 0)                    AS ebo_aov,
        MAX(order_amount)                                       AS ebo_max_bill,

        -- Returns
        COALESCE(SUM(rt_qty), 0)                                AS ebo_return_qty,
        COALESCE(SUM(rt_amount), 0)                             AS ebo_return_amount,

        -- Timeline
        MIN(invoice_date)                                       AS first_ebo_date,
        MAX(invoice_date)                                       AS last_ebo_date,
        (CURRENT_DATE - MAX(invoice_date))                      AS ebo_days_since_last,

        -- Primary store (most visited)
        MODE() WITHIN GROUP (ORDER BY invoice_associate_name)   AS primary_store

    FROM ebo_base
    GROUP BY combo
),

-- Second EBO purchase date (for first-to-second gap)
ebo_second AS (
    SELECT DISTINCT ON (combo)
        combo,
        invoice_date                                            AS second_ebo_date
    FROM (
        SELECT
            combo,
            invoice_date,
            ROW_NUMBER() OVER (
                PARTITION BY combo ORDER BY invoice_date ASC
            )                                                   AS rn
        FROM ebo_base
    ) ranked
    WHERE rn = 2
),

-- Same-month repeat flag for EBO
ebo_same_month AS (
    SELECT DISTINCT combo
    FROM (
        SELECT
            combo,
            DATE_TRUNC('month', invoice_date)                   AS mo,
            COUNT(DISTINCT invoice_date)                        AS visits
        FROM ebo_base
        GROUP BY combo, DATE_TRUNC('month', invoice_date)
    ) x
    WHERE visits >= 2
),

-- ── Step B: Clean and aggregate Shopify transactions ─────────────────────────
shp_base AS (
    SELECT
        public.fn_clean_combo(combo)            AS combo,
        channel_order_date,
        client_sku_id_ean,
        order_count,
        order_qty,
        cod_qty,
        ncod_qty,
        cancelled_qty,
        customer_canclled_qty,
        seller_cancelled_qty,
        packed_dispatched_qty,
        order_amount
    FROM public.cust_osdcombo_view
    WHERE combo IS NOT NULL
      AND combo <> ''
      AND order_amount >= 0
      -- Exclude B2B / marketplace accounts at source (only place LIKE is used)
      AND combo NOT LIKE '%myshopify%'
      AND combo NOT LIKE '%nitro.co%'
      AND combo NOT LIKE '%lenskartomni%'
      AND combo NOT LIKE '%greenevolve%'
      AND combo NOT LIKE '%swiss-beauty%'
),

shp_agg AS (
    SELECT
        combo,

        -- Volume
        SUM(order_count)                                        AS total_online_orders,
        SUM(order_qty)                                          AS total_online_qty,
        COUNT(DISTINCT channel_order_date)                      AS online_order_days,

        -- Revenue
        SUM(order_amount)                                       AS total_online_spend,
        ROUND(AVG(order_amount)::NUMERIC, 0)                    AS online_aov,
        MAX(order_amount)                                       AS online_max_order,

        -- Payment split
        SUM(cod_qty)                                            AS total_cod_qty,
        SUM(ncod_qty)                                           AS total_prepaid_qty,
        ROUND(SUM(cod_qty)::NUMERIC
            / NULLIF(SUM(order_count), 0) * 100, 1)            AS cod_pct,

        -- Cancellations
        SUM(cancelled_qty)                                      AS total_cancelled_qty,
        SUM(customer_canclled_qty)                              AS cust_cancelled_qty,
        SUM(seller_cancelled_qty)                               AS seller_cancelled_qty,
        ROUND(SUM(cancelled_qty)::NUMERIC
            / NULLIF(SUM(order_qty), 0) * 100, 1)              AS cancel_rate_pct,
        ROUND(SUM(customer_canclled_qty)::NUMERIC
            / NULLIF(SUM(order_qty), 0) * 100, 1)              AS cust_cancel_rate_pct,

        -- Fulfilment
        SUM(packed_dispatched_qty)                              AS total_dispatched_qty,
        ROUND(SUM(packed_dispatched_qty)::NUMERIC
            / NULLIF(SUM(order_qty), 0) * 100, 1)              AS fulfilment_rate_pct,

        -- COD reliability score (0–100)
        -- Formula: 100 minus penalty for high COD% and high customer-cancel%
        -- Higher score = more reliable customer to fulfil
        GREATEST(0,
            ROUND((100
                - (SUM(cod_qty)::NUMERIC
                    / NULLIF(SUM(order_count), 0) * 40)
                - (SUM(customer_canclled_qty)::NUMERIC
                    / NULLIF(SUM(order_qty), 0) * 60)
            )::NUMERIC, 1)
        )                                                       AS cod_reliability_score,

        -- Timeline
        MIN(channel_order_date)                                 AS first_online_date,
        MAX(channel_order_date)                                 AS last_online_date,
        (CURRENT_DATE - MAX(channel_order_date))                AS online_days_since_last

    FROM shp_base
    GROUP BY combo
),

-- Second Shopify purchase date
shp_second AS (
    SELECT DISTINCT ON (combo)
        combo,
        channel_order_date                                      AS second_online_date
    FROM (
        SELECT
            combo,
            channel_order_date,
            ROW_NUMBER() OVER (
                PARTITION BY combo ORDER BY channel_order_date ASC
            )                                                   AS rn
        FROM shp_base
    ) ranked
    WHERE rn = 2
),

-- Same-month repeat flag for Shopify
shp_same_month AS (
    SELECT DISTINCT combo
    FROM (
        SELECT
            combo,
            DATE_TRUNC('month', channel_order_date)             AS mo,
            COUNT(DISTINCT channel_order_date)                  AS orders
        FROM shp_base
        GROUP BY combo, DATE_TRUNC('month', channel_order_date)
    ) x
    WHERE orders >= 2
),

-- ── Step C: Returns aggregation ───────────────────────────────────────────────
rt_agg AS (
    SELECT
        public.fn_clean_combo(combo)                            AS combo,

        SUM(rt_qty)                                             AS total_returns,
        -- cr_qty = real customer dissatisfaction returns
        SUM(cr_qty)                                             AS customer_returns,
        -- rto_qty = courier failure, NOT customer's fault
        SUM(rto_qty)                                            AS rto_returns,
        SUM(blank_qty)                                          AS unclassified_returns,
        SUM(pass_qty)                                           AS qc_pass_qty,
        SUM(fail_qty)                                           AS qc_fail_qty,
        ROUND(SUM(pass_qty)::NUMERIC
            / NULLIF(SUM(rt_qty), 0) * 100, 1)                 AS qc_pass_rate_pct,
        ROUND(AVG(
            CASE
                WHEN return_order_processed_time IS NOT NULL
                 AND channel_order_date IS NOT NULL
                THEN (return_order_processed_time - channel_order_date)
            END
        )::NUMERIC, 1)                                          AS avg_return_days,
        MAX(return_order_processed_time)                        AS last_return_date

    FROM public.cust_rtcombo_view
    WHERE combo IS NOT NULL AND combo <> ''
    GROUP BY public.fn_clean_combo(combo)
),

-- ── Step D: Geo — best non-null row per customer ──────────────────────────────
geo_ranked AS (
    SELECT
        public.fn_clean_combo(combo)                            AS combo,
        consumer_name,
        consumer_pincode,
        consumer_city,
        consumer_state,
        consumer_zone,
        store_city,
        ROW_NUMBER() OVER (
            PARTITION BY public.fn_clean_combo(combo)
            ORDER BY
                (CASE WHEN consumer_pincode IS NOT NULL THEN 1 ELSE 0 END) DESC,
                (CASE WHEN consumer_city    IS NOT NULL THEN 1 ELSE 0 END) DESC,
                (CASE WHEN consumer_state   IS NOT NULL THEN 1 ELSE 0 END) DESC
        )                                                       AS rn
    FROM public.cust_details_view
    WHERE combo IS NOT NULL AND combo <> ''
),

geo AS (
    SELECT
        combo,
        INITCAP(TRIM(consumer_name))                            AS consumer_name,
        consumer_pincode,
        UPPER(TRIM(consumer_city))                              AS consumer_city,
        UPPER(TRIM(consumer_state))                             AS consumer_state,
        UPPER(TRIM(consumer_zone))                              AS consumer_zone,
        store_city
    FROM geo_ranked
    WHERE rn = 1
),

-- ── Step E: Category + size via item_master join ──────────────────────────────
-- EBO SKUs enriched with category / size / brand
ebo_items AS (
    SELECT
        public.fn_clean_combo(e.combo)                          AS combo,
        UPPER(TRIM(im."itemCategoryCode"))                        AS category,
        UPPER(TRIM(im.brand))                                   AS brand,
        TRIM(im."sizeNew")                                        AS size_raw,
        public.fn_size_group(TRIM(im."sizeNew"))                  AS size_group,
        e.order_amount
    FROM public.cust_ebo_salescombo_view e
    INNER JOIN public.item_master im
            ON im.ean = e.barcode
    WHERE e.combo IS NOT NULL
      AND im."ean" IS NOT NULL
),

-- Shopify SKUs enriched with category / size / brand
shp_items AS (
    SELECT
        public.fn_clean_combo(s.combo)                          AS combo,
        UPPER(TRIM(im."itemCategoryCode"))                        AS category,
        UPPER(TRIM(im.brand))                                   AS brand,
        TRIM(im."sizeNew")                                        AS size_raw,
        public.fn_size_group(TRIM(im."sizeNew"))                  AS size_group,
        s.order_amount
    FROM public.cust_osdcombo_view s
    INNER JOIN public.item_master im
            ON im."itemNo" = s.client_sku_id_ean
    WHERE s.combo IS NOT NULL
      AND s.combo NOT LIKE '%myshopify%'
      AND im."ean" IS NOT NULL
),

-- All items combined
all_items AS (
    SELECT * FROM ebo_items
    UNION ALL
    SELECT * FROM shp_items
),

-- Spend per customer per category
cat_spend AS (
    SELECT
        combo,
        category,
        SUM(order_amount)                                       AS cat_spend,
        COUNT(*)                                                AS cat_txns
    FROM all_items
    GROUP BY combo, category
),

-- Rank categories by spend per customer
cat_ranked AS (
    SELECT
        combo,
        category,
        cat_spend,
        cat_txns,
        ROW_NUMBER() OVER (
            PARTITION BY combo ORDER BY cat_spend DESC
        )                                                       AS cat_rank,
        SUM(cat_spend) OVER (PARTITION BY combo)               AS total_cat_spend,
        COUNT(category) OVER (PARTITION BY combo)     AS total_categories
    FROM cat_spend
),

cat_agg AS (
    SELECT
        combo,
        MAX(total_categories)                                   AS total_categories,
        MAX(CASE WHEN cat_rank = 1 THEN category END)          AS top_category,
        MAX(CASE WHEN cat_rank = 2 THEN category END)          AS second_category,
        ROUND((MAX(CASE WHEN cat_rank = 1 THEN cat_spend END)
            / NULLIF(MAX(total_cat_spend), 0) * 100)::NUMERIC, 1) AS top_category_spend_pct,

        -- Single-category: all purchases in exactly one category
        CASE WHEN MAX(total_categories) = 1
             THEN TRUE ELSE FALSE END                           AS is_single_category,

        -- Dominant-category: top category >= 80% of spend
        CASE WHEN ROUND((MAX(CASE WHEN cat_rank = 1 THEN cat_spend END)
                / NULLIF(MAX(total_cat_spend), 0) * 100)::NUMERIC, 1) >= 80
             THEN TRUE ELSE FALSE END                           AS is_dominant_category
    FROM cat_ranked
    GROUP BY combo
),

-- Top brand per customer
brand_agg AS (
    SELECT DISTINCT ON (combo)
        combo,
        brand                                                   AS top_brand,
        COUNT(*) OVER (PARTITION BY combo)                      AS distinct_brands
    FROM all_items
    WHERE brand IS NOT NULL
    GROUP BY combo, brand
    ORDER BY combo, COUNT(*) DESC
),

-- Size behaviour per customer
size_agg AS (
    SELECT
        combo,
        COUNT(DISTINCT size_raw)                                AS distinct_sizes,
        COUNT(DISTINCT size_raw) FILTER (
            WHERE size_group = 'Adult Standard'
        )                                                       AS adult_sizes,
        STRING_AGG(DISTINCT size_raw, '+' ORDER BY size_raw)
            FILTER (WHERE size_group = 'Adult Standard')        AS size_combination
    FROM all_items
    WHERE size_raw IS NOT NULL
    GROUP BY combo
),

-- ── Step F: Final assembly ────────────────────────────────────────────────────
-- Anchored on cust_email_ph_master (cleanest, one row per customer)
-- All CTEs above joined as LEFT JOINs — no row multiplication possible
base AS (
    SELECT
        m.unq_id,
        public.fn_clean_combo(m.combo)                          AS combo_clean,
        m.combo                                                 AS combo_raw,
        m.email,
        m.phone,
        m.platform,
        m.in_ebo,
        m.in_shopify,
        m.first_seen_at::DATE                                   AS first_seen_date,
        m.last_updated_at::DATE                                 AS last_updated_date,
        m.min_ebo_date,
        m.max_ebo_date,
        m.min_shp_date,
        m.max_shp_date
    FROM public.cust_email_ph_master m
)

SELECT

    -- ── Identity ──────────────────────────────────────────────────────────────
    b.unq_id,
    b.combo_raw                                                 AS combo,
    b.email,
    b.phone,
    b.platform,
    b.in_ebo,
    b.in_shopify,
    b.first_seen_date,
    b.last_updated_date,

    -- ── Geography (pre-computed, equality filters only) ───────────────────────
    g.consumer_name,
    g.consumer_pincode,
    g.consumer_city,
    g.consumer_state,
    g.consumer_zone,
    g.store_city,

    -- ── EBO Metrics ───────────────────────────────────────────────────────────
    COALESCE(e.total_ebo_bills, 0)                              AS total_ebo_bills,
    COALESCE(e.total_ebo_skus, 0)                               AS total_ebo_skus,
    COALESCE(e.ebo_visit_days, 0)                               AS ebo_visit_days,
    COALESCE(e.total_ebo_spend, 0)                              AS total_ebo_spend,
    e.ebo_aov,
    e.ebo_max_bill,
    COALESCE(e.ebo_return_qty, 0)                               AS ebo_return_qty,
    COALESCE(e.ebo_return_amount, 0)                            AS ebo_return_amount,
    b.min_ebo_date                                              AS first_ebo_date,
    b.max_ebo_date                                              AS last_ebo_date,
    es.second_ebo_date,
    CASE
        WHEN es.second_ebo_date IS NOT NULL
        THEN (es.second_ebo_date - b.min_ebo_date)
    END                                                         AS days_ebo_1st_to_2nd,
    e.ebo_days_since_last,
    CASE WHEN esm.combo IS NOT NULL THEN TRUE ELSE FALSE END    AS ebo_same_month_repeat,
    e.primary_store,

    -- ── Shopify Metrics ───────────────────────────────────────────────────────
    COALESCE(s.total_online_orders, 0)                          AS total_online_orders,
    COALESCE(s.total_online_qty, 0)                             AS total_online_qty,
    COALESCE(s.online_order_days, 0)                            AS online_order_days,
    COALESCE(s.total_online_spend, 0)                           AS total_online_spend,
    s.online_aov,
    s.online_max_order,
    COALESCE(s.total_cod_qty, 0)                                AS total_cod_qty,
    COALESCE(s.total_prepaid_qty, 0)                            AS total_prepaid_qty,
    COALESCE(s.cod_pct, 0)                                      AS cod_pct,
    COALESCE(s.cancel_rate_pct, 0)                              AS cancel_rate_pct,
    COALESCE(s.cust_cancel_rate_pct, 0)                         AS cust_cancel_rate_pct,
    COALESCE(s.fulfilment_rate_pct, 0)                          AS fulfilment_rate_pct,
    s.cod_reliability_score,
    b.min_shp_date                                              AS first_online_date,
    b.max_shp_date                                              AS last_online_date,
    ss.second_online_date,
    CASE
        WHEN ss.second_online_date IS NOT NULL
        THEN (ss.second_online_date - b.min_shp_date)
    END                                                         AS days_online_1st_to_2nd,
    s.online_days_since_last,
    CASE WHEN ssm.combo IS NOT NULL THEN TRUE ELSE FALSE END    AS online_same_month_repeat,

    -- ── Returns Metrics ───────────────────────────────────────────────────────
    COALESCE(r.total_returns, 0)                                AS total_returns,
    COALESCE(r.customer_returns, 0)                             AS customer_returns,
    COALESCE(r.rto_returns, 0)                                  AS rto_returns,
    COALESCE(r.qc_pass_rate_pct, 0)                             AS qc_pass_rate_pct,
    COALESCE(r.avg_return_days, 0)                              AS avg_return_days,
    r.last_return_date,

    -- ── Category & Product (from item_master join) ────────────────────────────
    ca.top_category,
    ca.second_category,
    ca.top_category_spend_pct,
    COALESCE(ca.total_categories, 0)                            AS total_categories,
    COALESCE(ca.is_single_category, FALSE)                      AS is_single_category,
    COALESCE(ca.is_dominant_category, FALSE)                    AS is_dominant_category,

    -- Category label used as frontend filter chip
    -- e.g. "LEHENGA Only", "KURTA SET Dominant", "Multi-Category"
    CASE
        WHEN ca.is_single_category  = TRUE  THEN ca.top_category || ' Only'
        WHEN ca.is_dominant_category = TRUE  THEN ca.top_category || ' Dominant'
        WHEN ca.top_category IS NOT NULL     THEN 'Multi-Category'
        ELSE                                      'Uncategorised'
    END                                                         AS category_label,

    br.top_brand,
    COALESCE(br.distinct_brands, 0)                             AS distinct_brands,

    -- ── Size Behaviour (frontend filter: Single Size / Multi Size) ─────────────
    COALESCE(sz.distinct_sizes, 0)                              AS distinct_sizes,
    COALESCE(sz.adult_sizes, 0)                                 AS adult_sizes,
    sz.size_combination,                                        -- e.g. "L+M+XL"
    CASE
        WHEN sz.adult_sizes = 0 THEN 'No Size Data'
        WHEN sz.adult_sizes = 1 THEN 'Single Size'
        ELSE                        'Multi Size'
    END                                                         AS size_behaviour,

    -- ── Combined Lifetime Metrics ─────────────────────────────────────────────
    COALESCE(e.total_ebo_spend, 0)
        + COALESCE(s.total_online_spend, 0)                     AS total_lifetime_spend,

    COALESCE(e.total_ebo_bills, 0)
        + COALESCE(s.total_online_orders, 0)                    AS total_lifetime_orders,

    -- Online spend share % (useful for migration analysis)
    CASE
        WHEN (COALESCE(e.total_ebo_spend, 0)
            + COALESCE(s.total_online_spend, 0)) > 0
        THEN ROUND(
            (COALESCE(s.total_online_spend, 0)::NUMERIC
            / (COALESCE(e.total_ebo_spend, 0)
             + COALESCE(s.total_online_spend, 0)) * 100)::NUMERIC, 1)
    END                                                         AS online_spend_pct,

    -- Days since last purchase across ANY channel
    LEAST(
        COALESCE(e.ebo_days_since_last, 99999),
        COALESCE(s.online_days_since_last, 99999)
    )                                                           AS days_since_last_purchase,

    -- Days from first to second purchase (cross-channel: whichever is shorter)
    LEAST(
        COALESCE(
            CASE WHEN es.second_ebo_date IS NOT NULL
                 THEN (es.second_ebo_date - b.min_ebo_date) END,
            99999),
        COALESCE(
            CASE WHEN ss.second_online_date IS NOT NULL
                 THEN (ss.second_online_date - b.min_shp_date) END,
            99999)
    )                                                           AS days_1st_to_2nd_purchase,

    -- ── Retention Flags (frontend filter: retained_30d = true/false) ──────────
    CASE
        WHEN LEAST(
            COALESCE(CASE WHEN es.second_ebo_date IS NOT NULL
                THEN es.second_ebo_date - b.min_ebo_date END, 99999),
            COALESCE(CASE WHEN ss.second_online_date IS NOT NULL
                THEN ss.second_online_date - b.min_shp_date END, 99999)
        ) <= 30  THEN TRUE ELSE FALSE
    END                                                         AS retained_30d,

    CASE
        WHEN LEAST(
            COALESCE(CASE WHEN es.second_ebo_date IS NOT NULL
                THEN es.second_ebo_date - b.min_ebo_date END, 99999),
            COALESCE(CASE WHEN ss.second_online_date IS NOT NULL
                THEN ss.second_online_date - b.min_shp_date END, 99999)
        ) <= 60  THEN TRUE ELSE FALSE
    END                                                         AS retained_60d,

    CASE
        WHEN LEAST(
            COALESCE(CASE WHEN es.second_ebo_date IS NOT NULL
                THEN es.second_ebo_date - b.min_ebo_date END, 99999),
            COALESCE(CASE WHEN ss.second_online_date IS NOT NULL
                THEN ss.second_online_date - b.min_shp_date END, 99999)
        ) <= 90  THEN TRUE ELSE FALSE
    END                                                         AS retained_90d,

    -- Same-month repeat (either channel)
    CASE
        WHEN esm.combo IS NOT NULL OR ssm.combo IS NOT NULL
        THEN TRUE ELSE FALSE
    END                                                         AS same_month_repeat,

    -- ── Customer Type (frontend filter chip: New / Repeat) ────────────────────
    CASE
        WHEN COALESCE(e.total_ebo_bills, 0)
           + COALESCE(s.total_online_orders, 0) = 1 THEN 'New'
        WHEN COALESCE(e.total_ebo_bills, 0)
           + COALESCE(s.total_online_orders, 0) >= 2 THEN 'Repeat'
        ELSE 'Unknown'
    END                                                         AS customer_type,

    -- ── Purchase Frequency Bucket (frontend filter) ───────────────────────────
    -- Calibrated: 64% are 1-order, 82% are 1-2 orders
    CASE
        WHEN COALESCE(e.total_ebo_bills,0)
           + COALESCE(s.total_online_orders,0) = 1  THEN '1 Order'
        WHEN COALESCE(e.total_ebo_bills,0)
           + COALESCE(s.total_online_orders,0) = 2  THEN '2 Orders'
        WHEN COALESCE(e.total_ebo_bills,0)
           + COALESCE(s.total_online_orders,0) <= 4  THEN '3-4 Orders'
        WHEN COALESCE(e.total_ebo_bills,0)
           + COALESCE(s.total_online_orders,0) <= 9  THEN '5-9 Orders'
        ELSE                                              '10+ Orders'
    END                                                         AS frequency_bucket,

    -- ── Channel Journey (frontend filter) ────────────────────────────────────
    CASE
        WHEN b.in_ebo AND b.in_shopify       THEN 'Both'
        WHEN b.in_ebo AND NOT b.in_shopify   THEN 'Offline Only'
        WHEN b.in_shopify AND NOT b.in_ebo   THEN 'Online Only'
        ELSE                                      'Unknown'
    END                                                         AS channel_journey,

    -- ── Migration Type (frontend filter) ─────────────────────────────────────
    -- EBO_first : started offline, moved online (true migration)
    -- Shopify_first : started online, then visited store
    -- Both_same_time : first recorded dates in same month
    -- EBO_only / Shopify_only : single channel
    CASE
        WHEN b.in_ebo AND b.in_shopify
             AND b.min_ebo_date < b.min_shp_date   THEN 'EBO First'
        WHEN b.in_ebo AND b.in_shopify
             AND b.min_shp_date < b.min_ebo_date   THEN 'Shopify First'
        WHEN b.in_ebo AND b.in_shopify             THEN 'Both Same Time'
        WHEN b.in_ebo AND NOT b.in_shopify         THEN 'EBO Only'
        WHEN b.in_shopify AND NOT b.in_ebo         THEN 'Shopify Only'
        ELSE                                            'Unknown'
    END                                                         AS migration_type,

    -- Migration lag: days between first EBO and first Shopify visit
    CASE
        WHEN b.in_ebo AND b.in_shopify
        THEN ABS(b.min_shp_date - b.min_ebo_date)
    END                                                         AS migration_lag_days,

    -- AOV difference after migration (online vs offline)
    CASE
        WHEN s.online_aov IS NOT NULL AND e.ebo_aov IS NOT NULL
        THEN ROUND((s.online_aov - e.ebo_aov)::NUMERIC, 0)
    END                                                         AS online_vs_ebo_aov_diff,

    -- ── RFM Scores (calibrated to your real data) ─────────────────────────────
    -- R Score — Recency
    CASE
        WHEN LEAST(COALESCE(e.ebo_days_since_last, 99999),
                   COALESCE(s.online_days_since_last, 99999)) <=  30 THEN 5
        WHEN LEAST(COALESCE(e.ebo_days_since_last, 99999),
                   COALESCE(s.online_days_since_last, 99999)) <=  90 THEN 4
        WHEN LEAST(COALESCE(e.ebo_days_since_last, 99999),
                   COALESCE(s.online_days_since_last, 99999)) <= 180 THEN 3
        WHEN LEAST(COALESCE(e.ebo_days_since_last, 99999),
                   COALESCE(s.online_days_since_last, 99999)) <= 365 THEN 2
        ELSE 1
    END                                                         AS rfm_r,

    -- F Score — Frequency (calibrated: 64% = 1 order, 82% = 1-2 orders)
    CASE
        WHEN COALESCE(e.total_ebo_bills,0)
           + COALESCE(s.total_online_orders,0) >= 10 THEN 5
        WHEN COALESCE(e.total_ebo_bills,0)
           + COALESCE(s.total_online_orders,0) >=  5 THEN 4
        WHEN COALESCE(e.total_ebo_bills,0)
           + COALESCE(s.total_online_orders,0) >=  3 THEN 3
        WHEN COALESCE(e.total_ebo_bills,0)
           + COALESCE(s.total_online_orders,0) =   2 THEN 2
        ELSE 1
    END                                                         AS rfm_f,

    -- M Score — Monetary (calibrated: p25=1399, p50=2468, p75=4759, p95=14030)
    CASE
        WHEN COALESCE(e.total_ebo_spend,0)
           + COALESCE(s.total_online_spend,0) > 15000 THEN 5   -- top 5%
        WHEN COALESCE(e.total_ebo_spend,0)
           + COALESCE(s.total_online_spend,0) >  5000 THEN 4   -- top 25%
        WHEN COALESCE(e.total_ebo_spend,0)
           + COALESCE(s.total_online_spend,0) >  2500 THEN 3   -- top 50%
        WHEN COALESCE(e.total_ebo_spend,0)
           + COALESCE(s.total_online_spend,0) >  1400 THEN 2   -- top 75%
        ELSE 1
    END                                                         AS rfm_m,

    -- ── RFM Segment Label (frontend filter) ───────────────────────────────────
    CASE
        -- Champion: bought recently, buys often, spends most
        WHEN LEAST(COALESCE(e.ebo_days_since_last,99999),
                   COALESCE(s.online_days_since_last,99999)) <= 90
             AND (COALESCE(e.total_ebo_bills,0)
                + COALESCE(s.total_online_orders,0)) >= 5
             AND (COALESCE(e.total_ebo_spend,0)
                + COALESCE(s.total_online_spend,0)) > 15000     THEN 'Champion'

        -- Loyal: high spender, active in last 90 days
        WHEN LEAST(COALESCE(e.ebo_days_since_last,99999),
                   COALESCE(s.online_days_since_last,99999)) <= 90
             AND (COALESCE(e.total_ebo_spend,0)
                + COALESCE(s.total_online_spend,0)) > 5000      THEN 'Loyal'

        -- New Customer: first purchase in last 30 days, only 1 order
        WHEN LEAST(COALESCE(e.ebo_days_since_last,99999),
                   COALESCE(s.online_days_since_last,99999)) <= 30
             AND (COALESCE(e.total_ebo_bills,0)
                + COALESCE(s.total_online_orders,0)) = 1        THEN 'New Customer'

        -- Promising: recent but low frequency
        WHEN LEAST(COALESCE(e.ebo_days_since_last,99999),
                   COALESCE(s.online_days_since_last,99999)) <= 90
             AND (COALESCE(e.total_ebo_bills,0)
                + COALESCE(s.total_online_orders,0)) <= 2       THEN 'Promising'

        -- Need Attention: used to buy regularly, now cooling
        WHEN LEAST(COALESCE(e.ebo_days_since_last,99999),
                   COALESCE(s.online_days_since_last,99999)) BETWEEN 91 AND 180
             AND (COALESCE(e.total_ebo_bills,0)
                + COALESCE(s.total_online_orders,0)) >= 3       THEN 'Need Attention'

        -- At Risk: decent history but haven't bought in 180+ days
        WHEN LEAST(COALESCE(e.ebo_days_since_last,99999),
                   COALESCE(s.online_days_since_last,99999)) BETWEEN 181 AND 365
             AND (COALESCE(e.total_ebo_spend,0)
                + COALESCE(s.total_online_spend,0)) > 2500      THEN 'At Risk'

        -- Cannot Lose: high value but gone quiet > 180 days
        WHEN LEAST(COALESCE(e.ebo_days_since_last,99999),
                   COALESCE(s.online_days_since_last,99999)) > 180
             AND (COALESCE(e.total_ebo_spend,0)
                + COALESCE(s.total_online_spend,0)) > 5000      THEN 'Cannot Lose'

        -- Lost: no purchase in over a year
        WHEN LEAST(COALESCE(e.ebo_days_since_last,99999),
                   COALESCE(s.online_days_since_last,99999)) > 365 THEN 'Lost'

        ELSE                                                        'Occasional'
    END                                                         AS rfm_segment,

    -- ── Churn Risk (frontend filter) ──────────────────────────────────────────
    CASE
        WHEN LEAST(COALESCE(e.ebo_days_since_last,99999),
                   COALESCE(s.online_days_since_last,99999)) > 365 THEN 'High'
        WHEN LEAST(COALESCE(e.ebo_days_since_last,99999),
                   COALESCE(s.online_days_since_last,99999)) > 180 THEN 'Medium'
        WHEN LEAST(COALESCE(e.ebo_days_since_last,99999),
                   COALESCE(s.online_days_since_last,99999)) > 90  THEN 'Low'
        ELSE                                                            'None'
    END                                                         AS churn_risk,

    -- ── Return Risk (frontend filter) ─────────────────────────────────────────
    CASE
        WHEN COALESCE(r.customer_returns, 0) = 0             THEN 'No Returns'
        WHEN COALESCE(r.customer_returns, 0) BETWEEN 1 AND 2 THEN 'Low'
        WHEN COALESCE(r.customer_returns, 0) BETWEEN 3 AND 5 THEN 'Medium'
        ELSE                                                      'High'
    END                                                         AS return_risk,

    -- ── Overall Recency Bucket (frontend filter) ───────────────────────────────
    CASE
        WHEN LEAST(COALESCE(e.ebo_days_since_last,99999),
                   COALESCE(s.online_days_since_last,99999)) <=  30 THEN 'Active'
        WHEN LEAST(COALESCE(e.ebo_days_since_last,99999),
                   COALESCE(s.online_days_since_last,99999)) <=  90 THEN 'Warm'
        WHEN LEAST(COALESCE(e.ebo_days_since_last,99999),
                   COALESCE(s.online_days_since_last,99999)) <= 180 THEN 'Cooling'
        WHEN LEAST(COALESCE(e.ebo_days_since_last,99999),
                   COALESCE(s.online_days_since_last,99999)) <= 365 THEN 'At Risk'
        ELSE                                                            'Lapsed'
    END                                                         AS recency_bucket,

    -- Metadata
    NOW()                                                       AS refreshed_at

FROM base b
LEFT JOIN geo          g   ON g.combo    = b.combo_clean
LEFT JOIN ebo_agg      e   ON e.combo    = b.combo_clean
LEFT JOIN ebo_second   es  ON es.combo   = b.combo_clean
LEFT JOIN ebo_same_month esm ON esm.combo = b.combo_clean
LEFT JOIN shp_agg      s   ON s.combo    = b.combo_clean
LEFT JOIN shp_second   ss  ON ss.combo   = b.combo_clean
LEFT JOIN shp_same_month ssm ON ssm.combo = b.combo_clean
LEFT JOIN rt_agg       r   ON r.combo    = b.combo_clean
LEFT JOIN cat_agg      ca  ON ca.combo   = b.combo_clean
LEFT JOIN brand_agg    br  ON br.combo   = b.combo_clean
LEFT JOIN size_agg     sz  ON sz.combo   = b.combo_clean;


-- ── Indexes — all frontend filter columns ─────────────────────────────────────
-- Point lookups (Customer 360 search)
CREATE  INDEX idx_cmp_unq_id        ON public.cust_master_profile (unq_id);
CREATE        INDEX idx_cmp_email         ON public.cust_master_profile (email);
CREATE        INDEX idx_cmp_phone         ON public.cust_master_profile (phone);

-- Segment / dashboard filters
CREATE        INDEX idx_cmp_rfm_segment   ON public.cust_master_profile (rfm_segment);
CREATE        INDEX idx_cmp_churn_risk    ON public.cust_master_profile (churn_risk);
CREATE        INDEX idx_cmp_return_risk   ON public.cust_master_profile (return_risk);
CREATE        INDEX idx_cmp_customer_type ON public.cust_master_profile (customer_type);
CREATE        INDEX idx_cmp_recency       ON public.cust_master_profile (recency_bucket);
CREATE        INDEX idx_cmp_freq_bucket   ON public.cust_master_profile (frequency_bucket);
CREATE        INDEX idx_cmp_platform      ON public.cust_master_profile (platform);
CREATE        INDEX idx_cmp_channel       ON public.cust_master_profile (channel_journey);
CREATE        INDEX idx_cmp_migration     ON public.cust_master_profile (migration_type);

-- Geo filters
CREATE        INDEX idx_cmp_zone          ON public.cust_master_profile (consumer_zone);
CREATE        INDEX idx_cmp_state         ON public.cust_master_profile (consumer_state);
CREATE        INDEX idx_cmp_city          ON public.cust_master_profile (consumer_city);
CREATE        INDEX idx_cmp_pincode       ON public.cust_master_profile (consumer_pincode);

-- Category / product filters
CREATE        INDEX idx_cmp_top_category  ON public.cust_master_profile (top_category);
CREATE        INDEX idx_cmp_cat_label     ON public.cust_master_profile (category_label);
CREATE        INDEX idx_cmp_top_brand     ON public.cust_master_profile (top_brand);
CREATE        INDEX idx_cmp_size_beh      ON public.cust_master_profile (size_behaviour);

-- Store filter
CREATE        INDEX idx_cmp_store         ON public.cust_master_profile (primary_store);

-- Date range filters
CREATE        INDEX idx_cmp_first_seen    ON public.cust_master_profile (first_seen_date);
CREATE        INDEX idx_cmp_last_updated  ON public.cust_master_profile (last_updated_date);

-- Retention flags
CREATE        INDEX idx_cmp_retained_30   ON public.cust_master_profile (retained_30d);
CREATE        INDEX idx_cmp_retained_90   ON public.cust_master_profile (retained_90d);

-- Composite index for most common dashboard query pattern
CREATE        INDEX idx_cmp_zone_rfm      ON public.cust_master_profile (consumer_zone, rfm_segment);
CREATE        INDEX idx_cmp_store_type    ON public.cust_master_profile (primary_store, customer_type);
CREATE        INDEX idx_cmp_cat_type      ON public.cust_master_profile (top_category, customer_type);


-- ============================================================================
-- SECTION 3 : cust_monthly_cohort_mv
-- Pre-aggregated cohort retention grid.
-- Frontend cohort screen queries this directly — no heavy computation at runtime.
-- Grain: one row per cohort_month × activity_month
-- ============================================================================

DROP MATERIALIZED VIEW IF EXISTS public.cust_monthly_cohort_mv CASCADE;

CREATE MATERIALIZED VIEW public.cust_monthly_cohort_mv AS

WITH all_txns AS (
    -- All EBO transactions
    SELECT
        public.fn_clean_combo(combo)                            AS combo,
        invoice_date                                            AS txn_date
    FROM public.cust_ebo_salescombo_view
    WHERE combo IS NOT NULL AND combo <> ''

    UNION ALL

    -- All Shopify transactions
    SELECT
        public.fn_clean_combo(combo)                            AS combo,
        channel_order_date                                      AS txn_date
    FROM public.cust_osdcombo_view
    WHERE combo IS NOT NULL
      AND combo <> ''
      AND combo NOT LIKE '%myshopify%'
      AND combo NOT LIKE '%nitro.co%'
),

-- Each customer's cohort = month of their very first transaction
customer_cohort AS (
    SELECT
        combo,
        DATE_TRUNC('month', MIN(txn_date))::DATE                AS cohort_month
    FROM all_txns
    GROUP BY combo
),

-- Size of each cohort
cohort_size AS (
    SELECT cohort_month, COUNT(DISTINCT combo)                  AS cohort_size
    FROM customer_cohort
    GROUP BY cohort_month
),

-- Tag every transaction with its customer's cohort month
tagged AS (
    SELECT
        cc.cohort_month,
        DATE_TRUNC('month', t.txn_date)::DATE                   AS activity_month,
        t.combo
    FROM all_txns t
    INNER JOIN customer_cohort cc ON cc.combo = t.combo
),

-- Aggregate: how many customers from each cohort were active each month
activity AS (
    SELECT
        cohort_month,
        activity_month,
        COUNT(DISTINCT combo)                                   AS active_customers,
        COUNT(*)                                                AS total_transactions
    FROM tagged
    GROUP BY cohort_month, activity_month
)

SELECT
    a.cohort_month,
    a.activity_month,
    cs.cohort_size,
    a.active_customers,
    a.total_transactions,

    -- Months since acquisition (0 = first month, 1 = next month, etc.)
    (
        EXTRACT(YEAR  FROM AGE(a.activity_month, a.cohort_month)) * 12
      + EXTRACT(MONTH FROM AGE(a.activity_month, a.cohort_month))
    )::INT                                                      AS months_since_first,

    -- Retention rate for this cohort in this activity month
    ROUND(a.active_customers::NUMERIC
        / NULLIF(cs.cohort_size, 0) * 100, 2)                  AS retention_rate_pct,

    -- New vs Repeat tag
    -- month 0 = acquisition month (all "New"), month 1+ = Repeat activity
    CASE
        WHEN (
            EXTRACT(YEAR  FROM AGE(a.activity_month, a.cohort_month)) * 12
          + EXTRACT(MONTH FROM AGE(a.activity_month, a.cohort_month))
        ) = 0 THEN 'New'
        ELSE       'Repeat'
    END                                                         AS customer_activity_type

FROM activity a
INNER JOIN cohort_size cs ON cs.cohort_month = a.cohort_month
ORDER BY a.cohort_month, a.activity_month;

CREATE INDEX idx_cohort_month    ON public.cust_monthly_cohort_mv (cohort_month);
CREATE INDEX idx_activity_month  ON public.cust_monthly_cohort_mv (activity_month);
CREATE INDEX idx_months_since    ON public.cust_monthly_cohort_mv (months_since_first);


-- ============================================================================
-- SECTION 3b : cust_monthly_active_mv
-- Pre-aggregated monthly activity per customer-combo, so the API never has to
-- scan the raw transaction views for "active in month X" queries (dashboard +
-- channel pages with a month filter). Grain: one row per (combo, activity_month).
-- Join to cust_master_profile via fn_clean_combo(combo) — see functional index
-- idx_cmp_clean_combo below. Refreshed nightly by refresh_pipeline.py.
-- ============================================================================

DROP MATERIALIZED VIEW IF EXISTS public.cust_monthly_active_mv CASCADE;

CREATE MATERIALIZED VIEW public.cust_monthly_active_mv AS
WITH ebo AS (
    SELECT public.fn_clean_combo(combo)               AS combo,
           DATE_TRUNC('month', invoice_date)::date    AS activity_month,
           COUNT(*)                                   AS ebo_orders,
           SUM(order_amount)                          AS ebo_spend
    FROM public.cust_ebo_salescombo_view
    WHERE combo IS NOT NULL AND invoice_date IS NOT NULL
    GROUP BY 1, 2
),
shp AS (
    SELECT public.fn_clean_combo(combo)                  AS combo,
           DATE_TRUNC('month', channel_order_date)::date AS activity_month,
           SUM(order_count)                              AS online_orders,
           SUM(order_amount)                             AS online_spend
    FROM public.cust_osdcombo_view
    WHERE combo IS NOT NULL
      AND combo NOT LIKE '%myshopify%'
      AND channel_order_date IS NOT NULL
    GROUP BY 1, 2
)
SELECT
    COALESCE(e.combo, s.combo)                   AS combo,
    COALESCE(e.activity_month, s.activity_month) AS activity_month,
    COALESCE(e.ebo_orders, 0)                    AS ebo_orders,
    COALESCE(e.ebo_spend, 0)                     AS ebo_spend,
    COALESCE(s.online_orders, 0)                 AS online_orders,
    COALESCE(s.online_spend, 0)                  AS online_spend,
    (COALESCE(e.ebo_orders, 0)  > 0)             AS in_ebo,
    (COALESCE(s.online_orders, 0) > 0)           AS in_shp
FROM ebo e
FULL OUTER JOIN shp s
  ON e.combo = s.combo AND e.activity_month = s.activity_month;

-- Unique index required for REFRESH MATERIALIZED VIEW CONCURRENTLY
CREATE UNIQUE INDEX uq_cma_combo_month ON public.cust_monthly_active_mv (combo, activity_month);
CREATE INDEX        idx_cma_month      ON public.cust_monthly_active_mv (activity_month);

-- Functional index on the profile so the MV ↔ profile join (on the cleaned combo)
-- is a fast index lookup instead of a full scan. fn_clean_combo is IMMUTABLE.
CREATE INDEX IF NOT EXISTS idx_cmp_clean_combo
    ON public.cust_master_profile (public.fn_clean_combo(combo));


-- ============================================================================
-- SECTION 4 : store_summary_mv
-- Pre-aggregated store-level metrics.
-- Frontend store screen queries this directly.
-- Grain: one row per store (invoice_associate_name)
-- ============================================================================

DROP MATERIALIZED VIEW IF EXISTS public.store_summary_mv CASCADE;

CREATE MATERIALIZED VIEW public.store_summary_mv AS

WITH store_txns AS (
    SELECT
        TRIM(e.invoice_associate_name)                          AS store_name,
        public.fn_clean_combo(e.combo)                          AS combo,
        e.invoice_date,
        e.order_amount,
        e.nob
    FROM public.cust_ebo_salescombo_view e
    WHERE e.invoice_associate_name IS NOT NULL
      AND e.invoice_associate_name <> ''
      AND e.combo IS NOT NULL
),

store_customer AS (
    -- One row per store + customer with visit count and spend at that store
    SELECT
        store_name,
        combo,
        COUNT(DISTINCT invoice_date)                            AS visit_days,
        SUM(nob)                                                AS bills_at_store,
        SUM(order_amount)                                       AS spend_at_store,
        MIN(invoice_date)                                       AS first_visit,
        MAX(invoice_date)                                       AS last_visit
    FROM store_txns
    GROUP BY store_name, combo
),

store_with_profile AS (
    SELECT
        sc.store_name,
        sc.combo,
        sc.visit_days,
        sc.bills_at_store,
        sc.spend_at_store,
        mp.rfm_segment,
        mp.churn_risk,
        mp.customer_type,
        mp.top_category,
        mp.migration_type,
        mp.total_lifetime_spend,
        mp.retained_30d,
        mp.retained_60d,
        mp.retained_90d,
        mp.consumer_zone,
        mp.online_aov,
        mp.ebo_aov
    FROM store_customer sc
    LEFT JOIN public.cust_master_profile mp
           ON mp.email IS NOT NULL   -- join via master profile
          AND public.fn_clean_combo(mp.combo) = sc.combo
)

SELECT
    store_name,

    -- Volume
    COUNT(DISTINCT combo)                                       AS total_customers,
    COUNT(DISTINCT combo) FILTER (
        WHERE visit_days >= 2
    )                                                           AS repeat_customers,
    ROUND(
        COUNT(DISTINCT combo) FILTER (WHERE visit_days >= 2)::NUMERIC
        / NULLIF(COUNT(DISTINCT combo), 0) * 100, 1
    )                                                           AS repeat_customer_pct,
    ROUND(AVG(visit_days)::NUMERIC, 1)                         AS avg_visits_per_customer,
    ROUND(AVG(bills_at_store)::NUMERIC, 1)                     AS avg_bills_per_customer,

    -- Revenue
    ROUND(SUM(spend_at_store)::NUMERIC, 0)                     AS total_store_revenue,
    ROUND(AVG(ebo_aov)::NUMERIC, 0)                            AS avg_ebo_aov_at_store,
    ROUND(AVG(total_lifetime_spend)::NUMERIC, 0)               AS avg_customer_ltv,

    -- Retention
    ROUND(COUNT(DISTINCT combo) FILTER (WHERE retained_30d)::NUMERIC
        / NULLIF(COUNT(DISTINCT combo), 0) * 100, 1)           AS retention_30d_pct,
    ROUND(COUNT(DISTINCT combo) FILTER (WHERE retained_60d)::NUMERIC
        / NULLIF(COUNT(DISTINCT combo), 0) * 100, 1)           AS retention_60d_pct,
    ROUND(COUNT(DISTINCT combo) FILTER (WHERE retained_90d)::NUMERIC
        / NULLIF(COUNT(DISTINCT combo), 0) * 100, 1)           AS retention_90d_pct,

    -- RFM breakdown at store
    COUNT(DISTINCT combo) FILTER (
        WHERE rfm_segment = 'Champion'
    )                                                           AS champion_count,
    COUNT(DISTINCT combo) FILTER (
        WHERE rfm_segment = 'Loyal'
    )                                                           AS loyal_count,
    COUNT(DISTINCT combo) FILTER (
        WHERE rfm_segment IN ('At Risk','Cannot Lose')
    )                                                           AS at_risk_count,
    COUNT(DISTINCT combo) FILTER (
        WHERE churn_risk = 'High'
    )                                                           AS high_churn_count,

    -- Migration: customers who first came to this store then moved online
    COUNT(DISTINCT combo) FILTER (
        WHERE migration_type = 'EBO First'
    )                                                           AS migrated_to_online,

    -- Top category at this store
    MODE() WITHIN GROUP (ORDER BY top_category)                AS top_category_at_store,

    -- Zone of majority of store's customers
    MODE() WITHIN GROUP (ORDER BY consumer_zone)               AS primary_customer_zone

FROM store_with_profile
GROUP BY store_name
ORDER BY total_customers DESC;

CREATE UNIQUE INDEX idx_store_name ON public.store_summary_mv (store_name);


-- ============================================================================
-- SECTION 5 : pg_cron Daily Refresh Schedule
-- Run once as superuser to register jobs.
-- Layer 3 master refreshes at 02:00 AM IST (20:30 UTC previous day)
-- Analytics views refresh at 02:30 AM IST (21:00 UTC previous day)
-- ============================================================================

-- Enable pg_cron (run once as superuser if not already enabled)
-- CREATE EXTENSION IF NOT EXISTS pg_cron;

-- Remove existing schedules safely
DO $$
DECLARE
    v_job TEXT;
BEGIN
    FOREACH v_job IN ARRAY ARRAY[
        'refresh_cust_master_profile',
        'refresh_cust_monthly_cohort_mv',
        'refresh_store_summary_mv'
    ]
    LOOP
        BEGIN
            PERFORM cron.unschedule(v_job);
        EXCEPTION WHEN OTHERS THEN
            NULL; -- job didn't exist, ignore
        END;
    END LOOP;
END;
$$;

-- Master profile — 02:00 AM IST daily
SELECT cron.schedule(
    'refresh_cust_master_profile',
    '30 20 * * *',
    'REFRESH MATERIALIZED VIEW CONCURRENTLY public.cust_master_profile'
);

-- Analytics views — 02:30 AM IST daily (after master is done)
SELECT cron.schedule(
    'refresh_cust_monthly_cohort_mv',
    '0 21 * * *',
    'REFRESH MATERIALIZED VIEW CONCURRENTLY public.cust_monthly_cohort_mv'
);

SELECT cron.schedule(
    'refresh_store_summary_mv',
    '0 21 * * *',
    'REFRESH MATERIALIZED VIEW CONCURRENTLY public.store_summary_mv'
);


-- ============================================================================
-- SECTION 6 : Validation Queries
-- Run these after the first full build to confirm everything is correct.
-- ============================================================================

-- 1. Row counts
SELECT 'cust_master_profile'    AS view_name, COUNT(*) AS rows FROM public.cust_master_profile
UNION ALL
SELECT 'cust_monthly_cohort_mv',               COUNT(*)        FROM public.cust_monthly_cohort_mv
UNION ALL
SELECT 'store_summary_mv',                     COUNT(*)        FROM public.store_summary_mv;

-- 2. RFM segment distribution (should feel balanced, not all in one bucket)
SELECT
    rfm_segment,
    COUNT(*)                                                    AS customers,
    ROUND((COUNT(*) * 100.0 / SUM(COUNT(*)) OVER ())::NUMERIC, 1)         AS pct
FROM public.cust_master_profile
GROUP BY rfm_segment
ORDER BY customers DESC;

-- 3. Channel journey split
SELECT
    channel_journey,
    COUNT(*)                                                    AS customers,
    ROUND((COUNT(*) * 100.0 / SUM(COUNT(*)) OVER ())::NUMERIC, 1)         AS pct
FROM public.cust_master_profile
GROUP BY channel_journey
ORDER BY customers DESC;

-- 4. Migration type split
SELECT
    migration_type,
    COUNT(*)                                                    AS customers,
    ROUND((COUNT(*) * 100.0 / SUM(COUNT(*)) OVER ())::NUMERIC, 1)         AS pct
FROM public.cust_master_profile
GROUP BY migration_type
ORDER BY customers DESC;

-- 5. Category label distribution
SELECT
    category_label,
    COUNT(*)                                                    AS customers,
    ROUND((COUNT(*) * 100.0 / SUM(COUNT(*)) OVER ())::NUMERIC, 1)         AS pct
FROM public.cust_master_profile
WHERE category_label IS NOT NULL
GROUP BY category_label
ORDER BY customers DESC
LIMIT 20;

-- 6. Size behaviour split
SELECT
    size_behaviour,
    COUNT(*)                                                    AS customers,
    ROUND((COUNT(*) * 100.0 / SUM(COUNT(*)) OVER ())::NUMERIC, 1)         AS pct
FROM public.cust_master_profile
GROUP BY size_behaviour
ORDER BY customers DESC;

-- 7. New vs Repeat AOV comparison
SELECT
    customer_type,
    COUNT(*)                                                    AS customers,
    ROUND(AVG(ebo_aov)::NUMERIC, 0)                             AS avg_ebo_aov,
    ROUND(AVG(online_aov)::NUMERIC, 0)                          AS avg_online_aov,
    ROUND(AVG((total_lifetime_spend
        / NULLIF(total_lifetime_orders, 0))::NUMERIC)::NUMERIC, 0) AS blended_aov
FROM public.cust_master_profile
WHERE customer_type IN ('New', 'Repeat')
GROUP BY customer_type;

-- 8. Sample Customer 360 lookup (replace with real email)
SELECT
    unq_id, consumer_name, email, phone,
    consumer_city, consumer_zone, consumer_pincode,
    channel_journey, migration_type, rfm_segment,
    total_lifetime_spend, total_lifetime_orders,
    customer_type, churn_risk, return_risk,
    top_category, category_label, size_behaviour,
    first_seen_date, last_updated_date,
    days_since_last_purchase, days_1st_to_2nd_purchase,
    retained_30d, retained_60d, retained_90d
FROM public.cust_master_profile
WHERE email = 'replace_with_real@email.com';

-- 9. LEHENGA-only customers export (self-serve export pattern)
SELECT
    unq_id, consumer_name, email, phone,
    consumer_city, consumer_zone,
    total_lifetime_spend, total_lifetime_orders,
    rfm_segment, churn_risk, last_updated_date
FROM public.cust_master_profile
WHERE category_label = 'LEHENGA Only'
ORDER BY total_lifetime_spend DESC;

-- 10. Store performance summary
SELECT
    store_name, total_customers, repeat_customers,
    repeat_customer_pct, retention_30d_pct, retention_90d_pct,
    avg_customer_ltv, migrated_to_online, top_category_at_store
FROM public.store_summary_mv
ORDER BY total_customers DESC;

-- 11. Cohort retention (last 12 months, month 0-6)
SELECT
    cohort_month, months_since_first,
    cohort_size, active_customers, retention_rate_pct
FROM public.cust_monthly_cohort_mv
WHERE cohort_month >= CURRENT_DATE - INTERVAL '12 months'
  AND months_since_first <= 6
ORDER BY cohort_month, months_since_first;