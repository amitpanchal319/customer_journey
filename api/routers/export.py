# api/routers/export.py

import io
import csv
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Optional
from database.connection import get_db

router = APIRouter()

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
    primary_store,
    retained_30d, retained_60d, retained_90d,
    first_seen_date, last_updated_date, days_since_last_purchase
"""


def _build_where(filter_map: dict):
    filters = ["1=1"]
    params  = {}
    for col, val in filter_map.items():
        if val is not None:
            filters.append(f"{col} = :{col}")
            params[col] = val
    return " AND ".join(filters), params


def _add_month_filter(where: str, params: dict, months: Optional[str]):
    """
    Add month filter using raw transaction views.
    months = comma-separated YYYY-MM strings e.g. "2026-05,2026-04"
    Uses invoice_date + channel_order_date — works for all historical months.
    """
    if not months:
        return where, params

    month_list = [m.strip() for m in months.split(',') if m.strip()]
    if not month_list:
        return where, params

    # Build IN clause for both EBO and Shopify
    placeholders = ', '.join([
        f"DATE_TRUNC('month', CAST(:month_{i} || '-01' AS DATE))"
        for i in range(len(month_list))
    ])

    where += f"""
        AND public.fn_clean_combo(combo) IN (
            SELECT DISTINCT public.fn_clean_combo(combo)
            FROM public.cust_ebo_salescombo_view
            WHERE DATE_TRUNC('month', invoice_date) IN ({placeholders})
              AND combo IS NOT NULL
            UNION
            SELECT DISTINCT public.fn_clean_combo(combo)
            FROM public.cust_osdcombo_view
            WHERE DATE_TRUNC('month', channel_order_date) IN ({placeholders})
              AND combo IS NOT NULL
              AND combo NOT LIKE '%myshopify%'
        )"""

    for i, m in enumerate(month_list):
        params[f'month_{i}'] = m

    return where, params


@router.get("/count")
def get_export_count(
    rfm_segment:      Optional[str]  = Query(None),
    churn_risk:       Optional[str]  = Query(None),
    customer_type:    Optional[str]  = Query(None),
    consumer_zone:    Optional[str]  = Query(None),
    consumer_state:   Optional[str]  = Query(None),
    top_category:     Optional[str]  = Query(None),
    category_label:   Optional[str]  = Query(None),
    primary_store:    Optional[str]  = Query(None),
    migration_type:   Optional[str]  = Query(None),
    size_behaviour:   Optional[str]  = Query(None),
    months:           Optional[str]  = Query(None, description="Comma-separated YYYY-MM e.g. 2026-05,2026-04"),
    db: Session = Depends(get_db),
):
    """Preview count before download."""
    where, params = _build_where({
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
    })
    where, params = _add_month_filter(where, params, months)

    row = db.execute(text(f"""
        SELECT COUNT(*) AS count
        FROM public.cust_master_profile
        WHERE {where}
    """), params).mappings().first()

    return {
        "count"  : row["count"],
        "filters": {k: v for k, v in params.items() if not k.startswith('month_')},
        "months" : months,
    }


@router.get("/csv")
def export_csv(
    rfm_segment:      Optional[str]  = Query(None),
    churn_risk:       Optional[str]  = Query(None),
    return_risk:      Optional[str]  = Query(None),
    customer_type:    Optional[str]  = Query(None),
    frequency_bucket: Optional[str]  = Query(None),
    recency_bucket:   Optional[str]  = Query(None),
    platform:         Optional[str]  = Query(None),
    channel_journey:  Optional[str]  = Query(None),
    migration_type:   Optional[str]  = Query(None),
    consumer_zone:    Optional[str]  = Query(None),
    consumer_state:   Optional[str]  = Query(None),
    consumer_city:    Optional[str]  = Query(None),
    consumer_pincode: Optional[str]  = Query(None),
    top_category:     Optional[str]  = Query(None),
    category_label:   Optional[str]  = Query(None),
    top_brand:        Optional[str]  = Query(None),
    size_behaviour:   Optional[str]  = Query(None),
    primary_store:    Optional[str]  = Query(None),
    retained_30d:     Optional[bool] = Query(None),
    retained_90d:     Optional[bool] = Query(None),
    months:           Optional[str]  = Query(None, description="Comma-separated YYYY-MM e.g. 2026-05,2026-04"),
    db: Session = Depends(get_db),
):
    """Self-serve export — any filter combination → CSV download. Max 100,000 rows."""
    where, params = _build_where({
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
    })

    if retained_30d is not None:
        where += " AND retained_30d = :retained_30d"
        params["retained_30d"] = retained_30d
    if retained_90d is not None:
        where += " AND retained_90d = :retained_90d"
        params["retained_90d"] = retained_90d

    where, params = _add_month_filter(where, params, months)

    rows = db.execute(text(f"""
        SELECT {EXPORT_COLUMNS}
        FROM public.cust_master_profile
        WHERE {where}
        ORDER BY total_lifetime_spend DESC
        LIMIT 100000
    """), params).mappings().all()

    if not rows:
        return {"message": "No customers match the selected filters", "count": 0}

    # Build filename with active filters
    month_str = f"_months_{months.replace(',','_')}" if months else ""
    filename  = f"customer_export{month_str}.csv"

    def generate():
        buf    = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        buf.seek(0); yield buf.read(); buf.truncate(0); buf.seek(0)
        for row in rows:
            writer.writerow({k: (str(v) if v is not None else "") for k, v in dict(row).items()})
            buf.seek(0); yield buf.read(); buf.truncate(0); buf.seek(0)

    return StreamingResponse(
        generate(),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )