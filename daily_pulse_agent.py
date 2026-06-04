# daily_pulse_agent.py
# ----------------------------------------------------------------
# Daily Pulse Narrator — Customer Journey AI Agent
# Runs at 9:00 AM IST daily via Windows Task Scheduler
# ----------------------------------------------------------------

import os
import sys
import json
import logging
import psycopg2
import requests
from datetime import datetime, date, timedelta
from dotenv import load_dotenv

load_dotenv()

sys.path.append(os.path.dirname(__file__))
from slack_sender     import send_files_to_slack, chunk_list
from slack_channel_id import get_channel_id_by_name

# ── Config ────────────────────────────────────────────────────────────────────
PG = {
    "host"    : os.getenv("PG_HOST",     "10.150.0.5"),
    "port"    : int(os.getenv("PG_PORT", "5432")),
    "dbname"  : os.getenv("PG_DATABASE", "Unicorn"),
    "user"    : os.getenv("PG_USER",     "Amit"),
    "password": os.getenv("PG_PASSWORD", "Amit@23200"),
}

GROQ_API_KEY  = os.getenv("GROQ_API_KEY")
SLACK_TOKEN   = os.getenv("SLACK_TOKEN")
SLACK_CHANNEL = "da_testing"

EMAIL_SENDER     = os.getenv("EMAIL_SENDER",     "amit.panchal@libas.in")
EMAIL_TOKEN_PATH = os.getenv("EMAIL_TOKEN_PATH", "Himanshu.json")
EMAIL_RECIPIENTS = os.getenv("EMAIL_RECIPIENTS", "amit.panchal@libas.in").split(",")
EMAIL_CC         = os.getenv("EMAIL_CC",         "").split(",")
EMAIL_CLASS_FILE = os.getenv("EMAIL_CLASS_FILE", "email_sender")  # filename without .py

# ── Logging ───────────────────────────────────────────────────────────────────
LOG_DIR  = os.path.join(os.path.dirname(__file__), "logs")
os.makedirs(LOG_DIR, exist_ok=True)
log_file = os.path.join(LOG_DIR, f"pulse_{date.today().strftime('%Y-%m-%d')}.log")

