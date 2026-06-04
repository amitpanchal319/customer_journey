# api/routers/cohorts.py

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from database.connection import get_db

router = APIRouter()


@router.get("/retention")
def get_cohort_retention(
    months: int = Query(12, description="0 = all time"),
    start_month: str = Query(None, description="YYYY-MM — show cohorts from this month onwards"),
    cohort_months: str = Query(None, description="Comma-separated YYYY-MM — show only these cohort months"),
    db: Session = Depends(get_db),
):
    if cohort_months:
        ml = [m.strip() for m in cohort_months.split(',') if m.strip()]
        if ml:
            ins = ", ".join(f"DATE_TRUNC('month', CAST(:cm{i} AS DATE))" for i in range(len(ml)))
            where_clause = f"WHERE DATE_TRUNC('month', cohort_month) IN ({ins})"
            params = {f"cm{i}": m + "-01" for i, m in enumerate(ml)}
        else:
            where_clause = ""; params = {}
    elif start_month:
        where_clause = "WHERE cohort_month >= DATE_TRUNC('month', CAST(:start_month AS DATE))"
        params = {"start_month": start_month + "-01"}
    elif months == 0:
        where_clause = ""
        params = {}
    else:
        where_clause = "WHERE cohort_month >= DATE_TRUNC('month', CURRENT_DATE) - (:months || ' months')::INTERVAL"
        params = {"months": months}

    rows = db.execute(text(f"""
        SELECT
            TO_CHAR(cohort_month, 'Mon YYYY')   AS cohort_label,
            cohort_month,
            months_since_first,
            cohort_size,
            active_customers,
            retention_rate_pct,
            customer_activity_type
        FROM public.cust_monthly_cohort_mv
        {where_clause}
        ORDER BY cohort_month, months_since_first
    """), params).mappings().all()
    return [dict(r) for r in rows]


@router.get("/mom")
def get_mom_new_vs_repeat(
    months: int = Query(12, description="0 = all time"),
    start_month: str = Query(None, description="YYYY-MM — show data from this month onwards"),
    end_month: str = Query(None, description="YYYY-MM — show 12 months ending at this month"),
    channel_journey: str = Query(None, description="Online Only | Offline Only | Both — filter by channel"),
    db: Session = Depends(get_db),
):
    # NOTE: channel_journey is accepted for API compatibility but intentionally
    # NOT applied here — the cohort MV has no channel dimension, and deriving it
    # from the raw transaction views is too slow to do on every dashboard load.
    # This trend always reflects all channels. (To make it channel-aware, add a
    # channel_journey column to cust_monthly_cohort_mv.)
    _ = channel_journey

    # ── Use the pre-aggregated MV (fast) ──
    if end_month:
        where_clause = """WHERE activity_month <= DATE_TRUNC('month', CAST(:end_month AS DATE))
                            AND activity_month >  DATE_TRUNC('month', CAST(:end_month AS DATE)) - INTERVAL '12 months'"""
        params = {"end_month": end_month + "-01"}
    elif start_month:
        where_clause = "WHERE activity_month >= DATE_TRUNC('month', CAST(:start_month AS DATE))"
        params = {"start_month": start_month + "-01"}
    elif months == 0:
        where_clause = ""
        params = {}
    else:
        where_clause = "WHERE activity_month >= DATE_TRUNC('month', CURRENT_DATE) - (:months || ' months')::INTERVAL"
        params = {"months": months}

    rows = db.execute(text(f"""
        SELECT
            TO_CHAR(activity_month, 'Mon YYYY')     AS month_label,
            activity_month,
            SUM(CASE WHEN customer_activity_type = 'New'
                THEN active_customers ELSE 0 END)   AS new_customers,
            SUM(CASE WHEN customer_activity_type = 'Repeat'
                THEN active_customers ELSE 0 END)   AS repeat_customers,
            SUM(active_customers)                   AS total_active,
            ROUND((
                SUM(CASE WHEN customer_activity_type = 'Repeat'
                    THEN active_customers ELSE 0 END)::NUMERIC
                / NULLIF(SUM(active_customers), 0) * 100
            )::NUMERIC, 1)                          AS repeat_pct
        FROM public.cust_monthly_cohort_mv
        {where_clause}
        GROUP BY activity_month
        ORDER BY activity_month DESC
    """), params).mappings().all()
    return [dict(r) for r in rows]


