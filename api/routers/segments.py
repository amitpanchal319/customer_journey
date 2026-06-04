# api/routers/segments.py

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Optional
from database.connection import get_db

router = APIRouter()

# Month "active customers" come from the pre-aggregated MV (cust_monthly_active_mv)
# joined to the profile via the functional index idx_cmp_clean_combo — fast, instead
# of scanning the raw transaction views on every request.
_STATEMENT_TIMEOUT_MS = 20000  # safety net: abort a runaway query, never hang the worker


def _safe_rows(db, sql, params, fallback=None):
    """Run a query under a statement timeout; on timeout/error return fallback gracefully."""
    try:
        db.execute(text(f"SET LOCAL statement_timeout = '{_STATEMENT_TIMEOUT_MS}'"))
        return db.execute(text(sql), params).mappings().all()
    except Exception:
        db.rollback()
        return [] if fallback is None else fallback


def _resolve_range(month, start_month, end_month):
    """
    Resolve a month range from the params. Accepts a single `month` (back-compat) OR
    `start_month`/`end_month` (YYYY-MM). Returns (start_date, end_date) as 'YYYY-MM-01'
    strings (inclusive month range), or (None, None) when no period is selected.
    """
    s = start_month or month
    e = end_month or month or start_month
    if not s and not e:
        return None, None
    s = s or e
    e = e or s
    if e < s:                       # tolerate reversed picks
        s, e = e, s
    return s + "-01", e + "-01"


@router.get("/summary")
def get_segment_summary(
    month:           Optional[str] = None,
    start_month:     Optional[str] = None,
    end_month:       Optional[str] = None,
    channel_journey: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """
    Dashboard summary cards. `channel_journey` and a period are optional and compose.
    Period = a single `month` OR a `start_month`..`end_month` range (YYYY-MM). With a
    period: counts are for customers active in that month range (online/offline/both
    derived from activity in the range). Without a period: lifetime composition.
    """
    cj = channel_journey or None
    s_date, e_date = _resolve_range(month, start_month, end_month)

    if s_date:
        rows = _safe_rows(db, """
            WITH am AS (
                SELECT combo, BOOL_OR(in_ebo) AS in_ebo, BOOL_OR(in_shp) AS in_shp
                FROM public.cust_monthly_active_mv
                WHERE activity_month BETWEEN DATE_TRUNC('month', CAST(:start_date AS DATE))
                                         AND DATE_TRUNC('month', CAST(:end_date AS DATE))
                GROUP BY combo
            ),
            active AS (
                SELECT mp.customer_type, mp.total_lifetime_spend, am.in_ebo, am.in_shp
                FROM public.cust_master_profile mp
                JOIN am ON am.combo = public.fn_clean_combo(mp.combo)
                WHERE (:channel_journey IS NULL OR mp.channel_journey = :channel_journey)
            )
            SELECT
                COUNT(*)                                              AS total_customers,
                COUNT(*) FILTER (WHERE in_shp AND NOT in_ebo)         AS online_customers,
                COUNT(*) FILTER (WHERE in_ebo AND NOT in_shp)         AS offline_customers,
                COUNT(*) FILTER (WHERE in_ebo AND in_shp)             AS both_customers,
                COUNT(*) FILTER (WHERE customer_type = 'Repeat')      AS repeat_customers,
                COUNT(*) FILTER (WHERE customer_type = 'New')         AS new_customers,
                ROUND((COUNT(*) FILTER (WHERE customer_type = 'Repeat')::NUMERIC
                    / NULLIF(COUNT(*), 0) * 100)::NUMERIC, 1)         AS repeat_rate_pct,
                ROUND(AVG(total_lifetime_spend)::NUMERIC, 0)          AS avg_ltv
            FROM active
        """, {"start_date": s_date, "end_date": e_date, "channel_journey": cj})
        return dict(rows[0]) if rows else {
            "total_customers": 0, "online_customers": 0, "offline_customers": 0,
            "both_customers": 0, "repeat_customers": 0, "new_customers": 0,
            "repeat_rate_pct": 0, "avg_ltv": 0,
        }

    row = db.execute(text("""
        SELECT
            COUNT(*)                                            AS total_customers,
            COUNT(*) FILTER (WHERE customer_type = 'Repeat')   AS repeat_customers,
            COUNT(*) FILTER (WHERE customer_type = 'New')      AS new_customers,
            ROUND((COUNT(*) FILTER (WHERE customer_type = 'Repeat')::NUMERIC
                / NULLIF(COUNT(*), 0) * 100)::NUMERIC, 1)      AS repeat_rate_pct,
            ROUND(AVG(total_lifetime_spend)::NUMERIC, 0)        AS avg_ltv,
            COUNT(*) FILTER (WHERE churn_risk = 'High')         AS high_churn_customers,
            COUNT(*) FILTER (WHERE channel_journey = 'Online Only')  AS online_customers,
            COUNT(*) FILTER (WHERE channel_journey = 'Offline Only') AS offline_customers,
            COUNT(*) FILTER (WHERE channel_journey = 'Both')         AS both_customers,
            COUNT(*) FILTER (
                WHERE last_updated_date = CURRENT_DATE
            )                                                   AS new_today
        FROM public.cust_master_profile
        WHERE (:channel_journey IS NULL OR channel_journey = :channel_journey)
    """), {"channel_journey": cj}).mappings().first()
    return dict(row)


@router.get("/rfm")
def get_rfm_distribution(
    zone:            Optional[str] = None,
    platform:        Optional[str] = None,
    channel_journey: Optional[str] = None,
    month:           Optional[str] = None,
    start_month:     Optional[str] = None,
    end_month:       Optional[str] = None,
    top_category:    Optional[str] = None,
    db: Session = Depends(get_db),
):
    filters = ["1=1"]
    params  = {}
    if zone:             filters.append("consumer_zone = :zone");              params["zone"]            = zone
    if platform:         filters.append("platform = :platform");               params["platform"]        = platform
    if channel_journey:  filters.append("channel_journey = :channel_journey"); params["channel_journey"] = channel_journey
    if top_category:     filters.append("top_category = :top_category");       params["top_category"]    = top_category

    s_date, e_date = _resolve_range(month, start_month, end_month)
    if s_date:
        params["start_date"] = s_date
        params["end_date"]   = e_date

    where = " AND ".join(filters)

    if s_date:
        # Customers active in the selected month range; "New This Month" = first purchase in range
        sql = f"""
        WITH active_combos AS (
            SELECT DISTINCT combo FROM public.cust_monthly_active_mv
            WHERE activity_month BETWEEN DATE_TRUNC('month', CAST(:start_date AS DATE))
                                     AND DATE_TRUNC('month', CAST(:end_date AS DATE))
        ),
        new_this_month AS (
            -- Customers whose very first purchase ever was in this range
            SELECT DISTINCT public.fn_clean_combo(mp.combo) AS combo
            FROM public.cust_master_profile mp
            WHERE DATE_TRUNC('month', mp.first_seen_date) BETWEEN DATE_TRUNC('month', CAST(:start_date AS DATE))
                                                             AND DATE_TRUNC('month', CAST(:end_date AS DATE))
        ),
        base_data AS (
            SELECT
                mp.combo,
                -- Override rfm_segment: if first purchase was this month → New This Month
                CASE
                    WHEN ntm.combo IS NOT NULL THEN 'New This Month'
                    ELSE mp.rfm_segment
                END                                             AS rfm_segment,
                mp.total_lifetime_spend,
                mp.total_lifetime_orders
            FROM public.cust_master_profile mp
            INNER JOIN active_combos ac
                    ON ac.combo = public.fn_clean_combo(mp.combo)
            LEFT JOIN new_this_month ntm
                   ON ntm.combo = public.fn_clean_combo(mp.combo)
            WHERE {where}
        )
        SELECT
            rfm_segment,
            COUNT(*)                                            AS customers,
            ROUND(AVG(total_lifetime_spend)::NUMERIC, 0)        AS avg_ltv,
            ROUND(AVG(CASE WHEN total_lifetime_orders > 0
                THEN total_lifetime_spend / total_lifetime_orders
            END)::NUMERIC, 0)                                   AS avg_aov,
            ROUND((COUNT(*)::NUMERIC / SUM(COUNT(*)) OVER () * 100)::NUMERIC, 1) AS pct
        FROM base_data
        GROUP BY rfm_segment
        ORDER BY
            CASE rfm_segment WHEN 'New This Month' THEN 0 ELSE 1 END,
            customers DESC
        """
    else:
        sql = f"""
        SELECT
            rfm_segment,
            COUNT(*)                                            AS customers,
            ROUND(AVG(total_lifetime_spend)::NUMERIC, 0)        AS avg_ltv,
            ROUND(AVG(CASE WHEN total_lifetime_orders > 0
                THEN total_lifetime_spend / total_lifetime_orders
            END)::NUMERIC, 0)                                   AS avg_aov,
            ROUND((COUNT(*)::NUMERIC / SUM(COUNT(*)) OVER () * 100)::NUMERIC, 1) AS pct
        FROM public.cust_master_profile
        WHERE {where}
        GROUP BY rfm_segment
        ORDER BY customers DESC
        """

    rows = _safe_rows(db, sql, params)
    return {"filters_applied": params, "segments": [dict(r) for r in rows]}


@router.get("/rfm/customers")
def get_rfm_customers(
    rfm_segment:  Optional[str] = None,
    zone:         Optional[str] = None,
    platform:     Optional[str] = None,
    month:        Optional[str] = None,
    top_category: Optional[str] = None,
    limit:        int = Query(500),
    db: Session = Depends(get_db),
):
    """
    Get customer details for RFM segment.
    When month is provided: shows month-specific activity (spend, orders, channel, SKUs).
    When no month: shows lifetime metrics.
    """
    filters = ["mp.rfm_segment IS NOT NULL"]
    params  = {}
    if rfm_segment:  filters.append("mp.rfm_segment = :rfm_segment");    params["rfm_segment"]  = rfm_segment
    if zone:         filters.append("mp.consumer_zone = :zone");          params["zone"]         = zone
    if platform:     filters.append("mp.platform = :platform");           params["platform"]     = platform
    if top_category: filters.append("mp.top_category = :top_category");   params["top_category"] = top_category
    if month:
        params["month_date"] = month + "-01"

    where = " AND ".join(filters)

    if month:
        # Month-specific query — join raw views to get what they did THIS month
        sql = f"""
        WITH new_this_month AS (
            SELECT DISTINCT public.fn_clean_combo(mp.combo) AS combo
            FROM public.cust_master_profile mp
            WHERE DATE_TRUNC('month', mp.first_seen_date)
                = DATE_TRUNC('month', CAST(:month_date AS DATE))
        ),
        month_ebo AS (
            SELECT
                public.fn_clean_combo(combo)        AS combo,
                SUM(order_amount)                   AS month_ebo_spend,
                COUNT(*)                            AS month_ebo_orders,
                STRING_AGG(DISTINCT barcode, ', '
                    ORDER BY barcode)               AS month_ebo_skus
            FROM public.cust_ebo_salescombo_view
            WHERE DATE_TRUNC('month', invoice_date)
                = DATE_TRUNC('month', CAST(:month_date AS DATE))
              AND combo IS NOT NULL
            GROUP BY public.fn_clean_combo(combo)
        ),
        month_shp AS (
            SELECT
                public.fn_clean_combo(combo)        AS combo,
                SUM(order_amount)                   AS month_online_spend,
                SUM(order_count)                    AS month_online_orders,
                STRING_AGG(DISTINCT client_sku_id_ean, ', '
                    ORDER BY client_sku_id_ean)     AS month_online_skus
            FROM public.cust_osdcombo_view
            WHERE DATE_TRUNC('month', channel_order_date)
                = DATE_TRUNC('month', CAST(:month_date AS DATE))
              AND combo IS NOT NULL
              AND combo NOT LIKE '%myshopify%'
            GROUP BY public.fn_clean_combo(combo)
        )
        SELECT
            mp.consumer_name,
            mp.email,
            mp.phone,
            mp.consumer_city,
            mp.consumer_state,
            mp.consumer_zone,
            mp.consumer_pincode,
            mp.platform,
            mp.channel_journey,
            CASE
                WHEN ntm.combo IS NOT NULL THEN 'New This Month'
                ELSE mp.rfm_segment
            END                                             AS rfm_segment,
            mp.churn_risk,
            mp.customer_type,
            mp.top_category,
            mp.top_brand,
            mp.size_behaviour,
            mp.primary_store,
            mp.migration_type,

            -- Month-specific metrics
            COALESCE(me.month_ebo_spend, 0)         AS month_ebo_spend,
            COALESCE(me.month_ebo_orders, 0)        AS month_ebo_orders,
            me.month_ebo_skus,
            COALESCE(ms.month_online_spend, 0)      AS month_online_spend,
            COALESCE(ms.month_online_orders, 0)     AS month_online_orders,
            ms.month_online_skus,
            COALESCE(me.month_ebo_spend, 0)
              + COALESCE(ms.month_online_spend, 0)  AS month_total_spend,
            COALESCE(me.month_ebo_orders, 0)
              + COALESCE(ms.month_online_orders, 0) AS month_total_orders,
            CASE
                WHEN me.combo IS NOT NULL AND ms.combo IS NOT NULL THEN 'Both'
                WHEN me.combo IS NOT NULL THEN 'EBO'
                WHEN ms.combo IS NOT NULL THEN 'Shopify'
                ELSE 'Unknown'
            END                                     AS month_active_channel,

            -- Lifetime for context
            mp.total_lifetime_spend,
            mp.total_lifetime_orders,
            mp.days_since_last_purchase,
            mp.first_seen_date,
            mp.last_updated_date

        FROM public.cust_master_profile mp
        LEFT JOIN month_ebo  me  ON me.combo  = public.fn_clean_combo(mp.combo)
        LEFT JOIN month_shp  ms  ON ms.combo  = public.fn_clean_combo(mp.combo)
        LEFT JOIN new_this_month ntm ON ntm.combo = public.fn_clean_combo(mp.combo)
        WHERE {where}
        ORDER BY month_total_spend DESC NULLS LAST
        LIMIT :limit
        """
    else:
        # No month — show lifetime metrics
        sql = f"""
        SELECT
            mp.consumer_name,
            mp.email,
            mp.phone,
            mp.consumer_city,
            mp.consumer_state,
            mp.consumer_zone,
            mp.consumer_pincode,
            mp.platform,
            mp.channel_journey,
            mp.rfm_segment,
            mp.churn_risk,
            mp.customer_type,
            mp.top_category,
            mp.top_brand,
            mp.size_behaviour,
            mp.size_combination,
            mp.primary_store,
            mp.migration_type,
            mp.total_lifetime_spend,
            mp.total_lifetime_orders,
            mp.total_ebo_spend,
            mp.total_online_spend,
            mp.ebo_aov,
            mp.online_aov,
            mp.days_since_last_purchase,
            mp.first_seen_date,
            mp.last_updated_date,
            mp.return_risk,
            mp.rfm_r, mp.rfm_f, mp.rfm_m
        FROM public.cust_master_profile mp
        WHERE {where}
        ORDER BY mp.total_lifetime_spend DESC NULLS LAST
        LIMIT :limit
        """

    rows = db.execute(
        text(sql), {**params, "limit": limit}
    ).mappings().all()

    return {
        "filters_applied": params,
        "count"          : len(rows),
        "customers"      : [dict(r) for r in rows],
    }


@router.get("/rfm/export-csv")
def export_rfm_csv(
    rfm_segment:  Optional[str] = None,
    zone:         Optional[str] = None,
    platform:     Optional[str] = None,
    month:        Optional[str] = None,
    top_category: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Export RFM filtered customers as CSV with all details."""
    import io, csv
    from fastapi.responses import StreamingResponse

    result = get_rfm_customers(
        rfm_segment=rfm_segment, zone=zone, platform=platform,
        month=month, top_category=top_category, limit=100000, db=db
    )
    rows = result["customers"]

    def generate():
        if not rows:
            yield "No data found\n"
            return
        buf    = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        buf.seek(0); yield buf.read(); buf.truncate(0); buf.seek(0)
        for row in rows:
            writer.writerow({k: (str(v) if v is not None else "") for k, v in row.items()})
            buf.seek(0); yield buf.read(); buf.truncate(0); buf.seek(0)

    month_str = f"_{month}" if month else ""
    seg_str   = f"_{rfm_segment.replace(' ','_')}" if rfm_segment else ""
    filename  = f"rfm{seg_str}{month_str}.csv"
    return StreamingResponse(
        generate(),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/churn")
def get_churn_distribution(
    zone:            Optional[str] = None,
    platform:        Optional[str] = None,
    channel_journey: Optional[str] = None,
    month:           Optional[str] = None,
    start_month:     Optional[str] = None,
    end_month:       Optional[str] = None,
    db: Session = Depends(get_db),
):
    filters = ["1=1"]
    params  = {}
    if zone:            filters.append("mp.consumer_zone = :zone");              params["zone"]            = zone
    if platform:        filters.append("mp.platform = :platform");               params["platform"]        = platform
    if channel_journey: filters.append("mp.channel_journey = :channel_journey"); params["channel_journey"] = channel_journey
    where = " AND ".join(filters)

    s_date, e_date = _resolve_range(month, start_month, end_month)
    if s_date:
        params["start_date"] = s_date
        params["end_date"]   = e_date
        sql = f"""
        WITH active_combos AS (
            SELECT DISTINCT combo FROM public.cust_monthly_active_mv
            WHERE activity_month BETWEEN DATE_TRUNC('month', CAST(:start_date AS DATE))
                                     AND DATE_TRUNC('month', CAST(:end_date AS DATE))
        )
        SELECT
            mp.churn_risk,
            COUNT(*)                                            AS customers,
            ROUND(AVG(mp.total_lifetime_spend)::NUMERIC, 0)     AS avg_ltv,
            ROUND((COUNT(*)::NUMERIC / SUM(COUNT(*)) OVER () * 100)::NUMERIC, 1) AS pct
        FROM public.cust_master_profile mp
        INNER JOIN active_combos ac ON ac.combo = public.fn_clean_combo(mp.combo)
        WHERE {where}
        GROUP BY mp.churn_risk
        ORDER BY CASE mp.churn_risk
            WHEN 'High' THEN 1 WHEN 'Medium' THEN 2
            WHEN 'Low'  THEN 3 ELSE 4 END
        """
    else:
        sql = f"""
        SELECT
            mp.churn_risk,
            COUNT(*)                                            AS customers,
            ROUND(AVG(mp.total_lifetime_spend)::NUMERIC, 0)     AS avg_ltv,
            ROUND((COUNT(*)::NUMERIC / SUM(COUNT(*)) OVER () * 100)::NUMERIC, 1) AS pct
        FROM public.cust_master_profile mp
        WHERE {where}
        GROUP BY mp.churn_risk
        ORDER BY CASE mp.churn_risk
            WHEN 'High' THEN 1 WHEN 'Medium' THEN 2
            WHEN 'Low'  THEN 3 ELSE 4 END
        """

    return [dict(r) for r in _safe_rows(db, sql, params)]


@router.get("/return-risk")
def get_return_risk_distribution(
    zone:            Optional[str] = None,
    platform:        Optional[str] = None,
    channel_journey: Optional[str] = None,
    month:           Optional[str] = None,
    start_month:     Optional[str] = None,
    end_month:       Optional[str] = None,
    db: Session = Depends(get_db),
):
    filters = ["1=1"]
    params  = {}
    if zone:            filters.append("mp.consumer_zone = :zone");              params["zone"]            = zone
    if platform:        filters.append("mp.platform = :platform");               params["platform"]        = platform
    if channel_journey: filters.append("mp.channel_journey = :channel_journey"); params["channel_journey"] = channel_journey
    where = " AND ".join(filters)

    s_date, e_date = _resolve_range(month, start_month, end_month)
    if s_date:
        params["start_date"] = s_date
        params["end_date"]   = e_date
        sql = f"""
        WITH active_combos AS (
            SELECT DISTINCT combo FROM public.cust_monthly_active_mv
            WHERE activity_month BETWEEN DATE_TRUNC('month', CAST(:start_date AS DATE))
                                     AND DATE_TRUNC('month', CAST(:end_date AS DATE))
        )
        SELECT
            mp.return_risk,
            COUNT(*)                                            AS customers,
            ROUND(AVG(mp.total_lifetime_spend)::NUMERIC, 0)     AS avg_ltv,
            ROUND((COUNT(*)::NUMERIC / SUM(COUNT(*)) OVER () * 100)::NUMERIC, 1) AS pct
        FROM public.cust_master_profile mp
        INNER JOIN active_combos ac ON ac.combo = public.fn_clean_combo(mp.combo)
        WHERE {where}
        GROUP BY mp.return_risk
        ORDER BY CASE mp.return_risk
            WHEN 'High' THEN 1 WHEN 'Medium' THEN 2
            WHEN 'Low'  THEN 3 WHEN 'No Returns' THEN 4 ELSE 5 END
        """
    else:
        sql = f"""
        SELECT
            mp.return_risk,
            COUNT(*)                                            AS customers,
            ROUND(AVG(mp.total_lifetime_spend)::NUMERIC, 0)     AS avg_ltv,
            ROUND((COUNT(*)::NUMERIC / SUM(COUNT(*)) OVER () * 100)::NUMERIC, 1) AS pct
        FROM public.cust_master_profile mp
        WHERE {where}
        GROUP BY mp.return_risk
        ORDER BY CASE mp.return_risk
            WHEN 'High' THEN 1 WHEN 'Medium' THEN 2
            WHEN 'Low'  THEN 3 WHEN 'No Returns' THEN 4 ELSE 5 END
        """

    return [dict(r) for r in _safe_rows(db, sql, params)]


@router.get("/aov-comparison")
def get_aov_comparison(
    month          : Optional[str] = None,
    channel_journey: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """AOV comparison — supports month filter using raw transaction views."""
    if month:
        # Month-specific: compute AOV from raw transaction views
        params = {"month_date": month + "-01"}
        cj_filter = "AND mp.channel_journey = :channel_journey" if channel_journey else ""
        if channel_journey:
            params["channel_journey"] = channel_journey

        rows = _safe_rows(db, f"""
        WITH am AS (
            SELECT combo, ebo_orders, ebo_spend, online_orders, online_spend
            FROM public.cust_monthly_active_mv
            WHERE activity_month = DATE_TRUNC('month', CAST(:month_date AS DATE))
        )
        SELECT
            mp.customer_type,
            COUNT(*)                                    AS customers,
            ROUND(AVG(CASE WHEN am.online_orders > 0
                THEN am.online_spend / am.online_orders END)::NUMERIC, 0) AS avg_online_aov,
            ROUND(AVG(CASE WHEN am.ebo_orders > 0
                THEN am.ebo_spend / am.ebo_orders END)::NUMERIC, 0)       AS avg_ebo_aov,
            ROUND(AVG(mp.total_lifetime_spend)::NUMERIC, 0)              AS avg_ltv
        FROM public.cust_master_profile mp
        INNER JOIN am ON am.combo = public.fn_clean_combo(mp.combo)
        WHERE mp.customer_type IN ('New', 'Repeat')
          {cj_filter}
        GROUP BY mp.customer_type
        """, params)
    else:
        params = {}
        cj_filter = "AND channel_journey = :channel_journey" if channel_journey else ""
        if channel_journey:
            params["channel_journey"] = channel_journey
        rows = db.execute(text(f"""
        SELECT
            customer_type,
            COUNT(*)                                                    AS customers,
            ROUND(AVG(ebo_aov)::NUMERIC, 0)                             AS avg_ebo_aov,
            ROUND(AVG(online_aov)::NUMERIC, 0)                          AS avg_online_aov,
            ROUND(AVG(total_lifetime_spend)::NUMERIC, 0)                AS avg_ltv
        FROM public.cust_master_profile
        WHERE customer_type IN ('New', 'Repeat')
          {cj_filter}
        GROUP BY customer_type
        """), params).mappings().all()

    return [dict(r) for r in rows]


@router.get("/frequency")
def get_frequency_distribution(
    month          : Optional[str] = None,
    channel_journey: Optional[str] = None,
    db: Session = Depends(get_db)
):
    filters = ["1=1"]
    params  = {}
    if channel_journey:
        filters.append("channel_journey = :channel_journey")
        params["channel_journey"] = channel_journey
    if month:
        filters.append("""
            public.fn_clean_combo(combo) IN (
                SELECT combo FROM public.cust_monthly_active_mv
                WHERE activity_month = DATE_TRUNC('month', CAST(:month_date AS DATE))
            )""")
        params["month_date"] = month + "-01"

    where = " AND ".join(filters)
    rows = _safe_rows(db, f"""
        SELECT
            frequency_bucket,
            COUNT(*)                                            AS customers,
            ROUND(AVG(total_lifetime_spend)::NUMERIC, 0)        AS avg_ltv,
            ROUND((COUNT(*)::NUMERIC / SUM(COUNT(*)) OVER () * 100)::NUMERIC, 1) AS pct
        FROM public.cust_master_profile
        WHERE {where}
        GROUP BY frequency_bucket
        ORDER BY CASE frequency_bucket
            WHEN '1 Order'    THEN 1 WHEN '2 Orders'   THEN 2
            WHEN '3-4 Orders' THEN 3 WHEN '5-9 Orders' THEN 4
            ELSE 5 END
    """, params)
    return [dict(r) for r in rows]


@router.get("/frequency/export-csv")
def export_frequency_csv(
    channel_journey: Optional[str] = None,
    month:           Optional[str] = None,
    db: Session = Depends(get_db),
):
    """
    CSV of purchase-frequency customers — month-aware.
    Columns: month, email, name, phone, city, order_count, amount.
    With month: order_count + amount are that month's activity (from the MV).
    Without month: lifetime order_count + amount.
    """
    import io, csv
    from fastapi.responses import StreamingResponse

    cj_filter = "AND mp.channel_journey = :channel_journey" if channel_journey else ""
    params = {}
    if channel_journey:
        params["channel_journey"] = channel_journey

    if month:
        params["month_date"] = month + "-01"
        sql = f"""
        WITH am AS (
            SELECT combo,
                   (ebo_orders + online_orders) AS orders,
                   (ebo_spend  + online_spend)  AS amount
            FROM public.cust_monthly_active_mv
            WHERE activity_month = DATE_TRUNC('month', CAST(:month_date AS DATE))
        )
        SELECT
            TO_CHAR(DATE_TRUNC('month', CAST(:month_date AS DATE)), 'Mon YYYY') AS month,
            mp.email,
            mp.consumer_name                       AS name,
            mp.phone,
            mp.consumer_city                       AS city,
            am.orders                              AS order_count,
            ROUND(am.amount::NUMERIC, 0)           AS amount
        FROM public.cust_master_profile mp
        INNER JOIN am ON am.combo = public.fn_clean_combo(mp.combo)
        WHERE 1=1 {cj_filter}
        ORDER BY am.amount DESC NULLS LAST
        LIMIT 100000
        """
    else:
        sql = f"""
        SELECT
            'All Time'                             AS month,
            mp.email,
            mp.consumer_name                       AS name,
            mp.phone,
            mp.consumer_city                       AS city,
            mp.total_lifetime_orders               AS order_count,
            ROUND(mp.total_lifetime_spend::NUMERIC, 0) AS amount
        FROM public.cust_master_profile mp
        WHERE 1=1 {cj_filter}
        ORDER BY mp.total_lifetime_spend DESC NULLS LAST
        LIMIT 100000
        """

    rows = _safe_rows(db, sql, params)
    fieldnames = ["month", "email", "name", "phone", "city", "order_count", "amount"]

    def generate():
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=fieldnames)
        writer.writeheader()
        buf.seek(0); yield buf.read(); buf.truncate(0); buf.seek(0)
        for r in rows:
            writer.writerow({k: (r.get(k) if r.get(k) is not None else "") for k in fieldnames})
            buf.seek(0); yield buf.read(); buf.truncate(0); buf.seek(0)

    ch_str    = f"_{channel_journey.replace(' ', '_')}" if channel_journey else ""
    month_str = f"_{month}" if month else "_all_time"
    filename  = f"purchase_frequency{ch_str}{month_str}.csv"
    return StreamingResponse(
        generate(),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/migration")
def get_migration_breakdown(db: Session = Depends(get_db)):
    rows = db.execute(text("""
        SELECT
            migration_type,
            COUNT(*)                                            AS customers,
            ROUND(AVG(migration_lag_days)::NUMERIC, 0)          AS avg_lag_days,
            ROUND(AVG(total_lifetime_spend)::NUMERIC, 0)        AS avg_ltv,
            ROUND((COUNT(*)::NUMERIC / SUM(COUNT(*)) OVER () * 100)::NUMERIC, 1) AS pct
        FROM public.cust_master_profile
        GROUP BY migration_type
        ORDER BY customers DESC
    """)).mappings().all()
    return [dict(r) for r in rows]


@router.get("/category")
def get_category_breakdown(
    zone:    Optional[str] = None,
    channel: Optional[str] = None,
    month:   Optional[str] = None,
    db: Session = Depends(get_db),
):
    filters = ["top_category IS NOT NULL"]
    params  = {}
    if zone:    filters.append("consumer_zone = :zone");      params["zone"]    = zone
    if channel: filters.append("channel_journey = :channel"); params["channel"] = channel
    if month:
        filters.append("""
            public.fn_clean_combo(combo) IN (
                SELECT combo FROM public.cust_monthly_active_mv
                WHERE activity_month = DATE_TRUNC('month', CAST(:month_date AS DATE))
            )""")
        params["month_date"] = month + "-01"
    where = " AND ".join(filters)

    rows = _safe_rows(db, f"""
        SELECT
            top_category,
            COUNT(*)                                                    AS customers,
            COUNT(*) FILTER (WHERE is_single_category = TRUE)           AS single_cat_customers,
            COUNT(*) FILTER (WHERE customer_type = 'Repeat')            AS repeat_customers,
            ROUND((COUNT(*) FILTER (WHERE customer_type = 'Repeat')::NUMERIC
                / NULLIF(COUNT(*), 0) * 100)::NUMERIC, 1)               AS repeat_rate_pct,
            ROUND(AVG(total_lifetime_spend)::NUMERIC, 0)                AS avg_ltv
        FROM public.cust_master_profile
        WHERE {where}
        GROUP BY top_category
        ORDER BY customers DESC
    """, params)
    return [dict(r) for r in rows]


@router.get("/size")
def get_size_behaviour(db: Session = Depends(get_db)):
    behaviour = db.execute(text("""
        SELECT
            size_behaviour,
            COUNT(*)                                            AS customers,
            ROUND((COUNT(*)::NUMERIC / SUM(COUNT(*)) OVER () * 100)::NUMERIC, 1) AS pct
        FROM public.cust_master_profile
        WHERE size_behaviour != 'No Size Data'
        GROUP BY size_behaviour
        ORDER BY customers DESC
    """)).mappings().all()

    combinations = db.execute(text("""
        SELECT size_combination, COUNT(*) AS customers
        FROM public.cust_master_profile
        WHERE size_behaviour = 'Multi Size'
          AND size_combination IS NOT NULL
        GROUP BY size_combination
        ORDER BY customers DESC
        LIMIT 20
    """)).mappings().all()

    return {
        "size_behaviour"   : [dict(r) for r in behaviour],
        "top_combinations" : [dict(r) for r in combinations],
    }