logging.basicConfig(
    level    = logging.INFO,
    format   = "%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt  = "%Y-%m-%d %H:%M:%S",
    handlers = [
        logging.FileHandler(log_file, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ]
)
log = logging.getLogger(__name__)


# ── Helpers ───────────────────────────────────────────────────────────────────
def fmt(n):
    """Format number in Indian style."""
    if n is None: return "0"
    n = int(n)
    if n >= 10000000: return f"{n/10000000:.1f}Cr"
    if n >= 100000:   return f"{n/100000:.1f}L"
    if n >= 1000:     return f"{n/1000:.1f}K"
    return str(n)

def fmtr(n):
    """Format rupees."""
    return f"₹{fmt(n)}"


# ── Step 1: Collect all metrics ───────────────────────────────────────────────
def collect_metrics(conn) -> dict:
    cur       = conn.cursor()
    today     = date.today()
    yesterday = today - timedelta(days=1)
    metrics   = {"report_date": today.strftime("%d %B %Y"),
                 "report_day" : today.strftime("%A"),
                 "yesterday"  : yesterday.strftime("%d %B %Y")}

    log.info("Collecting metrics...")

    # ── 1. Overall summary ────────────────────────────────────────────────────
    cur.execute("""
        SELECT
            COUNT(*)                                                        AS total_customers,
            COUNT(*) FILTER (WHERE customer_type = 'Repeat')               AS repeat_customers,
            ROUND((COUNT(*) FILTER (WHERE customer_type = 'Repeat')
                ::NUMERIC / NULLIF(COUNT(*),0) * 100), 1)                  AS repeat_rate_pct,
            ROUND(AVG(total_lifetime_spend)::NUMERIC, 0)                   AS avg_ltv,
            COUNT(*) FILTER (WHERE churn_risk = 'High')                    AS high_churn_count,
            COUNT(*) FILTER (WHERE last_updated_date = %s)                 AS new_yesterday,
            COUNT(*) FILTER (
                WHERE last_updated_date = %s AND customer_type = 'Repeat'
            )                                                               AS repeat_yesterday,
            COUNT(*) FILTER (WHERE rfm_segment = 'Champion')               AS champion_count,
            COUNT(*) FILTER (WHERE rfm_segment = 'Cannot Lose')            AS cannot_lose_count,
            COUNT(*) FILTER (WHERE rfm_segment = 'Lost')                   AS lost_count,
            COUNT(*) FILTER (WHERE same_month_repeat = TRUE)               AS same_month_repeat_count,
            ROUND(COUNT(*) FILTER (WHERE same_month_repeat = TRUE)
                ::NUMERIC / NULLIF(COUNT(*),0) * 100, 1)                   AS same_month_repeat_pct
        FROM public.cust_master_profile
    """, (yesterday, yesterday))
    row = cur.fetchone()
    metrics["overall"] = {
        "total_customers"       : int(row[0]  or 0),
        "repeat_customers"      : int(row[1]  or 0),
        "repeat_rate_pct"       : float(row[2] or 0),
        "avg_ltv"               : int(row[3]  or 0),
        "high_churn_count"      : int(row[4]  or 0),
        "new_yesterday"         : int(row[5]  or 0),
        "repeat_yesterday"      : int(row[6]  or 0),
        "champion_count"        : int(row[7]  or 0),
        "cannot_lose_count"     : int(row[8]  or 0),
        "lost_count"            : int(row[9]  or 0),
        "same_month_repeat_count": int(row[10] or 0),
        "same_month_repeat_pct" : float(row[11] or 0),
    }

    # ── 2. New customers added yesterday (top 5) ──────────────────────────────
    cur.execute("""
        SELECT
            consumer_name, email, phone,
            consumer_city, consumer_zone,
            total_lifetime_spend, channel_journey, top_category
        FROM public.cust_master_profile
        WHERE last_updated_date = %s
          AND customer_type = 'New'
        ORDER BY total_lifetime_spend DESC NULLS LAST
        LIMIT 5
    """, (yesterday,))
    metrics["new_customers_yesterday"] = [
        {
            "name"    : r[0] or "—",
            "email"   : r[1] or "—",
            "phone"   : r[2] or "—",
            "city"    : r[3] or "—",
            "zone"    : r[4] or "—",
            "spend"   : int(r[5] or 0),
            "channel" : r[6] or "—",
            "category": r[7] or "—",
        }
        for r in cur.fetchall()
    ]

    # ── 3. Repeat customers active yesterday (top 5) ──────────────────────────
    cur.execute("""
        SELECT
            consumer_name, email, phone,
            consumer_city, consumer_zone,
            total_lifetime_spend, total_lifetime_orders,
            rfm_segment, top_category
        FROM public.cust_master_profile
        WHERE last_updated_date = %s
          AND customer_type = 'Repeat'
        ORDER BY total_lifetime_spend DESC NULLS LAST
        LIMIT 5
    """, (yesterday,))
    metrics["repeat_customers_yesterday"] = [
        {
            "name"    : r[0] or "—",
            "email"   : r[1] or "—",
            "city"    : r[2] or "—",
            "zone"    : r[4] or "—",
            "ltv"     : int(r[5] or 0),
            "orders"  : int(r[6] or 0),
            "segment" : r[7] or "—",
            "category": r[8] or "—",
        }
        for r in cur.fetchall()
    ]

    # ── 4. Top categories ─────────────────────────────────────────────────────
    cur.execute("""
        SELECT
            top_category,
            COUNT(*)                                                AS customers,
            COUNT(*) FILTER (WHERE customer_type = 'Repeat')       AS repeat_cx,
            ROUND(COUNT(*) FILTER (WHERE customer_type = 'Repeat')
                ::NUMERIC / NULLIF(COUNT(*),0) * 100, 1)           AS repeat_rate,
            ROUND(AVG(total_lifetime_spend)::NUMERIC, 0)           AS avg_ltv
        FROM public.cust_master_profile
        WHERE top_category IS NOT NULL
        GROUP BY top_category
        ORDER BY customers DESC
        LIMIT 5
    """)
    metrics["top_categories"] = [
        {
            "category"   : r[0],
            "customers"  : int(r[1] or 0),
            "repeat_cx"  : int(r[2] or 0),
            "repeat_rate": float(r[3] or 0),
            "avg_ltv"    : int(r[4] or 0),
        }
        for r in cur.fetchall()
    ]

    # ── 5. Top sizes purchased ────────────────────────────────────────────────
    cur.execute("""
        SELECT
            size_combination,
            COUNT(*)                                                AS customers,
            ROUND(COUNT(*)::NUMERIC / SUM(COUNT(*)) OVER() * 100, 1) AS pct
        FROM public.cust_master_profile
        WHERE size_behaviour = 'Multi Size'
          AND size_combination IS NOT NULL
        GROUP BY size_combination
        ORDER BY customers DESC
        LIMIT 5
    """)
    metrics["top_size_combos"] = [
        {"size": r[0], "customers": int(r[1] or 0), "pct": float(r[2] or 0)}
        for r in cur.fetchall()
    ]

   # Single size most common — from size_combination column
    cur.execute("""
        SELECT
            size_combination                                        AS size,
            COUNT(*)                                                AS customers
        FROM public.cust_master_profile
        WHERE size_behaviour = 'Single Size'
          AND size_combination IS NOT NULL
          AND size_combination <> ''
        GROUP BY size_combination
        ORDER BY customers DESC
        LIMIT 3
    """)
    metrics["top_single_sizes"] = [
        {"size": r[0], "customers": int(r[1] or 0)}
        for r in cur.fetchall()
    ]

    # ── 6. Top season from item_master ────────────────────────────────────────
    cur.execute("""
        SELECT
            im."seasonNew"                                          AS season,
            COUNT(DISTINCT public.fn_clean_combo(e.combo))         AS customers
        FROM public.cust_ebo_salescombo_view e
        INNER JOIN public.item_master im ON im.ean = e.barcode
        WHERE im."seasonNew" IS NOT NULL AND im."seasonNew" <> ''
        GROUP BY im."seasonNew"
        ORDER BY customers DESC
        LIMIT 5
    """)
    metrics["top_seasons"] = [
        {"season": r[0], "customers": int(r[1] or 0)}
        for r in cur.fetchall()
    ]

    # ── 7. AOV — New vs Repeat ────────────────────────────────────────────────
    cur.execute("""
        SELECT
            customer_type,
            ROUND(AVG(ebo_aov)::NUMERIC, 0)                        AS avg_ebo_aov,
            ROUND(AVG(online_aov)::NUMERIC, 0)                     AS avg_online_aov,
            ROUND(AVG(total_lifetime_spend
                / NULLIF(total_lifetime_orders,0))::NUMERIC, 0)    AS blended_aov,
            COUNT(*)                                                AS customers
        FROM public.cust_master_profile
        WHERE customer_type IN ('New','Repeat')
        GROUP BY customer_type
    """)
    metrics["aov_comparison"] = [
        {
            "type"       : r[0],
            "ebo_aov"    : int(r[1] or 0),
            "online_aov" : int(r[2] or 0),
            "blended_aov": int(r[3] or 0),
            "customers"  : int(r[4] or 0),
        }
        for r in cur.fetchall()
    ]

    # ── 8. Channel migration stats ────────────────────────────────────────────
    cur.execute("""
        SELECT
            migration_type,
            COUNT(*)                                                AS customers,
            ROUND(AVG(total_lifetime_spend)::NUMERIC, 0)           AS avg_ltv
        FROM public.cust_master_profile
        GROUP BY migration_type
        ORDER BY customers DESC
    """)
    metrics["migration"] = [
        {"type": r[0], "customers": int(r[1] or 0), "avg_ltv": int(r[2] or 0)}
        for r in cur.fetchall()
    ]

    # ── 9. Top zones ──────────────────────────────────────────────────────────
    cur.execute("""
        SELECT
            consumer_zone,
            COUNT(*)                                                AS customers,
            ROUND(AVG(total_lifetime_spend)::NUMERIC, 0)           AS avg_ltv,
            COUNT(*) FILTER (WHERE churn_risk = 'High')            AS high_churn,
            ROUND(COUNT(*) FILTER (WHERE customer_type='Repeat')
                ::NUMERIC / NULLIF(COUNT(*),0) * 100, 1)           AS repeat_rate
        FROM public.cust_master_profile
        WHERE consumer_zone IS NOT NULL
        GROUP BY consumer_zone
        ORDER BY customers DESC
        LIMIT 5
    """)
    metrics["top_zones"] = [
        {
            "zone"       : r[0],
            "customers"  : int(r[1] or 0),
            "avg_ltv"    : int(r[2] or 0),
            "high_churn" : int(r[3] or 0),
            "repeat_rate": float(r[4] or 0),
        }
        for r in cur.fetchall()
    ]

    # ── 10. Top stores ────────────────────────────────────────────────────────
    cur.execute("""
        SELECT store_name, total_customers, repeat_customer_pct,
               avg_customer_ltv, retention_30d_pct, migrated_to_online
        FROM public.store_summary_mv
        ORDER BY total_customers DESC
        LIMIT 3
    """)
    metrics["top_stores"] = [
        {
            "store"         : r[0],
            "customers"     : int(r[1] or 0),
            "repeat_pct"    : float(r[2] or 0),
            "avg_ltv"       : int(r[3] or 0),
            "retention_30d" : float(r[4] or 0),
            "went_online"   : int(r[5] or 0),
        }
        for r in cur.fetchall()
    ]

    # ── 11. Cannot Lose alert — top 5 high value silent customers ─────────────
    cur.execute("""
        SELECT
            consumer_name, email, phone,
            consumer_city, total_lifetime_spend,
            days_since_last_purchase, top_category
        FROM public.cust_master_profile
        WHERE rfm_segment = 'Cannot Lose'
          AND days_since_last_purchase > 180
        ORDER BY total_lifetime_spend DESC NULLS LAST
        LIMIT 5
    """)
    metrics["cannot_lose_alerts"] = [
        {
            "name"    : r[0] or "—",
            "email"   : r[1] or "—",
            "phone"   : r[2] or "—",
            "city"    : r[3] or "—",
            "ltv"     : int(r[4] or 0),
            "days_silent": int(r[5] or 0),
            "category": r[6] or "—",
        }
        for r in cur.fetchall()
    ]

    # ── 12. Latest cohort M+1 retention ───────────────────────────────────────
    cur.execute("""
        SELECT TO_CHAR(cohort_month,'Mon YYYY'), cohort_size, retention_rate_pct
        FROM public.cust_monthly_cohort_mv
        WHERE months_since_first = 1
        ORDER BY cohort_month DESC LIMIT 1
    """)
    row = cur.fetchone()
    metrics["latest_cohort"] = {
        "cohort"         : row[0] if row else "N/A",
        "cohort_size"    : int(row[1]) if row else 0,
        "retention_m1"   : float(row[2]) if row else 0,
    }

    cur.close()
    log.info(f"✓ Metrics collected — {len(metrics)} sections")
    return metrics


# ── Step 2: Generate narrative with Groq ──────────────────────────────────────
def generate_narrative(metrics: dict) -> str:
    if not GROQ_API_KEY:
        log.warning("GROQ_API_KEY not set — using template")
        return build_template(metrics)

    log.info("Generating narrative with Groq...")

    # Send only summary metrics to Groq (not full customer lists — privacy)
    groq_metrics = {
        "report_date"       : metrics["report_date"],
        "report_day"        : metrics["report_day"],
        "overall"           : metrics["overall"],
        "top_categories"    : metrics["top_categories"],
        "top_single_sizes"  : metrics["top_single_sizes"],
        "top_size_combos"   : metrics["top_size_combos"][:3],
        "top_seasons"       : metrics["top_seasons"][:3],
        "aov_comparison"    : metrics["aov_comparison"],
        "migration"         : metrics["migration"],
        "top_zones"         : metrics["top_zones"][:3],
        "top_stores"        : metrics["top_stores"],
        "latest_cohort"     : metrics["latest_cohort"],
    }

    prompt = f"""You are a senior customer analytics manager at Libas, an Indian ethnic fashion brand.
Write a sharp, data-driven Daily Customer Pulse report for the leadership team.

STRICT RULES:
- Use Indian number format (Cr, L, K)
- Use ↑ for positive trends, ↓ for concerns
- Maximum 300 words total
- Use these exact section headers with emojis
- Be specific with numbers — no vague statements
- End with 2 concrete actions for today

SECTIONS TO INCLUDE:
📊 Overview (new + repeat customers yesterday, overall repeat rate, avg LTV)
🛍️ Category & Product Insights (top category, top sizes, top season)
💰 Revenue Intelligence (AOV new vs repeat, top zone by LTV)
🏪 Store Performance (top store highlight)
⚠️ Churn Alert (cannot lose count, action needed)
💡 Today's Actions (2 specific recommendations)

METRICS:
{json.dumps(groq_metrics, indent=2, default=str)}

Write the report now in plain text (no markdown headers, use the emoji headers above):"""

    try:
        response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type" : "application/json",
            },
            json={
                "model"      : "llama-3.3-70b-versatile",
                "messages"   : [{"role": "user", "content": prompt}],
                "temperature": 0.3,
                "max_tokens" : 700,
            },
            timeout=30,
        )

        if response.status_code != 200:
            log.error(f"Groq error {response.status_code}: {response.text}")
            return build_template(metrics)

        narrative = response.json()["choices"][0]["message"]["content"].strip()
        log.info("✓ Narrative generated")
        return narrative

    except Exception as e:
        log.error(f"Groq failed: {e} — using template")
        return build_template(metrics)