@router.get("/retention-flags")
def get_retention_flag_summary(db: Session = Depends(get_db)):
    rows = db.execute(text("""
        SELECT
            channel_journey,
            COUNT(*)                                                    AS customers,
            COUNT(*) FILTER (WHERE retained_30d = TRUE)                 AS retained_30d,
            COUNT(*) FILTER (WHERE retained_60d = TRUE)                 AS retained_60d,
            COUNT(*) FILTER (WHERE retained_90d = TRUE)                 AS retained_90d,
            ROUND((COUNT(*) FILTER (WHERE retained_30d)::NUMERIC
                / NULLIF(COUNT(*), 0) * 100)::NUMERIC, 1)               AS pct_30d,
            ROUND((COUNT(*) FILTER (WHERE retained_60d)::NUMERIC
                / NULLIF(COUNT(*), 0) * 100)::NUMERIC, 1)               AS pct_60d,
            ROUND((COUNT(*) FILTER (WHERE retained_90d)::NUMERIC
                / NULLIF(COUNT(*), 0) * 100)::NUMERIC, 1)               AS pct_90d,
            ROUND(AVG(CASE 
                WHEN days_1st_to_2nd_purchase > 0 
                 AND days_1st_to_2nd_purchase < 730
                THEN days_1st_to_2nd_purchase 
            END)::NUMERIC, 0)                                               AS avg_days_to_2nd_purchase
        FROM public.cust_master_profile
        WHERE customer_type IN ('New', 'Repeat')
        GROUP BY channel_journey
        ORDER BY customers DESC
    """)).mappings().all()
    return [dict(r) for r in rows]


