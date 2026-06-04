# api/routers/customer.py
# Primary key = combo (only truly unique column — email+phone concatenated)

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from database.connection import get_db

router = APIRouter()


@router.get("/search")
def search_customer(
    q    : str = Query(..., min_length=2, description="Email, phone, or name"),
    limit: int = Query(50, description="Max results to return"),
    db: Session = Depends(get_db),
):
    """
    Search by email (exact), phone (exact), or name (contains).
    Returns total_count — how many total matches exist,
    and top `limit` customers sorted by lifetime spend.
    """
    # Total count of all matches
    count_row = db.execute(text("""
        SELECT COUNT(*) AS total
        FROM public.cust_master_profile
        WHERE email = :q
           OR phone = :q
           OR LOWER(consumer_name) LIKE LOWER(:name_contains)
    """), {"q": q, "name_contains": "%" + q + "%"}).mappings().first()

    total_count = count_row["total"] if count_row else 0

    # Top results sorted by spend
    results = db.execute(text("""
        SELECT
            combo, unq_id, consumer_name, email, phone,
            consumer_city, consumer_state, consumer_zone,
            platform, channel_journey, customer_type,
            rfm_segment, churn_risk,
            total_lifetime_spend, total_lifetime_orders,
            total_ebo_spend, total_online_spend,
            ebo_aov, online_aov,
            total_ebo_bills, total_online_orders,
            top_category, top_brand, size_behaviour,
            primary_store, migration_type,
            days_since_last_purchase,
            first_seen_date, last_updated_date
        FROM public.cust_master_profile
        WHERE email = :q
           OR phone = :q
           OR LOWER(consumer_name) LIKE LOWER(:name_contains)
        ORDER BY total_lifetime_spend DESC NULLS LAST
        LIMIT :limit
    """), {"q": q, "name_contains": "%" + q + "%", "limit": limit}).mappings().all()

    return {
        "query"      : q,
        "total_count": total_count,
        "shown"      : len(results),
        "customers"  : [dict(r) for r in results],
    }