def build_template(metrics: dict) -> str:
    """Fallback template — no AI needed."""
    o   = metrics["overall"]
    tc  = metrics["top_categories"][0] if metrics["top_categories"] else {}
    ts  = metrics["top_single_sizes"][0] if metrics["top_single_sizes"] else {}
    tsz = metrics["top_size_combos"][0]  if metrics["top_size_combos"]  else {}
    tse = metrics["top_seasons"][0]      if metrics["top_seasons"]      else {}
    tz  = metrics["top_zones"][0]        if metrics["top_zones"]        else {}
    tst = metrics["top_stores"][0]       if metrics["top_stores"]       else {}
    co  = metrics["latest_cohort"]

    new_cx  = metrics["new_customers_yesterday"]
    rep_cx  = metrics["repeat_customers_yesterday"]
    aov     = {a["type"]: a for a in metrics["aov_comparison"]}
    cl      = metrics["cannot_lose_alerts"]

    lines = [
        f"📊 *Libas Customer Pulse — {metrics['report_date']} ({metrics['report_day']})*",
        "",
        f"📅 *Yesterday Summary ({metrics['yesterday']})*",
        f"• New Customers: {fmt(o['new_yesterday'])} | Repeat Active: {fmt(o['repeat_yesterday'])}",
        f"• Total Base: {fmt(o['total_customers'])} | Overall Repeat Rate: {o['repeat_rate_pct']}%",
        f"• Avg LTV: {fmtr(o['avg_ltv'])} | Same-Month Repeat: {o['same_month_repeat_pct']}%",
        "",
    ]

    if new_cx:
        lines.append("🆕 *New Customers Yesterday (Top 5)*")
        for c in new_cx:
            lines.append(f"  • {c['name']} | {c['city']} ({c['zone']}) | {c['channel']} | {c['category']}")
        lines.append("")

    if rep_cx:
        lines.append("🔄 *Repeat Customers Active Yesterday (Top 5 by LTV)*")
        for c in rep_cx:
            lines.append(f"  • {c['name']} | {c['city']} | LTV: {fmtr(c['ltv'])} | {c['orders']} orders | {c['segment']}")
        lines.append("")

    lines += [
        "🛍️ *Category & Product Intelligence*",
        f"• Top Category: {tc.get('category','—')} — {fmt(tc.get('customers',0))} customers | Repeat Rate: {tc.get('repeat_rate',0)}%",
        f"• Top Single Size: {ts.get('size','—')} ({fmt(ts.get('customers',0))} customers)",
        f"• Top Size Combo: {tsz.get('size','—')} ({fmt(tsz.get('customers',0))} customers)",
        f"• Top Season: {tse.get('season','—')} ({fmt(tse.get('customers',0))} customers)",
        "",
        "💰 *Revenue Intelligence*",
    ]

    for a in metrics["aov_comparison"]:
        lines.append(f"  • {a['type']} AOV — EBO: {fmtr(a['ebo_aov'])} | Online: {fmtr(a['online_aov'])} | Blended: {fmtr(a['blended_aov'])}")

    lines += [
        f"• Top Zone by Customers: {tz.get('zone','—')} — {fmt(tz.get('customers',0))} cx | Avg LTV: {fmtr(tz.get('avg_ltv',0))} | Repeat: {tz.get('repeat_rate',0)}%",
        "",
        "🏪 *Top Store*",
        f"• {tst.get('store','—')} — {fmt(tst.get('customers',0))} customers | Repeat: {tst.get('repeat_pct',0)}% | Avg LTV: {fmtr(tst.get('avg_ltv',0))} | Went Online: {fmt(tst.get('went_online',0))}",
        "",
        "📈 *Cohort Retention*",
        f"• {co.get('cohort','—')} cohort ({fmt(co.get('cohort_size',0))} customers) → M+1 Retention: {co.get('retention_m1',0)}%",
        "",
        f"⚠️ *Churn Alerts — Cannot Lose Customers ({fmt(o['cannot_lose_count'])} total)*",
    ]

    if cl:
        for c in cl:
            lines.append(f"  • {c['name']} | {c['city']} | LTV: {fmtr(c['ltv'])} | Silent {c['days_silent']} days | {c['category']}")
    else:
        lines.append("  • No critical churn alerts today ✓")

    lines += [
        "",
        "💡 *Today's Recommended Actions*",
        f"  1️⃣  Re-engage top {fmt(o['cannot_lose_count'])} 'Cannot Lose' customers — high LTV, going quiet. Send personalised offer.",
        f"  2️⃣  {tz.get('zone','NORTH')} zone has {fmt(tz.get('high_churn',0))} high-churn customers — target with {tc.get('category','KURTA SET')} seasonal campaign.",
    ]

    return "\n".join(lines)


