# api/routers/stores.py
# Enhanced store intelligence with MoM, RFM breakdown,
# Cannot Lose alerts, category/size, migration, multi-store customers

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import text
from database.connection import get_db
from typing import Optional

router = APIRouter()


# ── 1. Store summary (all stores) ────────────────────────────────────────────
@router.get("/summary")
def get_stores_summary(db: Session = Depends(get_db)):
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
            loyal_count,
            at_risk_count,
            high_churn_count,
            primary_customer_zone
        FROM public.store_summary_mv
        ORDER BY total_customers DESC
    """)).mappings().all()
    return [dict(r) for r in rows]


# ── 2. Store detail — full profile ───────────────────────────────────────────
@router.get("/detail/{store_name}")
def get_store_detail(store_name: str, db: Session = Depends(get_db)):
    """Full store profile — summary + RFM + categories + cannot lose alerts."""

    store = db.execute(text("""
        SELECT * FROM public.store_summary_mv
        WHERE store_name = :store_name LIMIT 1
    """), {"store_name": store_name}).mappings().first()

    if not store:
        raise HTTPException(status_code=404, detail="Store not found")

    # RFM segment breakdown for this store
    rfm = db.execute(text("""
        SELECT
            rfm_segment,
            COUNT(*)                                        AS customers,
            ROUND(AVG(total_lifetime_spend)::NUMERIC, 0)   AS avg_ltv,
            ROUND(COUNT(*)::NUMERIC /
                SUM(COUNT(*)) OVER() * 100, 1)             AS pct
        FROM public.cust_master_profile
        WHERE primary_store = :store_name
        GROUP BY rfm_segment
        ORDER BY customers DESC
    """), {"store_name": store_name}).mappings().all()

    # Top categories at this store (from EBO transactions)
    categories = db.execute(text("""
        SELECT
            UPPER(TRIM(im."itemCategoryCode"))              AS category,
            COUNT(DISTINCT public.fn_clean_combo(e.combo)) AS customers,
            SUM(e.order_amount)                            AS revenue,
            ROUND(AVG(e.order_amount)::NUMERIC, 0)         AS avg_bill
        FROM public.cust_ebo_salescombo_view e
        INNER JOIN public.item_master im ON im.ean = e.barcode
        WHERE TRIM(e.invoice_associate_name) = :store_name
          AND im."itemCategoryCode" IS NOT NULL
        GROUP BY UPPER(TRIM(im."itemCategoryCode"))
        ORDER BY customers DESC
        LIMIT 8
    """), {"store_name": store_name}).mappings().all()

    # Top sizes at this store
    sizes = db.execute(text("""
        SELECT
            TRIM(im."sizeNew")                              AS size,
            COUNT(*)                                        AS qty_sold,
            COUNT(DISTINCT public.fn_clean_combo(e.combo)) AS customers
        FROM public.cust_ebo_salescombo_view e
        INNER JOIN public.item_master im ON im.ean = e.barcode
        WHERE TRIM(e.invoice_associate_name) = :store_name
          AND im."sizeNew" IS NOT NULL
          AND im."sizeNew" <> ''
        GROUP BY TRIM(im."sizeNew")
        ORDER BY qty_sold DESC
        LIMIT 8
    """), {"store_name": store_name}).mappings().all()

    # Cannot Lose alerts — high value, 180+ days silent
    cannot_lose = db.execute(text("""
        SELECT
            consumer_name,
            email,
            phone,
            consumer_city,
            consumer_zone,
            total_lifetime_spend,
            total_ebo_bills,
            ebo_days_since_last,
            top_category,
            rfm_segment
        FROM public.cust_master_profile
        WHERE primary_store = :store_name
          AND rfm_segment IN ('Cannot Lose', 'At Risk', 'Champion')
          AND ebo_days_since_last > 90
        ORDER BY total_lifetime_spend DESC NULLS LAST
        LIMIT 20
    """), {"store_name": store_name}).mappings().all()

    # Online migration detail
    migration = db.execute(text("""
        SELECT
            migration_type,
            COUNT(*)                                        AS customers,
            ROUND(AVG(total_lifetime_spend)::NUMERIC, 0)   AS avg_ltv
        FROM public.cust_master_profile
        WHERE primary_store = :store_name
        GROUP BY migration_type
        ORDER BY customers DESC
    """), {"store_name": store_name}).mappings().all()

    # Top customers
    customers = db.execute(text("""
        SELECT
            consumer_name, email, phone,
            consumer_city, consumer_zone,
            rfm_segment, churn_risk, customer_type,
            total_ebo_bills, total_ebo_spend, ebo_aov,
            total_lifetime_spend, last_updated_date,
            top_category, migration_type
        FROM public.cust_master_profile
        WHERE primary_store = :store_name
        ORDER BY total_lifetime_spend DESC NULLS LAST
        LIMIT 200
    """), {"store_name": store_name}).mappings().all()

    return {
        "store"        : dict(store),
        "rfm"          : [dict(r) for r in rfm],
        "categories"   : [dict(r) for r in categories],
        "sizes"        : [dict(r) for r in sizes],
        "cannot_lose"  : [dict(r) for r in cannot_lose],
        "migration"    : [dict(r) for r in migration],
        "customers"    : [dict(r) for r in customers],
    }


# ── 3. Month-on-month store performance ──────────────────────────────────────
@router.get("/mom/{store_name}")
def get_store_mom(
    store_name : str,
    months     : Optional[str] = Query("12", description="Number of months or YYYY-MM for specific month"),
    db         : Session = Depends(get_db)
):
    """
    Month-on-month footfall, revenue, new vs repeat for a store.
    months param: either a number (e.g. 12) or a YYYY-MM string (e.g. 2026-05).
    If YYYY-MM: returns only that specific month's data.
    If number: returns last N months.
    """
    # Detect if months is a specific month (YYYY-MM) or a range number
    import re as _re
    if months and _re.match(r'^[0-9]{4}-[0-9]{2}$', months):
        # Specific month selected
        date_filter = """
            AND DATE_TRUNC('month', e.invoice_date)
              = DATE_TRUNC('month', CAST(:month_date AS DATE))"""
        params = {"store_name": store_name, "month_date": months + "-01"}
    else:
        # Range — last N months
        n = int(months) if months and months.isdigit() else 12
        date_filter = """
            AND e.invoice_date >= CURRENT_DATE - (:months || ' months')::INTERVAL"""
        params = {"store_name": store_name, "months": n}

    rows = db.execute(text(f"""
        SELECT
            DATE_TRUNC('month', e.invoice_date)::DATE       AS month,
            TO_CHAR(DATE_TRUNC('month', e.invoice_date),
                'Mon YYYY')                                 AS month_label,
            COUNT(DISTINCT public.fn_clean_combo(e.combo))  AS unique_customers,
            COUNT(*)                                        AS total_bills,
            ROUND(SUM(e.order_amount)::NUMERIC, 0)          AS revenue,
            ROUND(AVG(e.order_amount)::NUMERIC, 0)          AS avg_bill,
            COUNT(DISTINCT public.fn_clean_combo(e.combo))
                FILTER (WHERE mp.customer_type = 'New')     AS new_customers,
            COUNT(DISTINCT public.fn_clean_combo(e.combo))
                FILTER (WHERE mp.customer_type = 'Repeat')  AS repeat_customers
        FROM public.cust_ebo_salescombo_view e
        LEFT JOIN public.cust_master_profile mp
               ON public.fn_clean_combo(mp.combo)
                = public.fn_clean_combo(e.combo)
        WHERE TRIM(e.invoice_associate_name) = :store_name
          {date_filter}
        GROUP BY DATE_TRUNC('month', e.invoice_date)
        ORDER BY month ASC
    """), params).mappings().all()
    return [dict(r) for r in rows]


# ── 4. Multi-store customers — zone wise ─────────────────────────────────────
@router.get("/multi-store-customers")
def get_multi_store_customers(
    zone: Optional[str] = None,
    min_stores: int = Query(2, description="Min number of stores visited"),
    limit: int = Query(500),
    db: Session = Depends(get_db)
):
    """
    Customers who visited multiple EBO stores.
    Zone-wise breakdown available.
    These are your most engaged offline customers.
    """
    zone_filter = "AND mp.consumer_zone = :zone" if zone else ""
    params = {"min_stores": min_stores, "limit": limit}
    if zone:
        params["zone"] = zone

    rows = db.execute(text(f"""
        WITH store_visits AS (
            SELECT
                public.fn_clean_combo(e.combo)              AS combo,
                COUNT(DISTINCT TRIM(e.invoice_associate_name)) AS stores_visited,
                STRING_AGG(DISTINCT TRIM(e.invoice_associate_name),
                    ', ' ORDER BY TRIM(e.invoice_associate_name)) AS stores_list,
                COUNT(*)                                     AS total_bills,
                ROUND(SUM(e.order_amount)::NUMERIC, 0)       AS total_ebo_spend
            FROM public.cust_ebo_salescombo_view e
            WHERE e.invoice_associate_name IS NOT NULL
              AND e.combo IS NOT NULL
            GROUP BY public.fn_clean_combo(e.combo)
            HAVING COUNT(DISTINCT TRIM(e.invoice_associate_name)) >= :min_stores
        )
        SELECT
            mp.consumer_name,
            mp.email,
            mp.phone,
            mp.consumer_city,
            mp.consumer_state,
            mp.consumer_zone,
            mp.consumer_pincode,
            sv.stores_visited,
            sv.stores_list,
            sv.total_bills,
            sv.total_ebo_spend,
            mp.primary_store,
            mp.rfm_segment,
            mp.churn_risk,
            mp.top_category,
            mp.total_lifetime_spend,
            mp.total_online_spend,
            mp.migration_type,
            mp.channel_journey
        FROM store_visits sv
        INNER JOIN public.cust_master_profile mp
                ON public.fn_clean_combo(mp.combo) = sv.combo
        WHERE 1=1 {zone_filter}
        ORDER BY sv.stores_visited DESC, sv.total_ebo_spend DESC
        LIMIT :limit
    """), params).mappings().all()

    # Zone summary
    zone_summary = db.execute(text(f"""
        WITH store_visits AS (
            SELECT
                public.fn_clean_combo(e.combo) AS combo,
                COUNT(DISTINCT TRIM(e.invoice_associate_name)) AS stores_visited
            FROM public.cust_ebo_salescombo_view e
            WHERE e.invoice_associate_name IS NOT NULL
              AND e.combo IS NOT NULL
            GROUP BY public.fn_clean_combo(e.combo)
            HAVING COUNT(DISTINCT TRIM(e.invoice_associate_name)) >= :min_stores
        )
        SELECT
            COALESCE(mp.consumer_zone, 'Unknown')           AS zone,
            COUNT(*)                                        AS multi_store_customers,
            ROUND(AVG(sv.stores_visited)::NUMERIC, 1)       AS avg_stores_visited,
            ROUND(AVG(mp.total_lifetime_spend)::NUMERIC, 0) AS avg_ltv
        FROM store_visits sv
        INNER JOIN public.cust_master_profile mp
                ON public.fn_clean_combo(mp.combo) = sv.combo
        GROUP BY mp.consumer_zone
        ORDER BY multi_store_customers DESC
    """), {"min_stores": min_stores}).mappings().all()

    return {
        "total"        : len(rows),
        "zone_filter"  : zone,
        "min_stores"   : min_stores,
        "zone_summary" : [dict(r) for r in zone_summary],
        "customers"    : [dict(r) for r in rows],
    }


# ── 5. Store comparison ───────────────────────────────────────────────────────
@router.get("/store-compare")
def compare_stores(
    stores: str = Query(..., description="Comma-separated store names"),
    db: Session = Depends(get_db)
):
    """Compare 2-3 stores side by side."""
    store_list = [s.strip() for s in stores.split(",")][:3]

    if not store_list:
        return []

    # Build IN clause manually — SQLAlchemy ANY() has issues with lists
    placeholders = ", ".join([f":store_{i}" for i in range(len(store_list))])
    params = {f"store_{i}": name for i, name in enumerate(store_list)}

    rows = db.execute(text(f"""
        SELECT
            store_name,
            total_customers,
            repeat_customer_pct,
            avg_customer_ltv,
            retention_30d_pct,
            retention_90d_pct,
            champion_count,
            high_churn_count,
            migrated_to_online,
            top_category_at_store,
            primary_customer_zone
        FROM public.store_summary_mv
        WHERE store_name IN ({placeholders})
        ORDER BY total_customers DESC
    """), params).mappings().all()

    return [dict(r) for r in rows]


# ── 6. Export store customers CSV ────────────────────────────────────────────
@router.get("/export-csv/{store_name}")
def export_store_csv(
    store_name: str,
    segment: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Export store customers as CSV. Optionally filter by RFM segment."""
    import io, csv

    seg_filter = "AND rfm_segment = :segment" if segment else ""
    params     = {"store_name": store_name}
    if segment:
        params["segment"] = segment

    rows = db.execute(text(f"""
        SELECT
            consumer_name, email, phone,
            consumer_city, consumer_state, consumer_zone, consumer_pincode,
            rfm_segment, churn_risk, customer_type,
            total_ebo_bills, total_ebo_spend, ebo_aov, ebo_days_since_last,
            total_online_orders, total_online_spend,
            total_lifetime_spend, top_category, top_brand,
            migration_type, channel_journey, size_behaviour,
            first_seen_date, last_updated_date
        FROM public.cust_master_profile
        WHERE primary_store = :store_name {seg_filter}
        ORDER BY total_lifetime_spend DESC NULLS LAST
        LIMIT 100000
    """), params).mappings().all()

    def generate():
        if not rows:
            yield "No data\n"; return
        buf    = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        buf.seek(0); yield buf.read(); buf.truncate(0); buf.seek(0)
        for row in rows:
            writer.writerow({k:(str(v) if v is not None else "") for k,v in row.items()})
            buf.seek(0); yield buf.read(); buf.truncate(0); buf.seek(0)

    seg_str  = f"_{segment.replace(' ','_')}" if segment else ""
    filename = f"store_{store_name.replace(' ','_')}{seg_str}.csv"
    return StreamingResponse(
        generate(),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# ── Per-KPI-card export ───────────────────────────────────────────────────────
# Customers who transacted at the store (same grain as store_summary_mv cards),
# filtered by the metric behind each KPI card. Counts match the card numbers.
_STORE_METRIC_FILTER = {
    "all"          : "TRUE",                              # Total Customers / Avg LTV
    "repeat"       : "sc.visit_days >= 2",                # Repeat Rate
    "retained_30d" : "mp.retained_30d = TRUE",            # Retention 30d
    "went_online"  : "mp.migration_type = 'EBO First'",   # Went Online
    "high_churn"   : "mp.churn_risk = 'High'",            # High Churn
}


@router.get("/export-metric/{store_name}")
def export_store_metric_csv(
    store_name: str,
    metric: str = Query("all", description="all | repeat | retained_30d | went_online | high_churn"),
    db: Session = Depends(get_db),
):
    """Download the customers behind a specific store KPI card as CSV."""
    import io, csv

    where = _STORE_METRIC_FILTER.get(metric)
    if where is None:
        raise HTTPException(status_code=400, detail=f"Unknown metric: {metric}")

    rows = db.execute(text(f"""
        WITH sc AS (
            SELECT public.fn_clean_combo(combo)        AS combo,
                   COUNT(DISTINCT invoice_date)        AS visit_days,
                   SUM(nob)                            AS bills_at_store,
                   SUM(order_amount)                   AS spend_at_store
            FROM public.cust_ebo_salescombo_view
            WHERE TRIM(invoice_associate_name) = :store_name
              AND combo IS NOT NULL
            GROUP BY 1
        )
        SELECT * FROM (
            SELECT DISTINCT ON (sc.combo)
                mp.consumer_name                       AS name,
                mp.email,
                mp.phone,
                mp.consumer_city                       AS city,
                mp.consumer_zone                       AS zone,
                sc.visit_days                          AS store_visits,
                sc.bills_at_store                      AS store_bills,
                ROUND(sc.spend_at_store::NUMERIC, 0)   AS store_spend,
                mp.total_lifetime_spend,
                mp.customer_type,
                mp.rfm_segment,
                mp.churn_risk,
                mp.migration_type,
                mp.retained_30d,
                mp.top_category
            FROM sc
            JOIN public.cust_master_profile mp
              ON public.fn_clean_combo(mp.combo) = sc.combo
             AND mp.email IS NOT NULL
            WHERE {where}
            ORDER BY sc.combo, mp.total_lifetime_spend DESC NULLS LAST
        ) t
        ORDER BY total_lifetime_spend DESC NULLS LAST
        LIMIT 100000
    """), {"store_name": store_name}).mappings().all()

    def generate():
        if not rows:
            yield "No data\n"; return
        buf    = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        buf.seek(0); yield buf.read(); buf.truncate(0); buf.seek(0)
        for row in rows:
            writer.writerow({k: (str(v) if v is not None else "") for k, v in row.items()})
            buf.seek(0); yield buf.read(); buf.truncate(0); buf.seek(0)

    filename = f"store_{store_name.replace(' ','_')}_{metric}.csv"
    return StreamingResponse(
        generate(),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )



# ── Multi-store CSV export ────────────────────────────────────────────────────
@router.get("/multi-store-customers/export-csv")
def export_multi_store_csv(
    zone       : Optional[str] = None,
    min_stores : int = Query(2),
    db         : Session = Depends(get_db)
):
    """Export multi-store customers as CSV."""
    import io, csv

    result = get_multi_store_customers(zone=zone, min_stores=min_stores, limit=100000, db=db)
    rows   = result["customers"]

    def generate():
        if not rows:
            yield "No data\n"; return
        buf    = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        buf.seek(0); yield buf.read(); buf.truncate(0); buf.seek(0)
        for row in rows:
            writer.writerow({k:(str(v) if v is not None else "") for k,v in row.items()})
            buf.seek(0); yield buf.read(); buf.truncate(0); buf.seek(0)

    zone_str = f"_{zone}" if zone else ""
    filename = f"multi_store_customers{zone_str}.csv"
    return StreamingResponse(
        generate(),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )