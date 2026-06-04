# api/routers/agent.py
# ----------------------------------------------------------------
# Text-to-SQL Agent
# Uses Groq LLaMA with full schema context for high accuracy
# Endpoints:
#   GET  /api/agent/schema          — returns DB schema for frontend
#   POST /api/agent/query           — natural language → SQL → results
#   POST /api/agent/execute         — run raw SQL directly
# ----------------------------------------------------------------

import os
import re
import json
import requests
import psycopg2
import psycopg2.extras
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import text
from pydantic import BaseModel
from typing import Optional
from database.connection import get_db
from dotenv import load_dotenv

load_dotenv()

router       = APIRouter()
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL   = "llama-3.3-70b-versatile"

PG = {
    "host"    : os.getenv("PG_HOST",     "10.150.0.5"),
    "port"    : int(os.getenv("PG_PORT", "5432")),
    "dbname"  : os.getenv("PG_DATABASE", "Unicorn"),
    "user"    : os.getenv("PG_USER",     "Amit"),
    "password": os.getenv("PG_PASSWORD", "Amit@23200"),
}

# ── Full schema context — fed to Groq for accuracy ────────────────────────────
DB_SCHEMA = """
DATABASE: Unicorn (PostgreSQL)
Brand: Libas — Indian ethnic fashion (Shopify=Online, EBO=Offline stores)
All monetary values in Indian Rupees (₹). City/Zone values are UPPERCASE.

== PRIMARY TABLE (use for most queries) ==
TABLE: public.cust_master_profile  [2.24M rows — one row per customer]

EXACT COLUMN NAMES (use these exactly, no variations):
  unq_id                  BIGINT       -- customer ID (not unique, has duplicates)
  combo                   TEXT         -- PRIMARY KEY: email-phone concat (unique)
  email                   TEXT
  phone                   TEXT
  platform                TEXT         -- 'Shopify' | 'EBO' | 'Both'
  in_ebo                  BOOLEAN      -- has EBO purchases
  in_shopify              BOOLEAN      -- has Shopify purchases
  first_seen_date         DATE
  last_updated_date       DATE
  consumer_name           TEXT
  consumer_pincode        TEXT
  consumer_city           TEXT         -- UPPERCASE e.g. 'DELHI', 'MUMBAI'
  consumer_state          TEXT         -- UPPERCASE
  consumer_zone           TEXT         -- 'NORTH'|'SOUTH'|'EAST'|'WEST'|'CENTRAL'
  store_city              TEXT

  -- EBO (Offline store) metrics
  total_ebo_bills         NUMERIC      -- number of EBO invoices
  total_ebo_skus          NUMERIC      -- total SKUs purchased offline
  ebo_visit_days          BIGINT       -- distinct visit days
  total_ebo_spend         REAL         -- total offline spend
  ebo_aov                 NUMERIC      -- avg offline bill value
  ebo_max_bill            REAL         -- highest single bill
  ebo_return_qty          NUMERIC
  ebo_return_amount       REAL
  first_ebo_date          DATE
  last_ebo_date           DATE
  second_ebo_date         DATE
  days_ebo_1st_to_2nd     INTEGER      -- days between 1st and 2nd EBO visit
  ebo_days_since_last     INTEGER      -- days since last EBO visit
  ebo_same_month_repeat   BOOLEAN
  primary_store           VARCHAR      -- most visited store name

  -- Shopify (Online) metrics
  total_online_orders     NUMERIC
  total_online_qty        NUMERIC
  online_order_days       BIGINT
  total_online_spend      NUMERIC
  online_aov              NUMERIC
  online_max_order        NUMERIC
  total_cod_qty           NUMERIC
  total_prepaid_qty       NUMERIC
  cod_pct                 NUMERIC      -- % orders Cash on Delivery
  cancel_rate_pct         NUMERIC
  cust_cancel_rate_pct    NUMERIC
  fulfilment_rate_pct     NUMERIC
  cod_reliability_score   NUMERIC      -- 0-100
  first_online_date       DATE
  last_online_date        DATE
  second_online_date      DATE
  days_online_1st_to_2nd  INTEGER
  online_days_since_last  INTEGER
  online_same_month_repeat BOOLEAN

  -- Returns
  total_returns           NUMERIC
  customer_returns        NUMERIC      -- real customer-initiated returns
  rto_returns             NUMERIC      -- courier failed to deliver
  qc_pass_rate_pct        NUMERIC
  avg_return_days         NUMERIC
  last_return_date        DATE
  return_risk             TEXT         -- 'No Returns'|'Low'|'Medium'|'High'

  -- Product / Category behaviour
  top_category            TEXT         -- e.g. 'KURTA SET','LEHENGA','SAREES','KURTI'
  second_category         TEXT
  top_category_spend_pct  NUMERIC
  total_categories        BIGINT
  is_single_category      BOOLEAN
  is_dominant_category    BOOLEAN
  category_label          TEXT         -- e.g. 'KURTA SET Only','Multi-Category','KURTA SET Dominant'
  top_brand               TEXT         -- e.g. 'LIBAS','GERUA BY LIBAS'
  distinct_brands         BIGINT
  distinct_sizes          BIGINT
  adult_sizes             BIGINT
  size_combination        TEXT         -- e.g. 'L+M+XL', 'S+M', 'XL' (may be empty)
  size_behaviour          TEXT         -- 'Single Size'|'Multi Size'|'No Size Data'

  -- Combined lifetime metrics
  total_lifetime_spend    DOUBLE PRECISION
  total_lifetime_orders   NUMERIC
  online_spend_pct        NUMERIC      -- % of spend that is online
  days_since_last_purchase INTEGER     -- days since last purchase (any channel)
  days_1st_to_2nd_purchase INTEGER
  retained_30d            BOOLEAN
  retained_60d            BOOLEAN
  retained_90d            BOOLEAN
  same_month_repeat       BOOLEAN

  -- Segmentation
  customer_type           TEXT         -- 'New'|'Repeat'
  frequency_bucket        TEXT         -- '1 Order'|'2 Orders'|'3-4 Orders'|'5-9 Orders'|'10+ Orders'
  channel_journey         TEXT         -- 'Online Only'|'Offline Only'|'Both'
  migration_type          TEXT         -- 'EBO First'|'Shopify First'|'Both Same Time'|'EBO Only'|'Shopify Only'
  migration_lag_days      INTEGER
  online_vs_ebo_aov_diff  NUMERIC
  rfm_r                   INTEGER      -- recency score 1-5
  rfm_f                   INTEGER      -- frequency score 1-5
  rfm_m                   INTEGER      -- monetary score 1-5
  rfm_segment             TEXT         -- 'Champion'|'Loyal'|'New Customer'|'Promising'|'Need Attention'|'At Risk'|'Cannot Lose'|'Lost'|'Occasional'
  churn_risk              TEXT         -- 'None'|'Low'|'Medium'|'High'
  recency_bucket          TEXT         -- 'Active'|'Warm'|'Cooling'|'At Risk'|'Lapsed'
  refreshed_at            TIMESTAMPTZ

NOTE: size_combination may be NULL/empty for many customers — use LIKE or IS NOT NULL checks.
NOTE: There is NO col named "repeat_rate" — compute as COUNT FILTER / COUNT total.
NOTE: There is NO col named "ltv" — use total_lifetime_spend instead.
NOTE: There is NO col named "aov" — use ebo_aov or online_aov separately.

== RAW TRANSACTION VIEWS ==
TABLE: public.cust_ebo_salescombo_view  [957K rows]
  combo, invoice_date, invoice_associate_name (store name),
  barcode, nob (=1 bill), nsq (skus qty), order_amount, rt_qty, rt_amount

TABLE: public.cust_osdcombo_view  [3.87M rows]
  combo, channel_order_date, client_sku_id_ean, order_count,
  order_qty, cod_qty, ncod_qty, cancelled_qty, order_amount

TABLE: public.cust_rtcombo_view  [1.45M rows]
  combo, client_sku_id_ean, return_order_processed_time,
  channel_order_date, cr_qty, rto_qty, blank_qty, pass_qty, fail_qty, rt_qty

== ANALYTICS VIEWS ==
TABLE: public.cust_monthly_cohort_mv
  cohort_month, activity_month, cohort_size, active_customers,
  months_since_first, retention_rate_pct, customer_activity_type

TABLE: public.store_summary_mv
  store_name, total_customers, repeat_customers, repeat_customer_pct,
  avg_customer_ltv, retention_30d_pct, retention_90d_pct,
  champion_count, at_risk_count, high_churn_count,
  migrated_to_online, top_category_at_store

TABLE: public.item_master  [255K rows]
  itemNo, ean, shopifySKU, itemCategoryCode, subCategory, brand,
  sizeNew, seasonNew, designType, occassion, imageUrl

== JOIN KEYS ==
  EBO join    : cust_ebo_salescombo_view.barcode = item_master.ean
  Shopify join: cust_osdcombo_view.client_sku_id_ean = item_master."itemNo"   (NOT shopifySKU — itemNo matches 100%)
  combo join  : use fn_clean_combo(combo) on both sides for safety
"""