@router.get("/search/export-csv")
def export_search_csv(
    q : str = Query(..., min_length=2),
    db: Session = Depends(get_db),
):
    """Export ALL customers matching search query as CSV."""
    import io, csv
    from fastapi.responses import StreamingResponse

    rows = db.execute(text("""
        SELECT
            combo, unq_id, consumer_name, email, phone,
            consumer_city, consumer_state, consumer_zone,
            consumer_pincode, platform, channel_journey,
            customer_type, rfm_segment, churn_risk, return_risk,
            total_lifetime_spend, total_lifetime_orders,
            total_ebo_spend, total_online_spend,
            ebo_aov, online_aov, total_ebo_bills, total_online_orders,
            top_category, top_brand, size_behaviour, size_combination,
            primary_store, migration_type,
            days_since_last_purchase, first_seen_date, last_updated_date
        FROM public.cust_master_profile
        WHERE email = :q
           OR phone = :q
           OR LOWER(consumer_name) LIKE LOWER(:name_contains)
        ORDER BY total_lifetime_spend DESC NULLS LAST
        LIMIT 100000
    """), {"q": q, "name_contains": "%" + q + "%"}).mappings().all()

    def generate():
        if not rows:
            yield "No results\n"; return
        buf    = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        buf.seek(0); yield buf.read(); buf.truncate(0); buf.seek(0)
        for row in rows:
            writer.writerow({k:(str(v) if v is not None else "") for k,v in dict(row).items()})
            buf.seek(0); yield buf.read(); buf.truncate(0); buf.seek(0)

    safe_q   = q.replace(' ', '_')[:30]
    filename = f"search_{safe_q}.csv"
    return StreamingResponse(
        generate(),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/by-combo")
def get_customer_by_combo(
    combo: str = Query(..., description="Customer combo key (email-phone)"),
    db: Session = Depends(get_db),
):
    """Full Customer 360 profile by combo (primary key)."""
    row = db.execute(text("""
        SELECT *
        FROM public.cust_master_profile
        WHERE combo = :combo
        LIMIT 1
    """), {"combo": combo}).mappings().first()

    if not row:
        raise HTTPException(status_code=404, detail="Customer not found")

    return dict(row)


@router.get("/by-unq-id/{unq_id}")
def get_customer_by_unq_id(unq_id: int, db: Session = Depends(get_db)):
    """Lookup by unq_id — not unique, returns highest-spend match."""
    row = db.execute(text("""
        SELECT *
        FROM public.cust_master_profile
        WHERE unq_id = :unq_id
        ORDER BY total_lifetime_spend DESC NULLS LAST
        LIMIT 1
    """), {"unq_id": unq_id}).mappings().first()

    if not row:
        raise HTTPException(status_code=404, detail="Customer not found")

    return dict(row)


@router.get("/timeline")
def get_customer_timeline(
    combo   : str = Query(..., description="Customer combo key"),
    channel : str = Query("all", description="all | ebo | shopify"),
    db      : Session = Depends(get_db),
):
    """
    Transaction timeline with full product details.
    Joins item_master for itemNo, category, size, season, imageUrl.
    EBO join: barcode = item_master.ean
    Shopify join: client_sku_id_ean = item_master.shopifySKU
    """
    exists = db.execute(text("""
        SELECT combo FROM public.cust_master_profile
        WHERE combo = :combo LIMIT 1
    """), {"combo": combo}).mappings().first()

    if not exists:
        raise HTTPException(status_code=404, detail="Customer not found")

    timeline = []

    if channel in ("all", "ebo"):
        ebo_rows = db.execute(text("""
            SELECT
                e.invoice_date                          AS txn_date,
                'EBO'                                   AS channel,
                e.invoice_associate_name                AS store_or_platform,
                e.order_amount,
                e.nob                                   AS bills,
                e.nsq                                   AS skus,
                e.rt_qty                                AS return_qty,
                e.barcode                               AS sku_code,

                -- item_master details
                im."itemNo"                               AS item_no,
                im."itemCategoryCode"                     AS category,
                im."subCategory"                          AS sub_category,
                im."sizeNew"                             AS size,
                im."seasonNew"                            AS season,
                im.brand,
                im."designType"                           AS design_type,
                im.occassion                            AS occasion,

                -- Image — use thumbnail size (small)
                CASE
                    WHEN im."imageUrl" IS NOT NULL AND im."imageUrl" <> ''
                    THEN im."imageUrl"
                    ELSE NULL
                END                                     AS image_url

            FROM public.cust_ebo_salescombo_view e
            LEFT JOIN public.item_master im
                   ON im.ean = e.barcode
            WHERE LTRIM(TRIM(e.combo), '-!''`~+') = LTRIM(TRIM(:combo), '-!''`~+')
            ORDER BY e.invoice_date DESC
            LIMIT 200
        """), {"combo": combo}).mappings().all()
        timeline.extend([dict(r) for r in ebo_rows])

    if channel in ("all", "shopify"):
        shp_rows = db.execute(text("""
            SELECT
                s.channel_order_date                    AS txn_date,
                'Shopify'                               AS channel,
                'Shopify Online'                        AS store_or_platform,
                s.order_amount,
                s.order_count                           AS bills,
                s.order_qty                             AS skus,
                s.cancelled_qty                         AS return_qty,
                s.client_sku_id_ean                     AS sku_code,

                -- item_master details
                im."itemNo"                               AS item_no,
                im."itemCategoryCode"                     AS category,
                im."subCategory"                          AS sub_category,
                im."sizeNew"                             AS size,
                im."seasonNew"                            AS season,
                im.brand,
                im."designType"                           AS design_type,
                im.occassion                            AS occasion,

                -- Image — use thumbnail size (small)
                CASE
                    WHEN im."imageUrl" IS NOT NULL AND im."imageUrl" <> ''
                    THEN im."imageUrl"
                    ELSE NULL
                END                                     AS image_url

            FROM public.cust_osdcombo_view s
            LEFT JOIN public.item_master im
                   ON im."itemNo" = s.client_sku_id_ean
            WHERE LTRIM(TRIM(s.combo), '-!''`~+') = LTRIM(TRIM(:combo), '-!''`~+')
            ORDER BY s.channel_order_date DESC
            LIMIT 200
        """), {"combo": combo}).mappings().all()
        timeline.extend([dict(r) for r in shp_rows])

    timeline.sort(key=lambda x: str(x.get("txn_date") or ""), reverse=True)

    # ── Returns detail — join cust_rtcombo_view with item_master ─────────────
    returns = []
    returns_rows = db.execute(text("""
        SELECT
            r.channel_order_date                    AS order_date,
            r.return_order_processed_time           AS return_date,
            r.client_sku_id_ean                     AS sku_code,
            r.cr_qty                                AS customer_return_qty,
            r.rto_qty                               AS rto_qty,
            r.rt_qty                                AS total_return_qty,
            r.pass_qty                              AS qc_pass_qty,
            r.fail_qty                              AS qc_fail_qty,
            NULL::TEXT                              AS qc_status,

            -- item_master details
            im."itemNo"                               AS item_no,
            im."itemCategoryCode"                     AS category,
            im."subCategory"                          AS sub_category,
            im."sizeNew"                             AS size,
            im."seasonNew"                            AS season,
            im.brand,
            im."designType"                           AS design_type,

            -- Image
            CASE
                WHEN im."imageUrl" IS NOT NULL AND im."imageUrl" <> ''
                THEN im."imageUrl"
                ELSE NULL
            END                                     AS image_url

        FROM public.cust_rtcombo_view r
        LEFT JOIN public.item_master im
               ON im."itemNo" = r.client_sku_id_ean
            OR im.ean        = r.client_sku_id_ean
        WHERE LTRIM(TRIM(r.combo), '-!''`~+') = LTRIM(TRIM(:combo), '-!''`~+')
          AND r.rt_qty > 0
        ORDER BY r.return_order_processed_time DESC NULLS LAST
        LIMIT 200
    """), {"combo": combo}).mappings().all()
    returns.extend([dict(r) for r in returns_rows])

    return {
        "combo"             : combo,
        "total_transactions": len(timeline),
        "timeline"          : timeline,
        "total_returns"     : len(returns),
        "returns"           : returns,
    }