@router.get("/export-csv")
def export_cohort_csv(
    months: int = Query(12, description="0 = all time"),
    start_month: str = Query(None, description="YYYY-MM — export customers from this month onwards"),
    cohort_months: str = Query(None, description="Comma-separated YYYY-MM — export only these cohort months"),
    db: Session = Depends(get_db),
):
    """
    Export cohort retention data as CSV — one row per customer.
    Includes email, phone, platform, cohort month, and retention behaviour.
    Joins cust_monthly_cohort_mv logic back to cust_master_profile for PII.
    """
    import io, csv
    from fastapi.responses import StreamingResponse

    # Cohort = the customer's FIRST activity month, derived from the monthly-active MV
    # (same definition the on-screen grid uses). NOTE: cust_master_profile.first_seen_date
    # is unreliable here, so we compute the cohort from cust_monthly_active_mv instead.
    if cohort_months:
        ml = [m.strip() for m in cohort_months.split(',') if m.strip()]
        ins = ", ".join(f"DATE_TRUNC('month', CAST(:cm{i} AS DATE))" for i in range(len(ml)))
        cohort_filter = f"DATE_TRUNC('month', ch.cohort_month) IN ({ins})"
        params = {f"cm{i}": m + "-01" for i, m in enumerate(ml)}
    elif start_month:
        cohort_filter = "ch.cohort_month >= DATE_TRUNC('month', CAST(:start_month AS DATE))"
        params = {"start_month": start_month + "-01"}
    elif months == 0:
        cohort_filter = "TRUE"
        params = {}
    else:
        cohort_filter = "ch.cohort_month >= DATE_TRUNC('month', CURRENT_DATE) - (:months || ' months')::INTERVAL"
        params = {"months": months}

    rows = db.execute(text(f"""
        WITH ch AS (
            SELECT combo, MIN(activity_month) AS cohort_month
            FROM public.cust_monthly_active_mv
            GROUP BY combo
        )
        SELECT
            -- Identity
            mp.unq_id,
            mp.consumer_name,
            mp.email,
            mp.phone,
            mp.platform,
            mp.channel_journey,

            -- Cohort info (first activity month)
            TO_CHAR(ch.cohort_month, 'Mon YYYY')            AS cohort_month,
            ch.cohort_month                                 AS cohort_month_date,

            -- Purchase behaviour
            mp.customer_type,
            mp.total_lifetime_orders,
            mp.total_lifetime_spend,
            mp.total_ebo_bills,
            mp.total_online_orders,
            mp.days_since_last_purchase,
            mp.days_1st_to_2nd_purchase,

            -- Retention flags
            mp.retained_30d,
            mp.retained_60d,
            mp.retained_90d,

            -- Segment info
            mp.rfm_segment,
            mp.churn_risk,
            mp.recency_bucket,

            -- Geo
            mp.consumer_city,
            mp.consumer_state,
            mp.consumer_zone,

            -- Category
            mp.top_category,
            mp.last_updated_date

        FROM public.cust_master_profile mp
        JOIN ch ON ch.combo = public.fn_clean_combo(mp.combo)
        WHERE {cohort_filter}
        ORDER BY ch.cohort_month ASC, mp.total_lifetime_spend DESC NULLS LAST
        LIMIT 500000
    """), params).mappings().all()

    def generate():
        buf = io.StringIO()
        if not rows:
            yield "No data found"
            return
        writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        buf.seek(0)
        yield buf.read()
        buf.truncate(0)
        buf.seek(0)

        for row in rows:
            writer.writerow(dict(row))
            buf.seek(0)
            yield buf.read()
            buf.truncate(0)
            buf.seek(0)

    return StreamingResponse(
        generate(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=cohort_customers.csv"},
    )


@router.get("/repeat-by-month")
def get_repeat_customers_by_month(
    activity_month : str = Query(..., description="Month in YYYY-MM format e.g. 2026-05"),
    channel        : str = Query("all", description="all | ebo | shopify | both"),
    db: Session = Depends(get_db),
):
    """
    Returns all repeat customers who made a purchase in a specific month.
    Repeat = customer has more than 1 lifetime order.
    activity_month = the month you want to look at e.g. 2026-05 for May 2026.
    """
    # Build channel filter
    channel_filter = ""
    if channel == "ebo":
        channel_filter = "AND mp.total_ebo_bills > 0 AND mp.in_ebo = TRUE"
    elif channel == "shopify":
        channel_filter = "AND mp.total_online_orders > 0 AND mp.in_shopify = TRUE"
    elif channel == "both":
        channel_filter = "AND mp.in_ebo = TRUE AND mp.in_shopify = TRUE"

    # Build SQL as plain string — no f-string to avoid : parameter conflicts
    sql = """
        WITH activity_in_month AS (
            SELECT
                public.fn_clean_combo(combo)    AS combo,
                'EBO'                           AS txn_channel,
                SUM(order_amount)               AS month_spend,
                COUNT(*)                        AS month_orders
            FROM public.cust_ebo_salescombo_view
            WHERE DATE_TRUNC('month', invoice_date) = DATE_TRUNC('month', cast(:act_month AS DATE))
              AND combo IS NOT NULL
            GROUP BY public.fn_clean_combo(combo)

            UNION ALL

            SELECT
                public.fn_clean_combo(combo)    AS combo,
                'Shopify'                       AS txn_channel,
                SUM(order_amount)               AS month_spend,
                COUNT(*)                        AS month_orders
            FROM public.cust_osdcombo_view
            WHERE DATE_TRUNC('month', channel_order_date) = DATE_TRUNC('month', cast(:act_month AS DATE))
              AND combo IS NOT NULL
              AND combo NOT LIKE '%myshopify%'
            GROUP BY public.fn_clean_combo(combo)
        ),
        month_summary AS (
            SELECT
                combo,
                STRING_AGG(txn_channel, ' + ' ORDER BY txn_channel) AS active_channels,
                SUM(month_spend)    AS month_spend,
                SUM(month_orders)   AS month_orders
            FROM activity_in_month
            GROUP BY combo
        )

        SELECT
            mp.combo,
            mp.consumer_name,
            mp.email,
            mp.phone,
            mp.platform,
            mp.channel_journey,
            ms.active_channels                  AS active_in_month,
            ROUND(ms.month_spend::NUMERIC, 0)   AS spend_this_month,
            ms.month_orders                     AS orders_this_month,
            mp.total_lifetime_orders,
            mp.total_lifetime_spend,
            mp.total_ebo_bills,
            mp.total_online_orders,
            mp.rfm_segment,
            mp.churn_risk,
            mp.customer_type,
            mp.recency_bucket,
            mp.frequency_bucket,
            mp.top_category,
            mp.top_brand,
            mp.size_behaviour,
            mp.consumer_city,
            mp.consumer_state,
            mp.consumer_zone,
            mp.consumer_pincode,
            mp.first_seen_date,
            mp.last_updated_date,
            mp.days_since_last_purchase
        FROM month_summary ms
        INNER JOIN public.cust_master_profile mp
                ON mp.combo = ms.combo
        WHERE mp.total_lifetime_orders > 1
    """

    # Append channel filter as literal SQL (safe — only set from our own code)
    if channel_filter:
        sql += f" {channel_filter}"

    sql += " ORDER BY ms.month_spend DESC NULLS LAST"

    rows = db.execute(
        text(sql),
        {"act_month": activity_month + "-01"}
    ).mappings().all()

    return {
        "activity_month"    : activity_month,
        "channel_filter"    : channel,
        "repeat_customers"  : len(rows),
        "customers"         : [dict(r) for r in rows],
    }


@router.get("/repeat-by-month/export-csv")
def export_repeat_by_month_csv(
    activity_month : str = Query(..., description="Month in YYYY-MM format e.g. 2026-05"),
    channel        : str = Query("all", description="all | ebo | shopify | both"),
    db: Session = Depends(get_db),
):
    """Export repeat customers for a specific month as CSV."""
    import io, csv
    from fastapi.responses import StreamingResponse

    # Reuse the same logic
    result = get_repeat_customers_by_month(activity_month, channel, db)
    rows   = result["customers"]

    def generate():
        if not rows:
            yield "No repeat customers found for this month\n"
            return
        buf    = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        buf.seek(0); yield buf.read(); buf.truncate(0); buf.seek(0)
        for row in rows:
            writer.writerow(row)
            buf.seek(0); yield buf.read(); buf.truncate(0); buf.seek(0)

    filename = f"repeat_customers_{activity_month}.csv"
    return StreamingResponse(
        generate(),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# ============================================================================
# CHANNEL MIGRATION ANALYSIS ENDPOINTS
# ============================================================================

@router.get("/channel-migration/summary")
def get_channel_migration_summary(
    month: str = Query(None, description="YYYY-MM — restrict to customers active in this month"),
    db: Session = Depends(get_db),
):
    """
    Summary counts for the migration patterns. When `month` is given, only customers
    active in that month (from cust_monthly_active_mv) are counted; otherwise lifetime.
    """
    if month:
        join = """INNER JOIN (
                     SELECT combo FROM public.cust_monthly_active_mv
                     WHERE activity_month = DATE_TRUNC('month', CAST(:month_date AS DATE))
                  ) am ON am.combo = public.fn_clean_combo(mp.combo)"""
        params = {"month_date": month + "-01"}
    else:
        join = ""
        params = {}

    rows = db.execute(text(f"""
        SELECT
            COUNT(*) FILTER (
                WHERE mp.in_ebo = TRUE AND mp.in_shopify = FALSE AND mp.ebo_days_since_last > 180
            )                                                   AS ebo_first_never_back,
            COUNT(*) FILTER (
                WHERE mp.in_shopify = TRUE AND mp.in_ebo = FALSE
            )                                                   AS online_only_never_offline,
            COUNT(*) FILTER (
                WHERE mp.migration_type = 'EBO First'
            )                                                   AS ebo_first_moved_online,
            COUNT(*) FILTER (
                WHERE mp.migration_type = 'Shopify First'
            )                                                   AS online_first_moved_offline,
            COUNT(*) FILTER (
                WHERE mp.migration_type = 'Both Same Time'
            )                                                   AS same_month_both,
            COUNT(*) FILTER (
                WHERE mp.channel_journey IN ('Both', 'Omnichannel')
            )                                                   AS total_omnichannel
        FROM public.cust_master_profile mp
        {join}
    """), params).mappings().first()

    return dict(rows)


@router.get("/channel-migration/ebo-first-never-back")
def get_ebo_first_never_back(
    limit: int = Query(500, description="Max rows"),
    db: Session = Depends(get_db),
):
    """
    Customers who came to EBO (offline) first but never came back offline.
    These are customers who visited store once and never returned.
    """
    rows = db.execute(text("""
        SELECT
            mp.consumer_name,
            mp.email,
            mp.phone,
            mp.consumer_city,
            mp.consumer_zone,
            mp.consumer_pincode,
            mp.total_ebo_bills,
            mp.total_ebo_spend,
            mp.ebo_aov,
            mp.first_ebo_date,
            mp.last_ebo_date,
            mp.ebo_days_since_last,
            mp.primary_store,
            mp.top_category,
            mp.top_brand,
            mp.total_lifetime_spend,
            mp.rfm_segment,
            mp.churn_risk,
            NULL::TEXT                                          AS last_ebo_skus
        FROM public.cust_master_profile mp
        WHERE mp.in_ebo = TRUE
          AND mp.in_shopify = FALSE
          AND mp.ebo_days_since_last > 180
        ORDER BY mp.total_ebo_spend DESC NULLS LAST
        LIMIT :limit
    """), {"limit": limit}).mappings().all()

    return {
        "pattern"    : "EBO First — Never Came Back Offline",
        "description": "Visited store at least once but never returned (180+ days silent, no online purchases either)",
        "count"      : len(rows),
        "customers"  : [dict(r) for r in rows],
    }


@router.get("/channel-migration/online-never-offline")
def get_online_never_offline(
    limit: int = Query(500, description="Max rows"),
    db: Session = Depends(get_db),
):
    """
    Customers who came online first and never visited a store.
    Opportunity: convert them to in-store shoppers.
    """
    rows = db.execute(text("""
        SELECT
            mp.consumer_name,
            mp.email,
            mp.phone,
            mp.consumer_city,
            mp.consumer_zone,
            mp.consumer_pincode,
            mp.total_online_orders,
            mp.total_online_spend,
            mp.online_aov,
            mp.first_online_date,
            mp.last_online_date,
            mp.online_days_since_last,
            mp.top_category,
            mp.top_brand,
            mp.size_behaviour,
            mp.total_lifetime_spend,
            mp.rfm_segment,
            mp.churn_risk,
            mp.cod_pct,
            NULL::TEXT                                          AS last_online_skus
        FROM public.cust_master_profile mp
        WHERE mp.in_shopify = TRUE
          AND mp.in_ebo = FALSE
        ORDER BY mp.total_online_spend DESC NULLS LAST
        LIMIT :limit
    """), {"limit": limit}).mappings().all()

    return {
        "pattern"    : "Online First — Never Visited Store",
        "description": "Purchased only online, never visited any EBO store",
        "count"      : len(rows),
        "customers"  : [dict(r) for r in rows],
    }


@router.get("/channel-migration/ebo-to-online-same-month")
def get_ebo_to_online_same_month(
    limit: int = Query(500, description="Max rows"),
    db: Session = Depends(get_db),
):
    """
    Customers who visited EBO store and in the same month also bought online.
    These are true omnichannel customers who switch channels rapidly.
    """
    rows = db.execute(text("""
        SELECT
            mp.consumer_name,
            mp.email,
            mp.phone,
            mp.consumer_city,
            mp.consumer_zone,
            mp.consumer_pincode,
            mp.migration_type,
            mp.migration_lag_days,
            mp.first_ebo_date,
            mp.first_online_date,
            mp.total_ebo_bills,
            mp.total_ebo_spend,
            mp.total_online_orders,
            mp.total_online_spend,
            mp.total_lifetime_spend,
            mp.top_category,
            mp.top_brand,
            mp.primary_store,
            mp.rfm_segment,
            NULL::TEXT                                          AS ebo_skus_same_month,
            NULL::TEXT                                          AS online_skus_same_month
        FROM public.cust_master_profile mp
        WHERE mp.migration_type = 'Both Same Time'
           OR (
               mp.in_ebo = TRUE
               AND mp.in_shopify = TRUE
               AND mp.migration_lag_days <= 30
           )
        ORDER BY mp.total_lifetime_spend DESC NULLS LAST
        LIMIT :limit
    """), {"limit": limit}).mappings().all()

    return {
        "pattern"    : "EBO → Online Same Month (Rapid Migration)",
        "description": "Customers who bought offline and online in the same month — true omnichannel behaviour",
        "count"      : len(rows),
        "customers"  : [dict(r) for r in rows],
    }


@router.get("/channel-migration/mom-shift")
def get_mom_channel_shift(
    months: int = Query(12, description="Last N months"),
    db: Session = Depends(get_db),
):
    """
    Month on month channel migration counts.
    Shows how many customers shifted from EBO to Online or Online to EBO each month.
    """
    rows = db.execute(text("""
        SELECT
            DATE_TRUNC('month', first_seen_date)::DATE          AS cohort_month,
            TO_CHAR(DATE_TRUNC('month', first_seen_date), 'Mon YYYY') AS month_label,
            COUNT(*) FILTER (WHERE migration_type = 'EBO First')    AS ebo_first_moved_online,
            COUNT(*) FILTER (WHERE migration_type = 'Shopify First') AS online_first_moved_offline,
            COUNT(*) FILTER (WHERE migration_type = 'Both Same Time') AS same_month_both,
            COUNT(*) FILTER (WHERE migration_type = 'EBO Only')     AS ebo_only,
            COUNT(*) FILTER (WHERE migration_type = 'Shopify Only') AS online_only,
            COUNT(*)                                                  AS total_new
        FROM public.cust_master_profile
        WHERE first_seen_date >= CURRENT_DATE - (:months || ' months')::INTERVAL
          AND first_seen_date IS NOT NULL
        GROUP BY DATE_TRUNC('month', first_seen_date)
        ORDER BY cohort_month DESC
    """), {"months": months}).mappings().all()

    return [dict(r) for r in rows]


@router.get("/channel-migration/export-csv")
def export_migration_csv(
    pattern: str = Query(..., description="ebo_never_back | online_never_offline | same_month | mom_shift"),
    limit  : int = Query(10000, description="Max rows"),
    months : int = Query(12,    description="For mom_shift only"),
    db: Session = Depends(get_db),
):
    """Export any migration pattern as CSV."""
    import io, csv
    from fastapi.responses import StreamingResponse

    pattern_map = {
        "ebo_never_back"       : get_ebo_first_never_back,
        "online_never_offline" : get_online_never_offline,
        "same_month"           : get_ebo_to_online_same_month,
    }

    if pattern == "mom_shift":
        result = get_mom_channel_shift(months, db)
        rows   = result
        if not rows: return {"message": "No data", "count": 0}
        cols   = list(rows[0].keys())
    elif pattern in pattern_map:
        result = pattern_map[pattern](limit, db)
        rows   = result["customers"]
        if not rows: return {"message": "No data", "count": 0}
        cols   = list(rows[0].keys())
    else:
        raise HTTPException(status_code=400, detail=f"Unknown pattern: {pattern}")

    def generate():
        buf    = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=cols)
        writer.writeheader()
        buf.seek(0); yield buf.read(); buf.truncate(0); buf.seek(0)
        for row in rows:
            writer.writerow({k: (str(v) if v is not None else "") for k, v in row.items()})
            buf.seek(0); yield buf.read(); buf.truncate(0); buf.seek(0)

    filename = f"migration_{pattern}.csv"
    return StreamingResponse(
        generate(),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# WHERE clause for each KPI-card migration pattern (matches the summary counts)
_MIGRATION_PATTERN_WHERE = {
    "ebo_first_never_back"      : "mp.in_ebo = TRUE AND mp.in_shopify = FALSE AND mp.ebo_days_since_last > 180",
    "online_only_never_offline" : "mp.in_shopify = TRUE AND mp.in_ebo = FALSE",
    "ebo_first_moved_online"    : "mp.migration_type = 'EBO First'",
    "online_first_moved_offline": "mp.migration_type = 'Shopify First'",
    "same_month_both"           : "mp.migration_type = 'Both Same Time'",
    "total_omnichannel"         : "mp.channel_journey IN ('Both', 'Omnichannel')",
}


@router.get("/channel-migration/export-pattern")
def export_migration_pattern(
    pattern: str = Query(..., description="One of the 6 KPI-card pattern keys"),
    month:   str = Query(None, description="YYYY-MM — only customers active in this month"),
    limit:   int = Query(100000, description="Max rows"),
    db: Session = Depends(get_db),
):
    """
    Download any of the 6 migration KPI patterns as CSV, optionally restricted to a
    given month's active customers (via cust_monthly_active_mv). Columns include the
    month's orders + spend when a month is selected.
    """
    import io, csv
    from fastapi.responses import StreamingResponse

    where = _MIGRATION_PATTERN_WHERE.get(pattern)
    if where is None:
        raise HTTPException(status_code=400, detail=f"Unknown pattern: {pattern}")

    params = {"limit": limit}
    month_join = ""
    month_cols = ""
    if month:
        params["month_date"] = month + "-01"
        month_join = """INNER JOIN (
            SELECT combo,
                   (ebo_orders + online_orders) AS m_orders,
                   (ebo_spend  + online_spend)  AS m_spend
            FROM public.cust_monthly_active_mv
            WHERE activity_month = DATE_TRUNC('month', CAST(:month_date AS DATE))
        ) am ON am.combo = public.fn_clean_combo(mp.combo)"""
        month_cols = ("TO_CHAR(DATE_TRUNC('month', CAST(:month_date AS DATE)), 'Mon YYYY') AS month, "
                      "am.m_orders AS month_orders, ROUND(am.m_spend::NUMERIC, 0) AS month_spend, ")

    rows = db.execute(text(f"""
        SELECT
            {month_cols}
            mp.consumer_name        AS name,
            mp.email,
            mp.phone,
            mp.consumer_city        AS city,
            mp.consumer_zone        AS zone,
            mp.channel_journey,
            mp.migration_type,
            mp.total_ebo_bills,
            mp.total_ebo_spend,
            mp.total_online_orders,
            mp.total_online_spend,
            mp.total_lifetime_orders,
            mp.total_lifetime_spend,
            mp.rfm_segment,
            mp.churn_risk,
            mp.top_category,
            mp.primary_store,
            mp.days_since_last_purchase
        FROM public.cust_master_profile mp
        {month_join}
        WHERE {where}
        ORDER BY mp.total_lifetime_spend DESC NULLS LAST
        LIMIT :limit
    """), params).mappings().all()

    fieldnames = list(rows[0].keys()) if rows else ["name", "email", "phone"]

    def generate():
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=fieldnames)
        writer.writeheader()
        buf.seek(0); yield buf.read(); buf.truncate(0); buf.seek(0)
        for r in rows:
            writer.writerow({k: (str(v) if v is not None else "") for k, v in r.items()})
            buf.seek(0); yield buf.read(); buf.truncate(0); buf.seek(0)

    month_str = f"_{month}" if month else ""
    return StreamingResponse(
        generate(),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=migration_{pattern}{month_str}.csv"},
    )