# ── Step 3: Send to Slack ─────────────────────────────────────────────────────
def send_to_slack(narrative: str):
    if not SLACK_TOKEN:
        log.warning("SLACK_TOKEN not set — skipping Slack")
        return

    log.info(f"Sending to Slack #{SLACK_CHANNEL}...")
    try:
        from slack_sdk import WebClient
        client     = WebClient(token=SLACK_TOKEN)
        channel_id = get_channel_id_by_name(SLACK_TOKEN, SLACK_CHANNEL)
        client.chat_postMessage(
            channel = channel_id,
            text    = narrative,
            mrkdwn  = True,
        )
        log.info("✓ Sent to Slack")
    except Exception as e:
        log.error(f"Slack failed: {e}")


# ── Step 4: Send Email ────────────────────────────────────────────────────────
def send_email(narrative: str, metrics: dict):
    if not os.path.exists(EMAIL_TOKEN_PATH):
        log.warning("Email token not found — skipping email")
        return

    log.info(f"Sending email to: {EMAIL_RECIPIENTS}")
    try:
        email_module = __import__(EMAIL_CLASS_FILE)
        mailer       = email_module.SMTP(
            username   = EMAIL_SENDER,
            token_path = EMAIL_TOKEN_PATH,
        )

        # Build rich HTML email
        new_cx_rows = ""
        for c in metrics.get("new_customers_yesterday", []):
            new_cx_rows += f"""
            <tr>
                <td style="padding:6px 10px;border-bottom:1px solid #eee">{c['name']}</td>
                <td style="padding:6px 10px;border-bottom:1px solid #eee">{c['email']}</td>
                <td style="padding:6px 10px;border-bottom:1px solid #eee">{c['city']}, {c['zone']}</td>
                <td style="padding:6px 10px;border-bottom:1px solid #eee">{c['channel']}</td>
                <td style="padding:6px 10px;border-bottom:1px solid #eee">{c['category']}</td>
            </tr>"""

        rep_cx_rows = ""
        for c in metrics.get("repeat_customers_yesterday", []):
            rep_cx_rows += f"""
            <tr>
                <td style="padding:6px 10px;border-bottom:1px solid #eee">{c['name']}</td>
                <td style="padding:6px 10px;border-bottom:1px solid #eee">{c['city']}, {c['zone']}</td>
                <td style="padding:6px 10px;border-bottom:1px solid #eee">{fmtr(c['ltv'])}</td>
                <td style="padding:6px 10px;border-bottom:1px solid #eee">{c['orders']}</td>
                <td style="padding:6px 10px;border-bottom:1px solid #eee">{c['segment']}</td>
                <td style="padding:6px 10px;border-bottom:1px solid #eee">{c['category']}</td>
            </tr>"""

        churn_rows = ""
        for c in metrics.get("cannot_lose_alerts", []):
            churn_rows += f"""
            <tr>
                <td style="padding:6px 10px;border-bottom:1px solid #eee">{c['name']}</td>
                <td style="padding:6px 10px;border-bottom:1px solid #eee">{c['email']}</td>
                <td style="padding:6px 10px;border-bottom:1px solid #eee">{c['phone']}</td>
                <td style="padding:6px 10px;border-bottom:1px solid #eee">{c['city']}</td>
                <td style="padding:6px 10px;border-bottom:1px solid #eee">{fmtr(c['ltv'])}</td>
                <td style="padding:6px 10px;border-bottom:1px solid #eee;color:#dc2626;font-weight:600">{c['days_silent']} days</td>
                <td style="padding:6px 10px;border-bottom:1px solid #eee">{c['category']}</td>
            </tr>"""

        o   = metrics["overall"]
        tc  = metrics["top_categories"][0] if metrics["top_categories"] else {}
        ts  = metrics["top_single_sizes"][0] if metrics["top_single_sizes"] else {}
        tsz = metrics["top_size_combos"][0]  if metrics["top_size_combos"]  else {}
        tse = metrics["top_seasons"][0]      if metrics["top_seasons"]      else {}

        html_body = f"""
        <html>
        <body style="font-family:Arial,sans-serif;max-width:800px;margin:0 auto;padding:20px;color:#1a1a2e">

          <div style="background:linear-gradient(135deg,#0c8de4,#0a3f6c);padding:24px;border-radius:12px;margin-bottom:24px">
            <h1 style="color:#fff;margin:0;font-size:22px">📊 Libas Customer Pulse</h1>
            <p style="color:#bae0fd;margin:6px 0 0">{metrics['report_date']} — {metrics['report_day']}</p>
          </div>

          <!-- AI Narrative -->
          <div style="background:#f0f7ff;border-left:4px solid #0c8de4;padding:16px 20px;border-radius:0 8px 8px 0;margin-bottom:24px">
            <pre style="white-space:pre-wrap;font-family:Arial,sans-serif;font-size:13px;line-height:1.7;margin:0;color:#333">{narrative}</pre>
          </div>

          <!-- Summary KPIs -->
          <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-bottom:24px">
            {"".join([f'''<div style="background:#fff;border:1px solid #e2e6f0;border-radius:8px;padding:14px;text-align:center">
              <div style="font-size:11px;color:#9aa3bc;text-transform:uppercase;letter-spacing:0.05em">{label}</div>
              <div style="font-size:22px;font-weight:700;color:{color};margin-top:4px">{value}</div>
            </div>''' for label, value, color in [
                ("Total Customers",  fmt(o['total_customers']),   "#0c8de4"),
                ("New Yesterday",    fmt(o['new_yesterday']),     "#16a34a"),
                ("Repeat Yesterday", fmt(o['repeat_yesterday']),  "#0d9488"),
                ("Repeat Rate",      f"{o['repeat_rate_pct']}%", "#7c3aed"),
                ("High Churn",       fmt(o['high_churn_count']),  "#dc2626"),
                ("Avg LTV",          fmtr(o['avg_ltv']),          "#d97706"),
            ]])}
          </div>

          <!-- Top Insights row -->
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:24px">
            <div style="background:#fff;border:1px solid #e2e6f0;border-radius:8px;padding:16px">
              <div style="font-size:12px;font-weight:700;color:#5a6480;text-transform:uppercase;margin-bottom:10px">🛍️ Product Intelligence</div>
              <div style="font-size:13px;line-height:2">
                <div>Top Category: <strong>{tc.get('category','—')}</strong> ({fmt(tc.get('customers',0))} cx, {tc.get('repeat_rate',0)}% repeat)</div>
                <div>Top Single Size: <strong>{ts.get('size','—')}</strong> ({fmt(ts.get('customers',0))} cx)</div>
                <div>Top Size Combo: <strong>{tsz.get('size','—')}</strong> ({fmt(tsz.get('customers',0))} cx)</div>
                <div>Top Season: <strong>{tse.get('season','—')}</strong> ({fmt(tse.get('customers',0))} cx)</div>
              </div>
            </div>
            <div style="background:#fff;border:1px solid #e2e6f0;border-radius:8px;padding:16px">
              <div style="font-size:12px;font-weight:700;color:#5a6480;text-transform:uppercase;margin-bottom:10px">💰 AOV Comparison</div>
              {"".join([f'''<div style="display:flex;justify-content:space-between;padding:5px 0;border-bottom:1px solid #f1f3f8;font-size:13px">
                <span>{a['type']}</span>
                <span>EBO: <strong>{fmtr(a['ebo_aov'])}</strong> | Online: <strong>{fmtr(a['online_aov'])}</strong></span>
              </div>''' for a in metrics["aov_comparison"]])}
            </div>
          </div>

          <!-- New Customers Table -->
          {"f'''<div style=margin-bottom:24px><div style=font-size:14px;font-weight:700;margin-bottom:10px>🆕 New Customers Yesterday</div><table style=width:100%;border-collapse:collapse;font-size:12px><thead><tr style=background:#f1f3f8><th style=padding:8px 10px;text-align:left>Name</th><th style=padding:8px 10px;text-align:left>Email</th><th style=padding:8px 10px;text-align:left>Location</th><th style=padding:8px 10px;text-align:left>Channel</th><th style=padding:8px 10px;text-align:left>Category</th></tr></thead><tbody>{new_cx_rows}</tbody></table></div>'''" if new_cx_rows else ""}

          <!-- Repeat Customers Table -->
          {"f'''<div style=margin-bottom:24px><div style=font-size:14px;font-weight:700;margin-bottom:10px>🔄 Top Repeat Customers Yesterday</div><table style=width:100%;border-collapse:collapse;font-size:12px><thead><tr style=background:#f1f3f8><th style=padding:8px 10px;text-align:left>Name</th><th style=padding:8px 10px;text-align:left>Location</th><th style=padding:8px 10px;text-align:left>LTV</th><th style=padding:8px 10px;text-align:left>Orders</th><th style=padding:8px 10px;text-align:left>Segment</th><th style=padding:8px 10px;text-align:left>Category</th></tr></thead><tbody>{rep_cx_rows}</tbody></table></div>'''" if rep_cx_rows else ""}

          <!-- Cannot Lose Alert Table -->
          {"f'''<div style=margin-bottom:24px;border:1px solid #fca5a5;border-radius:8px;padding:16px><div style=font-size:14px;font-weight:700;color:#dc2626;margin-bottom:10px>⚠️ Cannot Lose — Immediate Action Required</div><table style=width:100%;border-collapse:collapse;font-size:12px><thead><tr style=background:#fee2e2><th style=padding:8px 10px;text-align:left>Name</th><th style=padding:8px 10px;text-align:left>Email</th><th style=padding:8px 10px;text-align:left>Phone</th><th style=padding:8px 10px;text-align:left>City</th><th style=padding:8px 10px;text-align:left>LTV</th><th style=padding:8px 10px;text-align:left>Silent Since</th><th style=padding:8px 10px;text-align:left>Category</th></tr></thead><tbody>{churn_rows}</tbody></table></div>'''" if churn_rows else ""}

          <div style="background:#f8f9fc;border-radius:8px;padding:12px 16px;font-size:11px;color:#9aa3bc;margin-top:20px;text-align:center">
            Auto-generated by Customer Journey Tool · Data refreshed at 3:00 AM IST · Report sent at 9:00 AM IST
          </div>

        </body>
        </html>
        """

        subject = f"📊 Libas Customer Pulse — {metrics['report_date']} ({metrics['report_day']})"
        mailer.send_msg(
            to         = EMAIL_RECIPIENTS,
            cc         = EMAIL_CC,
            subject    = subject,
            msgType    = "HTML",
            msg        = html_body,
            attachment = [],
        )
        log.info("✓ Email sent")

    except Exception as e:
        log.error(f"Email failed: {e}")


# ── Main ──────────────────────────────────────────────────────────────────────
def run():
    import time
    start = time.time()

    log.info("=" * 60)
    log.info("  LIBAS — DAILY PULSE AGENT")
    log.info(f"  {date.today().strftime('%A, %d %B %Y')}  |  {datetime.now().strftime('%H:%M:%S')}")
    log.info("=" * 60)

    try:
        conn = psycopg2.connect(**PG, connect_timeout=15)
        log.info("Connected to PostgreSQL")
    except Exception as e:
        log.critical(f"DB connection failed: {e}")
        sys.exit(1)

    try:
        metrics = collect_metrics(conn)
    except Exception as e:
        log.critical(f"Metrics collection failed: {e}")
        conn.close()
        sys.exit(1)
    finally:
        conn.close()

    narrative = generate_narrative(metrics)

    log.info("\n--- NARRATIVE ---")
    log.info(narrative)
    log.info("---\n")

    send_to_slack(narrative)
    send_email(narrative, metrics)

    log.info(f"✓ Pulse agent done in {round(time.time()-start,1)}s")
    log.info("=" * 60)


if __name__ == "__main__":
    run()