SYSTEM_PROMPT = f"""You are an expert PostgreSQL query writer for Libas customer analytics database.

{DB_SCHEMA}

YOUR TASK:
Convert the user's natural language question into a precise PostgreSQL SELECT query.

CRITICAL RULES:
1. Return ONLY the SQL query — no explanation, no markdown, no ```sql blocks
2. Always start with SELECT or WITH
3. Use LIMIT (max 500 for detail queries, no limit for aggregations <50 rows)
4. For monetary values: ROUND(value::NUMERIC, 0)
5. For percentages: ROUND(value::NUMERIC, 1)
6. Use = for exact text matches, ILIKE for partial name searches
7. ALWAYS use exact column names from the schema above — no invented columns
8. City/Zone values are UPPERCASE — use consumer_city = 'DELHI' not 'Delhi'
9. For repeat rate: ROUND(COUNT(*) FILTER (WHERE customer_type='Repeat')::NUMERIC / NULLIF(COUNT(*),0) * 100, 1)
10. For LTV use: total_lifetime_spend
11. For size queries: size_combination may be NULL — use IS NOT NULL AND size_combination <> ''
12. For category queries: use top_category column
13. Date filters: use ::DATE casting e.g. last_updated_date = CURRENT_DATE - 1

EXAMPLE CONVERSIONS:
Q: "Show me champion customers in Delhi"
A: SELECT consumer_name, email, phone, total_lifetime_spend, top_category FROM public.cust_master_profile WHERE rfm_segment = 'Champion' AND consumer_city = 'DELHI' ORDER BY total_lifetime_spend DESC LIMIT 100

Q: "How many customers per zone with average LTV"
A: SELECT consumer_zone, COUNT(*) AS customers, ROUND(AVG(total_lifetime_spend)::NUMERIC,0) AS avg_ltv FROM public.cust_master_profile WHERE consumer_zone IS NOT NULL GROUP BY consumer_zone ORDER BY customers DESC

Q: "Top 5 stores by repeat rate"
A: SELECT store_name, total_customers, repeat_customer_pct, avg_customer_ltv FROM public.store_summary_mv ORDER BY repeat_customer_pct DESC LIMIT 5

Q: "Top 5 categories by repeat purchase rate"
A: SELECT top_category, COUNT(*) AS customers, COUNT(*) FILTER (WHERE customer_type='Repeat') AS repeat_customers, ROUND(COUNT(*) FILTER (WHERE customer_type='Repeat')::NUMERIC/NULLIF(COUNT(*),0)*100,1) AS repeat_rate_pct FROM public.cust_master_profile WHERE top_category IS NOT NULL GROUP BY top_category ORDER BY repeat_rate_pct DESC LIMIT 5

Q: "New customers yesterday"
A: SELECT consumer_name, email, phone, consumer_city, consumer_zone, total_lifetime_spend, channel_journey FROM public.cust_master_profile WHERE last_updated_date = CURRENT_DATE - 1 AND customer_type = 'New' ORDER BY total_lifetime_spend DESC LIMIT 100

Q: "High churn risk customers in NORTH zone with LTV above 10000"
A: SELECT consumer_name, email, phone, consumer_city, total_lifetime_spend, rfm_segment, days_since_last_purchase FROM public.cust_master_profile WHERE churn_risk = 'High' AND consumer_zone = 'NORTH' AND total_lifetime_spend > 10000 ORDER BY total_lifetime_spend DESC LIMIT 200

Q: "Customers who came to EBO first but never came back"
A: SELECT consumer_name, email, phone, consumer_city, total_ebo_bills, total_ebo_spend, ebo_days_since_last, primary_store FROM public.cust_master_profile WHERE in_ebo = TRUE AND in_shopify = FALSE AND ebo_days_since_last > 180 ORDER BY total_ebo_spend DESC LIMIT 200

Q: "Compare AOV of new vs repeat customers"
A: SELECT customer_type, COUNT(*) AS customers, ROUND(AVG(ebo_aov)::NUMERIC,0) AS avg_ebo_aov, ROUND(AVG(online_aov)::NUMERIC,0) AS avg_online_aov FROM public.cust_master_profile WHERE customer_type IS NOT NULL GROUP BY customer_type ORDER BY customer_type
"""


# ── Pydantic models ───────────────────────────────────────────────────────────
class QueryRequest(BaseModel):
    question : str
    history  : Optional[list] = []   # previous Q&A for context

class ExecuteRequest(BaseModel):
    sql: str


# ── Schema endpoint ───────────────────────────────────────────────────────────
@router.get("/schema")
def get_schema():
    """Returns available tables and key columns for the frontend."""
    return {
        "tables": [
            {"name": "cust_master_profile",      "rows": "2.2M", "desc": "Master customer profile — one row per customer"},
            {"name": "cust_ebo_salescombo_view",  "rows": "957K", "desc": "EBO offline transaction details"},
            {"name": "cust_osdcombo_view",        "rows": "3.87M","desc": "Shopify online order details"},
            {"name": "cust_rtcombo_view",         "rows": "1.45M","desc": "Returns data"},
            {"name": "cust_monthly_cohort_mv",    "rows": "~500", "desc": "Cohort retention analytics"},
            {"name": "store_summary_mv",          "rows": "~50",  "desc": "Store-level aggregated metrics"},
            {"name": "item_master",               "rows": "256K", "desc": "Product catalogue with categories and sizes"},
        ],
        "example_questions": [
            "Show me champion customers in Delhi",
            "Top 10 stores by repeat rate",
            "How many customers per zone with average LTV?",
            "Customers who bought LEHENGA only",
            "High churn risk customers in NORTH zone with LTV above 10000",
            "Compare new vs repeat customer AOV",
            "Which city has the most omnichannel customers?",
            "Top 5 categories by repeat purchase rate",
            "Customers who returned more than 3 times",
            "Monthly new vs repeat customers last 6 months",
            "Stores with highest migration to online",
            "Customers with size combination L+XL in SOUTH zone",
            "Customers who came to EBO first but never came back offline",
            "Online customers who never visited a store",
            "Customers who shopped both online and offline in same month",
            "How many customers migrated from EBO to online each month?",
            "Show me EBO first customers who are now lost segment",
        ]
    }


# ── Text-to-SQL endpoint ──────────────────────────────────────────────────────
@router.post("/query")
def text_to_sql_query(req: QueryRequest, db: Session = Depends(get_db)):
    """
    Natural language → SQL → Execute → Return results
    1. Send question to Groq with full schema context
    2. Validate generated SQL (SELECT only check)
    3. Execute against PostgreSQL
    4. Return results + generated SQL
    """
    if not GROQ_API_KEY:
        raise HTTPException(status_code=503, detail="GROQ_API_KEY not configured")

    question = req.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question cannot be empty")

    # ── Build messages with conversation history ───────────────────────────────
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    # Add previous turns for context (last 4 exchanges)
    for h in (req.history or [])[-4:]:
        if h.get("role") and h.get("content"):
            messages.append({"role": h["role"], "content": h["content"]})

    messages.append({"role": "user", "content": question})

    # ── Call Groq ─────────────────────────────────────────────────────────────
    try:
        response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type" : "application/json",
            },
            json={
                "model"      : GROQ_MODEL,
                "messages"   : messages,
                "temperature": 0.1,   # very low for consistent SQL
                "max_tokens" : 800,
            },
            timeout=30,
        )

        if response.status_code != 200:
            raise HTTPException(
                status_code=503,
                detail=f"Groq API error: {response.status_code}"
            )

        generated_sql = response.json()["choices"][0]["message"]["content"].strip()

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Groq API failed: {str(e)}")

    # ── Clean SQL — remove markdown if model added it ─────────────────────────
    generated_sql = re.sub(r"```sql\s*", "", generated_sql, flags=re.IGNORECASE)
    generated_sql = re.sub(r"```\s*",    "", generated_sql)
    generated_sql = generated_sql.strip().rstrip(";")

    # ── Safety: ensure it's a SELECT ─────────────────────────────────────────
    first_word = generated_sql.strip().split()[0].upper() if generated_sql.strip() else ""
    if first_word not in ("SELECT", "WITH", "EXPLAIN"):
        raise HTTPException(
            status_code=400,
            detail=f"Generated query is not a SELECT statement. Got: {first_word}"
        )

    # ── Execute query ─────────────────────────────────────────────────────────
    try:
        result = db.execute(text(generated_sql))
        columns = list(result.keys())
        rows    = [list(r) for r in result.fetchall()]

        # Convert non-serializable types
        import decimal
        from datetime import date as dt_date, datetime as dt_datetime
        clean_rows = []
        for row in rows:
            clean_row = []
            for val in row:
                if isinstance(val, decimal.Decimal): val = float(val)
                elif isinstance(val, (dt_date, dt_datetime)): val = str(val)
                elif val is None: val = None
                else: val = val
                clean_row.append(val)
            clean_rows.append(clean_row)

        return {
            "question"   : question,
            "sql"        : generated_sql,
            "columns"    : columns,
            "rows"       : clean_rows,
            "row_count"  : len(clean_rows),
            "status"     : "success",
        }

    except Exception as e:
        # Return the SQL with the error so user can see what was generated
        return {
            "question"   : question,
            "sql"        : generated_sql,
            "columns"    : [],
            "rows"       : [],
            "row_count"  : 0,
            "status"     : "error",
            "error"      : str(e),
        }


# ── Direct SQL execute endpoint ───────────────────────────────────────────────
@router.post("/execute")
def execute_sql(req: ExecuteRequest, db: Session = Depends(get_db)):
    """Execute raw SQL directly (user can edit generated SQL and re-run)."""
    sql = req.sql.strip().rstrip(";")
    if not sql:
        raise HTTPException(status_code=400, detail="SQL cannot be empty")

    try:
        import decimal
        from datetime import date as dt_date, datetime as dt_datetime

        result  = db.execute(text(sql))
        columns = list(result.keys())
        rows    = [list(r) for r in result.fetchall()]

        clean_rows = []
        for row in rows:
            clean_row = []
            for val in row:
                if isinstance(val, decimal.Decimal): val = float(val)
                elif isinstance(val, (dt_date, dt_datetime)): val = str(val)
                clean_row.append(val)
            clean_rows.append(clean_row)

        return {
            "sql"      : sql,
            "columns"  : columns,
            "rows"     : clean_rows,
            "row_count": len(clean_rows),
            "status"   : "success",
        }

    except Exception as e:
        return {
            "sql"      : sql,
            "columns"  : [],
            "rows"     : [],
            "row_count": 0,
            "status"   : "error",
            "error"    : str(e),
        }


# ── CSV export endpoint ───────────────────────────────────────────────────────
@router.post("/export-csv")
def export_query_csv(req: ExecuteRequest):
    """Execute SQL and return results as CSV download."""
    import io, csv, psycopg2

    sql = req.sql.strip().rstrip(";")
    if not sql:
        raise HTTPException(status_code=400, detail="SQL cannot be empty")

    try:
        conn = psycopg2.connect(**PG, connect_timeout=15)
        cur  = conn.cursor()
        cur.execute(sql)
        columns = [d[0] for d in cur.description]
        rows    = cur.fetchall()
        cur.close()
        conn.close()

        def generate():
            buf    = io.StringIO()
            writer = csv.writer(buf)
            writer.writerow(columns)
            buf.seek(0); yield buf.read(); buf.truncate(0); buf.seek(0)
            for row in rows:
                writer.writerow([str(v) if v is not None else "" for v in row])
                buf.seek(0); yield buf.read(); buf.truncate(0); buf.seek(0)

        return StreamingResponse(
            generate(),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=query_results.csv"},
        )

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ============================================================================
# EBO AGENT — Store-scoped Text-to-SQL for offline customer intelligence
# ============================================================================

EBO_SCHEMA = """
DATABASE: Unicorn (PostgreSQL)
EBO = Exclusive Brand Outlet (offline stores). All monetary values in INR (₹).

== PRIMARY TABLES FOR EBO QUERIES ==

TABLE: public.cust_ebo_salescombo_view  [957K rows — one row per EBO bill]
  combo                   TEXT     -- customer identifier (email-phone)
  invoice_date            DATE     -- date of purchase
  invoice_associate_name  TEXT     -- store name e.g. 'Lajpat Nagar Delhi'
  barcode                 TEXT     -- product barcode (joins to item_master.ean)
  nob                     NUMERIC  -- number of bills (always 1 per row)
  nsq                     NUMERIC  -- number of SKUs in bill
  order_amount            NUMERIC  -- bill amount in ₹
  rt_qty                  NUMERIC  -- return quantity
  rt_amount               NUMERIC  -- return amount

TABLE: public.cust_master_profile  [2.24M rows — one row per customer]
  combo                   TEXT     -- PRIMARY KEY (matches fn_clean_combo(ebo.combo))
  consumer_name           TEXT
  email                   TEXT
  phone                   TEXT
  consumer_city           TEXT     -- UPPERCASE
  consumer_state          TEXT     -- UPPERCASE
  consumer_zone           TEXT     -- 'NORTH'|'SOUTH'|'EAST'|'WEST'|'CENTRAL'
  consumer_pincode        TEXT
  primary_store           TEXT     -- most visited store
  total_ebo_bills         NUMERIC  -- lifetime EBO visits
  total_ebo_spend         REAL     -- lifetime EBO spend
  ebo_aov                 NUMERIC  -- avg EBO bill value
  ebo_days_since_last     INTEGER  -- days since last EBO visit
  first_ebo_date          DATE
  last_ebo_date           DATE
  rfm_segment             TEXT     -- 'Champion'|'Loyal'|'At Risk'|'Cannot Lose'|'Lost' etc
  churn_risk              TEXT     -- 'None'|'Low'|'Medium'|'High'
  customer_type           TEXT     -- 'New'|'Repeat'
  top_category            TEXT     -- e.g. 'KURTA SET','LEHENGA'
  top_brand               TEXT
  size_behaviour          TEXT     -- 'Single Size'|'Multi Size'
  size_combination        TEXT     -- e.g. 'L+M+XL'
  migration_type          TEXT     -- 'EBO Only'|'EBO First'|'Both Same Time' etc
  total_lifetime_spend    DOUBLE PRECISION
  channel_journey         TEXT     -- 'Offline Only'|'Both'
  in_ebo                  BOOLEAN
  in_shopify              BOOLEAN

TABLE: public.item_master  [255K rows — product catalogue]
  ean                     VARCHAR  -- barcode (join key with cust_ebo_salescombo_view.barcode)
  itemNo                  VARCHAR  -- item number
  "itemCategoryCode"      VARCHAR  -- category e.g. 'KURTA SET','LEHENGA','SAREES'
  "subCategory"           VARCHAR  -- sub-category
  brand                   VARCHAR  -- brand name
  "sizeNew"               VARCHAR  -- size e.g. 'M','L','XL','XXL'
  "seasonNew"             VARCHAR  -- current season
  "designType"            VARCHAR  -- design type
  "occassion"             VARCHAR  -- occasion tag
  "fabric"                VARCHAR  -- fabric type
  "technique"             VARCHAR  -- production technique
  "color"                 VARCHAR  -- colour
  mrp                     VARCHAR  -- MRP (cast with safe_float() for math)
  "imageUrl"              TEXT     -- product image URL

TABLE: public.store_summary_mv  [per-store aggregated metrics]
  store_name, total_customers, repeat_customers, repeat_customer_pct,
  avg_customer_ltv, retention_30d_pct, retention_90d_pct,
  champion_count, at_risk_count, high_churn_count,
  migrated_to_online, top_category_at_store

== JOIN KEYS ==
  EBO transaction → customer profile:
    fn_clean_combo(e.combo) = fn_clean_combo(mp.combo)
  EBO transaction → product:
    e.barcode = im.ean
  item_master columns: ALWAYS double-quote e.g. im."itemCategoryCode"

== CRITICAL RULES ==
1. Store filter: WHERE TRIM(e.invoice_associate_name) = 'Store Name'
2. City/Zone: UPPERCASE in cust_master_profile
3. Amounts in ₹ — use ROUND(value::NUMERIC, 0)
4. Date filter: WHERE DATE_TRUNC('month', invoice_date) = DATE_TRUNC('month', CAST('YYYY-MM-01' AS DATE))
5. Customer join: always use fn_clean_combo() on BOTH sides
6. item_master columns: always double-quote — "itemCategoryCode", "sizeNew" etc
7. Return ONLY the SQL query — no explanation, no markdown

== 50 EBO EXAMPLE QUESTIONS ==

Q: Top 10 customers by spend at Lajpat Nagar Delhi this month
SQL: SELECT mp.consumer_name, mp.email, mp.phone, mp.consumer_city, SUM(e.order_amount) AS month_spend, COUNT(*) AS bills FROM public.cust_ebo_salescombo_view e JOIN public.cust_master_profile mp ON fn_clean_combo(mp.combo)=fn_clean_combo(e.combo) WHERE TRIM(e.invoice_associate_name)='Lajpat Nagar Delhi' AND DATE_TRUNC('month',e.invoice_date)=(SELECT DATE_TRUNC('month',MAX(invoice_date)) FROM public.cust_ebo_salescombo_view) GROUP BY mp.consumer_name,mp.email,mp.phone,mp.consumer_city ORDER BY month_spend DESC LIMIT 10;

Q: Which customers bought LEHENGA at any EBO store?
SQL: SELECT DISTINCT mp.consumer_name,mp.email,mp.phone,mp.consumer_city,mp.rfm_segment FROM public.cust_ebo_salescombo_view e JOIN public.item_master im ON im.ean=e.barcode JOIN public.cust_master_profile mp ON fn_clean_combo(mp.combo)=fn_clean_combo(e.combo) WHERE im."itemCategoryCode" ILIKE '%LEHENGA%' ORDER BY mp.consumer_name LIMIT 200;

Q: New customers at Rajouri Mall Delhi in January 2026
SQL: SELECT mp.consumer_name,mp.email,mp.phone,mp.consumer_city,e.invoice_date,e.order_amount FROM public.cust_ebo_salescombo_view e JOIN public.cust_master_profile mp ON fn_clean_combo(mp.combo)=fn_clean_combo(e.combo) WHERE TRIM(e.invoice_associate_name)='Rajouri Mall Delhi' AND DATE_TRUNC('month',e.invoice_date)=DATE_TRUNC('month','2026-01-01'::DATE) AND mp.customer_type='New' ORDER BY e.invoice_date DESC LIMIT 200;

Q: Customers at Lajpat Nagar Delhi who haven't visited in 90 days
SQL: SELECT mp.consumer_name,mp.email,mp.phone,mp.consumer_city,mp.total_ebo_bills,mp.total_ebo_spend,mp.ebo_days_since_last,mp.rfm_segment FROM public.cust_master_profile mp WHERE mp.primary_store='Lajpat Nagar Delhi' AND mp.ebo_days_since_last>90 ORDER BY mp.total_ebo_spend DESC LIMIT 200;

Q: Which sizes sell most at V3S Mall Delhi?
SQL: SELECT im."sizeNew" AS size, COUNT(*) AS qty_sold, COUNT(DISTINCT fn_clean_combo(e.combo)) AS customers FROM public.cust_ebo_salescombo_view e JOIN public.item_master im ON im.ean=e.barcode WHERE TRIM(e.invoice_associate_name)='V3S Mall Delhi' AND im."sizeNew" IS NOT NULL AND TRIM(im."sizeNew")!='' GROUP BY im."sizeNew" ORDER BY qty_sold DESC LIMIT 15;

Q: Cannot Lose customers at Phoenix Mall Pune with contact details
SQL: SELECT mp.consumer_name,mp.email,mp.phone,mp.consumer_city,mp.total_ebo_spend,mp.ebo_days_since_last,mp.top_category FROM public.cust_master_profile mp WHERE mp.primary_store='Phoenix Mall Pune' AND mp.rfm_segment='Cannot Lose' ORDER BY mp.total_ebo_spend DESC;

Q: Month on month revenue for Lulu Mall Lucknow last 12 months
SQL: SELECT TO_CHAR(DATE_TRUNC('month',e.invoice_date),'Mon YYYY') AS month, ROUND(SUM(e.order_amount)::NUMERIC,0) AS revenue, COUNT(DISTINCT fn_clean_combo(e.combo)) AS customers FROM public.cust_ebo_salescombo_view e WHERE TRIM(e.invoice_associate_name)='Lulu Mall Lucknow' AND e.invoice_date>=CURRENT_DATE-INTERVAL '12 months' GROUP BY DATE_TRUNC('month',e.invoice_date) ORDER BY DATE_TRUNC('month',e.invoice_date) ASC;

Q: Top categories at ZV-MallOfIndia-Noida by revenue
SQL: SELECT im."itemCategoryCode" AS category, ROUND(SUM(e.order_amount)::NUMERIC,0) AS revenue, COUNT(DISTINCT fn_clean_combo(e.combo)) AS customers FROM public.cust_ebo_salescombo_view e JOIN public.item_master im ON im.ean=e.barcode WHERE TRIM(e.invoice_associate_name)='ZV-MallOfIndia-Noida' AND im."itemCategoryCode" IS NOT NULL GROUP BY im."itemCategoryCode" ORDER BY revenue DESC LIMIT 10;

Q: Champion customers who shop both online and offline
SQL: SELECT mp.consumer_name,mp.email,mp.phone,mp.consumer_city,mp.total_ebo_spend,mp.total_online_spend,mp.total_lifetime_spend,mp.primary_store FROM public.cust_master_profile mp WHERE mp.rfm_segment='Champion' AND mp.in_ebo=TRUE AND mp.in_shopify=TRUE ORDER BY mp.total_lifetime_spend DESC LIMIT 100;

Q: Average bill value per store this month
SQL: SELECT TRIM(e.invoice_associate_name) AS store, ROUND(AVG(e.order_amount)::NUMERIC,0) AS avg_bill, COUNT(DISTINCT fn_clean_combo(e.combo)) AS customers, ROUND(SUM(e.order_amount)::NUMERIC,0) AS total_revenue FROM public.cust_ebo_salescombo_view e WHERE DATE_TRUNC('month',e.invoice_date)=(SELECT DATE_TRUNC('month',MAX(invoice_date)) FROM public.cust_ebo_salescombo_view) GROUP BY TRIM(e.invoice_associate_name) ORDER BY avg_bill DESC;
"""

EBO_SYSTEM_PROMPT = f"""You are an expert PostgreSQL query writer for Libas EBO (offline store) analytics.

{EBO_SCHEMA}

YOUR TASK: Convert natural language questions about EBO stores and customers into precise PostgreSQL SELECT queries.

CRITICAL RULES:
1. Return ONLY the SQL — no explanation, no markdown, no ```sql blocks
2. Always start with SELECT or WITH
3. Always double-quote item_master columns: "itemCategoryCode", "sizeNew", "seasonNew" etc
4. Use fn_clean_combo() on BOTH sides of customer joins
5. Store name filter: WHERE TRIM(e.invoice_associate_name) = 'Exact Store Name'
6. LIMIT all detail queries to 200 rows max, aggregations no limit
7. City/Zone values are UPPERCASE
8. For monetary values: ROUND(value::NUMERIC, 0)
9. If store name is mentioned, always filter to that store
10. If no store mentioned, query across all stores
11. DATA LAGS THE CALENDAR by a few days. For "this month" / "current month" / "latest month",
    do NOT use CURRENT_DATE (the current calendar month is usually empty). Instead use the most
    recent month that actually has data:
      DATE_TRUNC('month', e.invoice_date) = (SELECT DATE_TRUNC('month', MAX(invoice_date)) FROM public.cust_ebo_salescombo_view)
    Likewise for "this year", anchor to MAX(invoice_date), not CURRENT_DATE.
"""


class EBOQueryRequest(BaseModel):
    question    : str
    store_name  : Optional[str] = None   # scope to specific store if provided
    history     : Optional[list] = []


@router.post("/ebo-query")
def ebo_agent_query(req: EBOQueryRequest, db: Session = Depends(get_db)):
    """
    EBO Text-to-SQL Agent.
    Scoped to offline store data: EBO transactions + customer profiles + item_master.
    Optionally scoped to a specific store.
    """
    if not GROQ_API_KEY:
        raise HTTPException(status_code=503, detail="GROQ_API_KEY not configured")

    question = req.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question cannot be empty")

    # Build system prompt — inject store scope if provided
    system = EBO_SYSTEM_PROMPT
    if req.store_name:
        system += f"""

STORE LOCK (STRICT): You can ONLY answer about the store "{req.store_name}". This is a hard rule.
- When querying cust_ebo_salescombo_view, ALWAYS add: WHERE TRIM(invoice_associate_name) = '{req.store_name}'
- When querying cust_master_profile, ALWAYS add: WHERE primary_store = '{req.store_name}'
- If the user mentions, names, or asks about ANY OTHER store, IGNORE that other store name completely
  and still answer ONLY for "{req.store_name}". Never query, compare, or return data for any other store.
- Never write a query without the "{req.store_name}" store filter.
"""

    messages = [{"role": "system", "content": system}]
    for h in (req.history or [])[-4:]:
        if h.get("role") and h.get("content"):
            messages.append({"role": h["role"], "content": h["content"]})
    messages.append({"role": "user", "content": question})

    try:
        
        response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type" : "application/json",
            },
            json={
                "model"      : GROQ_MODEL,
                "messages"   : messages,
                "temperature": 0.1,
                "max_tokens" : 1000,
            },
            timeout=30,
        )
        if response.status_code != 200:
            raise HTTPException(status_code=503, detail=f"Groq error: {response.status_code}")

        sql = response.json()["choices"][0]["message"]["content"].strip()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Groq failed: {str(e)}")

    # Clean SQL
    sql = re.sub(r"```sql\s*", "", sql, flags=re.IGNORECASE)
    sql = re.sub(r"```\s*", "", sql).strip().rstrip(";")

    # STORE LOCK safety net: force every store filter to the scoped store, so a
    # store-page agent can never return another store's data even if the model slips.
    if req.store_name:
        sn = req.store_name.replace("'", "''")
        sql = re.sub(r"(invoice_associate_name\s*\)\s*=\s*)'[^']*'", rf"\1'{sn}'", sql, flags=re.IGNORECASE)
        sql = re.sub(r"(invoice_associate_name\s*=\s*)'[^']*'",      rf"\1'{sn}'", sql, flags=re.IGNORECASE)
        sql = re.sub(r"(primary_store\s*=\s*)'[^']*'",                rf"\1'{sn}'", sql, flags=re.IGNORECASE)

    first_word = sql.strip().split()[0].upper() if sql.strip() else ""
    if first_word not in ("SELECT", "WITH", "EXPLAIN"):
        raise HTTPException(status_code=400, detail=f"Not a SELECT query: {first_word}")

    # Execute
    try:
        import decimal
        from datetime import date as dt_date, datetime as dt_datetime

        result  = db.execute(text(sql))
        columns = list(result.keys())
        rows    = [list(r) for r in result.fetchall()]

        clean_rows = []
        for row in rows:
            clean_row = []
            for val in row:
                if isinstance(val, decimal.Decimal): val = float(val)
                elif isinstance(val, (dt_date, dt_datetime)): val = str(val)
                clean_row.append(val)
            clean_rows.append(clean_row)

        return {
            "question"  : question,
            "sql"       : sql,
            "store_scope": req.store_name,
            "columns"   : columns,
            "rows"      : clean_rows,
            "row_count" : len(clean_rows),
            "status"    : "success",
        }

    except Exception as e:
        return {
            "question"  : question,
            "sql"       : sql,
            "store_scope": req.store_name,
            "columns"   : [],
            "rows"      : [],
            "row_count" : 0,
            "status"    : "error",
            "error"     : str(e),
        }


@router.post("/ebo-export-csv")
def ebo_export_csv(req: ExecuteRequest):
    """Export EBO agent query results as CSV."""
    import io, csv, psycopg2
    sql = req.sql.strip().rstrip(";")
    if not sql:
        raise HTTPException(status_code=400, detail="SQL cannot be empty")
    try:
        conn = psycopg2.connect(**PG, connect_timeout=15)
        cur  = conn.cursor()
        cur.execute(sql)
        columns = [d[0] for d in cur.description]
        rows    = cur.fetchall()
        cur.close(); conn.close()
        def generate():
            buf    = io.StringIO()
            writer = csv.writer(buf)
            writer.writerow(columns)
            buf.seek(0); yield buf.read(); buf.truncate(0); buf.seek(0)
            for row in rows:
                writer.writerow([str(v) if v is not None else "" for v in row])
                buf.seek(0); yield buf.read(); buf.truncate(0); buf.seek(0)
        return StreamingResponse(
            generate(),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=ebo_query.csv"},
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── v2: LangGraph agentic endpoint ────────────────────────────────────────────
class AgentV2Request(BaseModel):
    question   : str
    store_name : Optional[str] = None
    history    : Optional[list] = []


@router.post("/v2/query")
def agent_v2_query(req: AgentV2Request):
    """
    Production agentic endpoint (LangGraph): reasoning + tool-calling + self-correction.
    Returns a natural-language answer, the primary result table, the SQL used, an
    optional chart image (base64 PNG), and observability metadata.
    """
    if not (req.question or "").strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty")
    from api.agent_graph.graph import run_agent          # lazy import (avoids circular)
    return run_agent(req.question.strip(), req.store_name, req.history)


@router.post("/v2/export-csv")
def agent_v2_export_csv(req: ExecuteRequest):
    """Export the agent's result as CSV — re-runs the SQL under the read-only guardrails."""
    import io, csv
    from api.agent_graph.guardrails import sanitize_sql, run_readonly, GuardrailError
    try:
        clean = sanitize_sql(req.sql or "")
        cols, rows = run_readonly(clean)
    except GuardrailError as e:
        raise HTTPException(status_code=400, detail=f"Blocked: {e}")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    def generate():
        buf = io.StringIO(); writer = csv.writer(buf)
        writer.writerow(cols)
        buf.seek(0); yield buf.read(); buf.truncate(0); buf.seek(0)
        for row in rows:
            writer.writerow([str(v) if v is not None else "" for v in row])
            buf.seek(0); yield buf.read(); buf.truncate(0); buf.seek(0)

    return StreamingResponse(
        generate(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=agent_result.csv"},
    )