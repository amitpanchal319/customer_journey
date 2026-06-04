# api/routers/segments.py
# ----------------------------------------------------------------
# Segment Dashboard — RFM, churn, filters, summary counts
# All queries hit cust_master_profile only (indexed columns)
# ----------------------------------------------------------------

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Optional
from database.connection import get_db

router = APIRouter()


@router.get("/summary")
def get_segment_summary(db: Session = Depends(get_db)):
    """
    High-level summary counts for the dashboard header cards.
    Total customers, repeat %, avg LTV, active today.
    """
    row = db.execute(text("""
        SELECT
            COUNT(*)                                            AS total_customers,
            COUNT(*) FILTER (WHERE customer_type = 'Repeat')   AS repeat_customers,
            ROUND(
                COUNT(*) FILTER (WHERE customer_type = 'Repeat')::NUMERIC
                / NULLIF(COUNT(*), 0) * 100, 1
            )                                                   AS repeat_rate_pct,
            ROUND(AVG(total_lifetime_spend)::NUMERIC, 0)        AS avg_ltv,
            COUNT(*) FILTER (WHERE churn_risk = 'High')         AS high_churn_customers,
            COUNT(*) FILTER (
                WHERE last_updated_date = CURRENT_DATE
            )                                                   AS new_today
        FROM public.cust_master_profile
    """)).mappings().first()
    return dict(row)


@router.get("/rfm")
def get_rfm_distribution(
    zone:          Optional[str] = None,
    state:         Optional[str] = None,
    platform:      Optional[str] = None,
    channel:       Optional[str] = None,
    top_category:  Optional[str] = None,
    db: Session = Depends(get_db),
):
    """
    RFM segment distribution with optional filters.
    All filter columns are indexed — no LIKE, no joins at query time.
    """
    filters = ["1=1"]
    params  = {}

    if zone:          filters.append("consumer_zone = :zone");          params["zone"]         = zone
    if state:         filters.append("consumer_state = :state");        params["state"]        = state
    if platform:      filters.append("platform = :platform");           params["platform"]     = platform
    if channel:       filters.append("channel_journey = :channel");     params["channel"]      = channel
    if top_category:  filters.append("top_category = :top_category");   params["top_category"] = top_category

    where = " AND ".join(filters)

    rows = db.execute(text(f"""
        SELECT
            rfm_segment,
            COUNT(*)                                            AS customers,
            ROUND(AVG(total_lifetime_spend)::NUMERIC, 0)        AS avg_ltv,
            ROUND(AVG(
                COALESCE(ebo_aov, 0) + COALESCE(online_aov, 0)
            )::NUMERIC, 0)                                      AS avg_aov,
            ROUND(
                COUNT(*)::NUMERIC / SUM(COUNT(*)) OVER () * 100, 1
            )                                                   AS pct
        FROM public.cust_master_profile
        WHERE {where}
        GROUP BY rfm_segment
        ORDER BY customers DESC
    """), params).mappings().all()

    return {"filters_applied": params, "segments": [dict(r) for r in rows]}


@router.get("/churn")
def get_churn_distribution(
    zone:     Optional[str] = None,
    platform: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Churn risk distribution with optional geo / platform filters."""
    filters = ["1=1"]
    params  = {}
    if zone:     filters.append("consumer_zone = :zone");     params["zone"]     = zone
    if platform: filters.append("platform = :platform");      params["platform"] = platform

    where = " AND ".join(filters)

    rows = db.execute(text(f"""
        SELECT
            churn_risk,
            COUNT(*)                                            AS customers,
            ROUND(AVG(total_lifetime_spend)::NUMERIC, 0)        AS avg_ltv,
            ROUND(
                COUNT(*)::NUMERIC / SUM(COUNT(*)) OVER () * 100, 1
            )                                                   AS pct
        FROM public.cust_master_profile
        WHERE {where}
        GROUP BY churn_risk
        ORDER BY
            CASE churn_risk
                WHEN 'High'   THEN 1
                WHEN 'Medium' THEN 2
                WHEN 'Low'    THEN 3
                ELSE 4
            END
    """), params).mappings().all()

    return [dict(r) for r in rows]


@router.get("/aov-comparison")
def get_aov_comparison(db: Session = Depends(get_db)):
    """AOV comparison — New vs Repeat customers across both channels."""
    rows = db.execute(text("""
        SELECT
            customer_type,
            COUNT(*)                                                    AS customers,
            ROUND(AVG(ebo_aov)::NUMERIC, 0)                             AS avg_ebo_aov,
            ROUND(AVG(online_aov)::NUMERIC, 0)                          AS avg_online_aov,
            ROUND(AVG(
                total_lifetime_spend / NULLIF(total_lifetime_orders, 0)
            )::NUMERIC, 0)                                              AS blended_aov,
            ROUND(AVG(total_lifetime_spend)::NUMERIC, 0)                AS avg_ltv
        FROM public.cust_master_profile
        WHERE customer_type IN ('New', 'Repeat')
        GROUP BY customer_type
    """)).mappings().all()
    return [dict(r) for r in rows]


@router.get("/frequency")
def get_frequency_distribution(db: Session = Depends(get_db)):
    """Purchase frequency bucket distribution."""
    rows = db.execute(text("""
        SELECT
            frequency_bucket,
            COUNT(*)                                            AS customers,
            ROUND(AVG(total_lifetime_spend)::NUMERIC, 0)        AS avg_ltv,
            ROUND(
                COUNT(*)::NUMERIC / SUM(COUNT(*)) OVER () * 100, 1
            )                                                   AS pct
        FROM public.cust_master_profile
        GROUP BY frequency_bucket
        ORDER BY
            CASE frequency_bucket
                WHEN '1 Order'    THEN 1
                WHEN '2 Orders'   THEN 2
                WHEN '3-4 Orders' THEN 3
                WHEN '5-9 Orders' THEN 4
                ELSE 5
            END
    """)).mappings().all()
    return [dict(r) for r in rows]


@router.get("/migration")
def get_migration_breakdown(db: Session = Depends(get_db)):
    """Channel migration type distribution + avg migration lag."""
    rows = db.execute(text("""
        SELECT
            migration_type,
            COUNT(*)                                            AS customers,
            ROUND(AVG(migration_lag_days)::NUMERIC, 0)          AS avg_lag_days,
            ROUND(AVG(total_lifetime_spend)::NUMERIC, 0)        AS avg_ltv,
            ROUND(
                COUNT(*)::NUMERIC / SUM(COUNT(*)) OVER () * 100, 1
            )                                                   AS pct
        FROM public.cust_master_profile
        GROUP BY migration_type
        ORDER BY customers DESC
    """)).mappings().all()
    return [dict(r) for r in rows]


@router.get("/category")
def get_category_breakdown(
    zone:    Optional[str] = None,
    channel: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Category-wise customer distribution including category-only customers."""
    filters = ["top_category IS NOT NULL"]
    params  = {}
    if zone:    filters.append("consumer_zone = :zone");    params["zone"]    = zone
    if channel: filters.append("channel_journey = :channel"); params["channel"] = channel

    where = " AND ".join(filters)

    rows = db.execute(text(f"""
        SELECT
            top_category,
            COUNT(*)                                                    AS customers,
            COUNT(*) FILTER (WHERE is_single_category = TRUE)           AS single_cat_customers,
            COUNT(*) FILTER (WHERE customer_type = 'Repeat')            AS repeat_customers,
            ROUND(
                COUNT(*) FILTER (WHERE customer_type = 'Repeat')::NUMERIC
                / NULLIF(COUNT(*), 0) * 100, 1
            )                                                           AS repeat_rate_pct,
            ROUND(AVG(total_lifetime_spend)::NUMERIC, 0)                AS avg_ltv
        FROM public.cust_master_profile
        WHERE {where}
        GROUP BY top_category
        ORDER BY customers DESC
    """), params).mappings().all()
    return [dict(r) for r in rows]


@router.get("/size")
def get_size_behaviour(db: Session = Depends(get_db)):
    """Size behaviour distribution + top size combinations."""
    behaviour = db.execute(text("""
        SELECT
            size_behaviour,
            COUNT(*)                                            AS customers,
            ROUND(
                COUNT(*)::NUMERIC / SUM(COUNT(*)) OVER () * 100, 1
            )                                                   AS pct
        FROM public.cust_master_profile
        WHERE size_behaviour != 'No Size Data'
        GROUP BY size_behaviour
        ORDER BY customers DESC
    """)).mappings().all()

    combinations = db.execute(text("""
        SELECT
            size_combination,
            COUNT(*)                                            AS customers
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


# ================================================================
# api/routers/cohorts.py
# ================================================================

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Optional
from database.connection import get_db

router = APIRouter()


@router.get("/retention")
def get_cohort_retention(
    months: int = Query(12, description="Number of past months of cohorts to show"),
    db: Session = Depends(get_db),
):
    """
    Cohort retention grid.
    Returns cohort_month × months_since_first × retention_rate_pct.
    Frontend renders this as a heatmap table.
    """
    rows = db.execute(text("""
        SELECT
            TO_CHAR(cohort_month, 'Mon YYYY')   AS cohort_label,
            cohort_month,
            months_since_first,
            cohort_size,
            active_customers,
            retention_rate_pct,
            customer_activity_type
        FROM public.cust_monthly_cohort_mv
        WHERE cohort_month >= DATE_TRUNC('month', CURRENT_DATE)
                             - (:months || ' months')::INTERVAL
        ORDER BY cohort_month, months_since_first
    """), {"months": months}).mappings().all()
    return [dict(r) for r in rows]


@router.get("/mom")
def get_mom_new_vs_repeat(
    months: int = Query(12, description="Number of past months to show"),
    db: Session = Depends(get_db),
):
    """
    Month-on-month new vs repeat customer contribution.
    New = acquisition month (months_since_first = 0).
    Repeat = any activity in subsequent months.
    """
    rows = db.execute(text("""
        SELECT
            TO_CHAR(activity_month, 'Mon YYYY')     AS month_label,
            activity_month,
            SUM(CASE WHEN customer_activity_type = 'New'
                THEN active_customers ELSE 0 END)   AS new_customers,
            SUM(CASE WHEN customer_activity_type = 'Repeat'
                THEN active_customers ELSE 0 END)   AS repeat_customers,
            SUM(active_customers)                   AS total_active,
            ROUND(
                SUM(CASE WHEN customer_activity_type = 'Repeat'
                    THEN active_customers ELSE 0 END)::NUMERIC
                / NULLIF(SUM(active_customers), 0) * 100, 1
            )                                       AS repeat_pct
        FROM public.cust_monthly_cohort_mv
        WHERE activity_month >= DATE_TRUNC('month', CURRENT_DATE)
                                - (:months || ' months')::INTERVAL
        GROUP BY activity_month
        ORDER BY activity_month DESC
    """), {"months": months}).mappings().all()
    return [dict(r) for r in rows]


@router.get("/retention-flags")
def get_retention_flag_summary(db: Session = Depends(get_db)):
    """
    30 / 60 / 90 day retention rates overall and by channel.
    """
    rows = db.execute(text("""
        SELECT
            channel_journey,
            COUNT(*)                                                    AS customers,
            COUNT(*) FILTER (WHERE retained_30d = TRUE)                 AS retained_30d,
            COUNT(*) FILTER (WHERE retained_60d = TRUE)                 AS retained_60d,
            COUNT(*) FILTER (WHERE retained_90d = TRUE)                 AS retained_90d,
            ROUND(COUNT(*) FILTER (WHERE retained_30d)::NUMERIC
                / NULLIF(COUNT(*), 0) * 100, 1)                         AS pct_30d,
            ROUND(COUNT(*) FILTER (WHERE retained_60d)::NUMERIC
                / NULLIF(COUNT(*), 0) * 100, 1)                         AS pct_60d,
            ROUND(COUNT(*) FILTER (WHERE retained_90d)::NUMERIC
                / NULLIF(COUNT(*), 0) * 100, 1)                         AS pct_90d,
            ROUND(AVG(days_1st_to_2nd_purchase)::NUMERIC, 0)            AS avg_days_to_2nd_purchase
        FROM public.cust_master_profile
        WHERE customer_type IN ('New', 'Repeat')
        GROUP BY channel_journey
        ORDER BY customers DESC
    """)).mappings().all()
    return [dict(r) for r in rows]


# ================================================================
# api/routers/stores.py
# ================================================================

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Optional
from database.connection import get_db

router = APIRouter()


@router.get("/summary")
def get_stores_summary(db: Session = Depends(get_db)):
    """All stores ranked by total customers."""
    rows = db.execute(text("""
        SELECT
            store_name,
            total_customers,
            repeat_customers,
            repeat_customer_pct,
            retention_30d_pct,
            retention_60d_pct,
            retention_90d_pct,
            avg_customer_ltv,
            total_store_revenue,
            migrated_to_online,
            top_category_at_store,
            champion_count,
            high_churn_count
        FROM public.store_summary_mv
        ORDER BY total_customers DESC
    """)).mappings().all()
    return [dict(r) for r in rows]


@router.get("/{store_name}")
def get_store_detail(store_name: str, db: Session = Depends(get_db)):
    """
    Store detail + customer list for a specific store.
    Customers are fetched from cust_master_profile using indexed primary_store.
    """
    store = db.execute(text("""
        SELECT * FROM public.store_summary_mv
        WHERE store_name = :store_name
        LIMIT 1
    """), {"store_name": store_name}).mappings().first()

    if not store:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Store not found")

    customers = db.execute(text("""
        SELECT
            unq_id, consumer_name, email, phone,
            consumer_city, consumer_zone,
            rfm_segment, churn_risk, customer_type,
            total_ebo_bills, total_ebo_spend, ebo_aov,
            total_lifetime_spend, last_updated_date
        FROM public.cust_master_profile
        WHERE primary_store = :store_name
        ORDER BY total_lifetime_spend DESC
        LIMIT 500
    """), {"store_name": store_name}).mappings().all()

    return {
        "store"     : dict(store),
        "customers" : [dict(r) for r in customers],
    }


# ================================================================
# api/routers/export.py
# ================================================================

import io
import csv
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Optional
from database.connection import get_db

router = APIRouter()

# Columns always included in the CSV export
EXPORT_COLUMNS = """
    unq_id, consumer_name, email, phone,
    consumer_city, consumer_state, consumer_zone, consumer_pincode,
    platform, channel_journey, migration_type,
    rfm_segment, churn_risk, return_risk, customer_type,
    frequency_bucket, recency_bucket,
    total_lifetime_spend, total_lifetime_orders,
    total_ebo_bills, total_ebo_spend, ebo_aov,
    total_online_orders, total_online_spend, online_aov,
    top_category, category_label, top_brand, size_behaviour,
    primary_store, consumer_pincode,
    retained_30d, retained_60d, retained_90d,
    first_seen_date, last_updated_date, days_since_last_purchase
"""


@router.get("/csv")
def export_csv(
    # ── Segment filters ────────────────────────────────────────────────────────
    rfm_segment:    Optional[str] = Query(None, description="e.g. Champion"),
    churn_risk:     Optional[str] = Query(None, description="High | Medium | Low | None"),
    return_risk:    Optional[str] = Query(None, description="High | Medium | Low | No Returns"),
    customer_type:  Optional[str] = Query(None, description="New | Repeat"),
    frequency_bucket: Optional[str] = Query(None, description="1 Order | 2 Orders | 3-4 Orders | ..."),
    recency_bucket: Optional[str] = Query(None, description="Active | Warm | Cooling | At Risk | Lapsed"),

    # ── Channel filters ────────────────────────────────────────────────────────
    platform:       Optional[str] = Query(None, description="Shopify | EBO | Both"),
    channel_journey: Optional[str] = Query(None, description="Omnichannel | Offline Only | Online Only"),
    migration_type: Optional[str] = Query(None, description="EBO First | Shopify First | ..."),

    # ── Geo filters ────────────────────────────────────────────────────────────
    consumer_zone:  Optional[str] = Query(None),
    consumer_state: Optional[str] = Query(None),
    consumer_city:  Optional[str] = Query(None),
    consumer_pincode: Optional[str] = Query(None),

    # ── Product filters ────────────────────────────────────────────────────────
    top_category:   Optional[str] = Query(None, description="e.g. LEHENGA"),
    category_label: Optional[str] = Query(None, description="e.g. LEHENGA Only"),
    top_brand:      Optional[str] = Query(None),
    size_behaviour: Optional[str] = Query(None, description="Single Size | Multi Size"),

    # ── Store filter ───────────────────────────────────────────────────────────
    primary_store:  Optional[str] = Query(None),

    # ── Retention filters ──────────────────────────────────────────────────────
    retained_30d:   Optional[bool] = Query(None),
    retained_90d:   Optional[bool] = Query(None),

    db: Session = Depends(get_db),
):
    """
    Self-serve export — any combination of filters → CSV download.
    All filter columns are indexed. No LIKE. No runtime joins.
    Max 100,000 rows per export.
    """
    filters = ["1=1"]
    params  = {}

    # Build WHERE clause dynamically — equality only (indexed)
    filter_map = {
        "rfm_segment"    : rfm_segment,
        "churn_risk"     : churn_risk,
        "return_risk"    : return_risk,
        "customer_type"  : customer_type,
        "frequency_bucket": frequency_bucket,
        "recency_bucket" : recency_bucket,
        "platform"       : platform,
        "channel_journey": channel_journey,
        "migration_type" : migration_type,
        "consumer_zone"  : consumer_zone,
        "consumer_state" : consumer_state,
        "consumer_city"  : consumer_city,
        "consumer_pincode": consumer_pincode,
        "top_category"   : top_category,
        "category_label" : category_label,
        "top_brand"      : top_brand,
        "size_behaviour" : size_behaviour,
        "primary_store"  : primary_store,
    }

    for col, val in filter_map.items():
        if val is not None:
            filters.append(f"{col} = :{col}")
            params[col] = val

    if retained_30d is not None:
        filters.append("retained_30d = :retained_30d")
        params["retained_30d"] = retained_30d

    if retained_90d is not None:
        filters.append("retained_90d = :retained_90d")
        params["retained_90d"] = retained_90d

    where = " AND ".join(filters)

    rows = db.execute(text(f"""
        SELECT {EXPORT_COLUMNS}
        FROM public.cust_master_profile
        WHERE {where}
        ORDER BY total_lifetime_spend DESC
        LIMIT 100000
    """), params).mappings().all()

    if not rows:
        return {"message": "No customers match the selected filters", "count": 0}

    # ── Stream CSV response ───────────────────────────────────────────────────
    def generate():
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=rows[0].keys())
        writer.writeheader()
        for row in rows:
            writer.writerow(dict(row))
        buffer.seek(0)
        yield buffer.read()

    filename = "customer_export.csv"
    return StreamingResponse(
        generate(),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/count")
def get_export_count(
    rfm_segment:    Optional[str] = Query(None),
    churn_risk:     Optional[str] = Query(None),
    customer_type:  Optional[str] = Query(None),
    consumer_zone:  Optional[str] = Query(None),
    consumer_state: Optional[str] = Query(None),
    top_category:   Optional[str] = Query(None),
    category_label: Optional[str] = Query(None),
    primary_store:  Optional[str] = Query(None),
    migration_type: Optional[str] = Query(None),
    size_behaviour: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """
    Preview count before download.
    Same filter logic as /export/csv but returns count only.
    Call this first so the user sees 'X customers match' before hitting export.
    """
    filters = ["1=1"]
    params  = {}

    filter_map = {
        "rfm_segment"   : rfm_segment,
        "churn_risk"    : churn_risk,
        "customer_type" : customer_type,
        "consumer_zone" : consumer_zone,
        "consumer_state": consumer_state,
        "top_category"  : top_category,
        "category_label": category_label,
        "primary_store" : primary_store,
        "migration_type": migration_type,
        "size_behaviour": size_behaviour,
    }

    for col, val in filter_map.items():
        if val is not None:
            filters.append(f"{col} = :{col}")
            params[col] = val

    where = " AND ".join(filters)

    row = db.execute(text(f"""
        SELECT COUNT(*) AS count
        FROM public.cust_master_profile
        WHERE {where}
    """), params).mappings().first()

    return {"count": row["count"], "filters": params}
