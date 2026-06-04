# refresh_pipeline.py
# ----------------------------------------------------------------
# Daily data refresh pipeline for Customer Journey Tool
# Refreshes all 3 materialized views in correct dependency order
#
# Schedule: Windows Task Scheduler at 3:00 AM IST daily
# Location: Place in customer_journey/ root folder
#
# Setup Task Scheduler:
#   1. Open Task Scheduler → Create Basic Task
#   2. Name: "CJourney Daily Refresh"
#   3. Trigger: Daily at 3:00 AM
#   4. Action: Start a program
#      Program: C:\Users\AmitPanchal\anaconda3\envs\aiml_env\python.exe
#      Arguments: refresh_pipeline.py
#      Start in: D:\Backup\Libas_Py\customer_journey
#
# Logs saved to: logs/refresh_YYYY-MM-DD.log
# ----------------------------------------------------------------

import os
import sys
import time
import logging
import psycopg2
from datetime import datetime, date
from dotenv import load_dotenv

load_dotenv()

# ── Config ────────────────────────────────────────────────────────────────────
PG = {
    "host"    : os.getenv("PG_HOST",     "10.150.0.5"),
    "port"    : int(os.getenv("PG_PORT", "5432")),
    "dbname"  : os.getenv("PG_DATABASE", "Unicorn"),
    "user"    : os.getenv("PG_USER",     "Amit"),
    "password": os.getenv("PG_PASSWORD", "Amit@23200"),
}

# Refresh order — dependency matters, never change this order
VIEWS = [
    {
        "name"    : "cust_master_profile",
        "label"   : "Master Customer Profile",
        "expected_mins": 25,
    },
    {
        "name"    : "cust_monthly_cohort_mv",
        "label"   : "Monthly Cohort View",
        "expected_mins": 8,
    },
    {
        "name"    : "cust_monthly_active_mv",
        "label"   : "Monthly Active Combos View",
        "expected_mins": 3,
    },
    {
        "name"    : "store_summary_mv",
        "label"   : "Store Summary View",
        "expected_mins": 5,
    },
]

# ── Logging setup ─────────────────────────────────────────────────────────────
LOG_DIR = os.path.join(os.path.dirname(__file__), "logs")
os.makedirs(LOG_DIR, exist_ok=True)

log_file = os.path.join(LOG_DIR, f"refresh_{date.today().strftime('%Y-%m-%d')}.log")

logging.basicConfig(
    level   = logging.INFO,
    format  = "%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt = "%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(log_file, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ]
)
log = logging.getLogger(__name__)


# ── Helpers ───────────────────────────────────────────────────────────────────

def connect():
    """Create a PostgreSQL connection with autocommit for DDL statements."""
    conn = psycopg2.connect(**PG, connect_timeout=30)
    conn.autocommit = True
    # Remove all timeouts — refresh can take 30+ minutes
    cur = conn.cursor()
    cur.execute("SET statement_timeout = 0")
    cur.execute("SET lock_timeout = 0")
    cur.execute("SET idle_in_transaction_session_timeout = 0")
    cur.close()
    return conn


def get_row_count(cur, view_name: str) -> int:
    """Fast row count from pg_class — no full table scan."""
    cur.execute("""
        SELECT reltuples::BIGINT
        FROM pg_class
        WHERE relname = %s
    """, (view_name,))
    row = cur.fetchone()
    return row[0] if row else 0


def fmt_duration(seconds: float) -> str:
    """Format seconds into human readable string."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    mins = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{mins}m {secs}s"


def create_refresh_log_table(cur):
    """Create refresh_log table if it doesn't exist."""
    cur.execute("""
        CREATE TABLE IF NOT EXISTS public.refresh_log (
            id              SERIAL PRIMARY KEY,
            run_at          TIMESTAMP DEFAULT NOW(),
            run_date        DATE      DEFAULT CURRENT_DATE,
            view_name       TEXT,
            status          TEXT,
            duration_secs   NUMERIC,
            rows_before     BIGINT,
            rows_after      BIGINT,
            error_message   TEXT
        )
    """)


def log_refresh_result(cur, view_name, status, duration_secs,
                        rows_before, rows_after, error_message=None):
    """Insert refresh result into audit log table."""
    cur.execute("""
        INSERT INTO public.refresh_log
            (view_name, status, duration_secs, rows_before, rows_after, error_message)
        VALUES (%s, %s, %s, %s, %s, %s)
    """, (view_name, status, round(duration_secs, 1),
          rows_before, rows_after, error_message))


def refresh_view(cur, view: dict) -> dict:
    """
    Refresh a single materialized view.
    Returns result dict with status, duration, row counts.
    Uses CONCURRENTLY so the view stays readable during refresh.
    """
    name  = view["name"]
    label = view["label"]

    log.info(f"Starting refresh: {label} ({name})")

    rows_before = get_row_count(cur, name)
    start       = time.time()

    try:
        cur.execute(
            f"REFRESH MATERIALIZED VIEW CONCURRENTLY public.{name}"
        )
        duration   = time.time() - start
        rows_after = get_row_count(cur, name)

        log.info(
            f"  ✓ {label} refreshed in {fmt_duration(duration)} "
            f"| rows: {rows_before:,} → {rows_after:,}"
        )

        return {
            "view"        : name,
            "status"      : "success",
            "duration"    : duration,
            "rows_before" : rows_before,
            "rows_after"  : rows_after,
            "error"       : None,
        }

    except Exception as e:
        duration = time.time() - start
        log.error(f"  ✗ {label} FAILED after {fmt_duration(duration)}: {e}")

        return {
            "view"        : name,
            "status"      : "failed",
            "duration"    : duration,
            "rows_before" : rows_before,
            "rows_after"  : 0,
            "error"       : str(e),
        }


# ── Main ──────────────────────────────────────────────────────────────────────

def run():
    pipeline_start = time.time()

    log.info("=" * 60)
    log.info("  CUSTOMER JOURNEY — DAILY REFRESH PIPELINE")
    log.info(f"  Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log.info(f"  Database  : {PG['dbname']} on {PG['host']}")
    log.info("=" * 60)

    # ── Connect ───────────────────────────────────────────────────────────────
    try:
        conn = connect()
        cur  = conn.cursor()
        log.info("Connected to PostgreSQL")
    except Exception as e:
        log.critical(f"Cannot connect to PostgreSQL: {e}")
        sys.exit(1)

    # ── Ensure log table exists ───────────────────────────────────────────────
    try:
        create_refresh_log_table(cur)
        log.info("Refresh log table ready")
    except Exception as e:
        log.warning(f"Could not create log table: {e}")

    # ── Refresh each view in order ────────────────────────────────────────────
    results     = []
    all_success = True

    for i, view in enumerate(VIEWS, 1):
        log.info(f"\n[{i}/{len(VIEWS)}] {view['label']}")
        log.info(f"  Expected duration: ~{view['expected_mins']} minutes")

        result = refresh_view(cur, view)
        results.append(result)

        # Log to audit table
        try:
            log_refresh_result(
                cur,
                view_name     = result["view"],
                status        = result["status"],
                duration_secs = result["duration"],
                rows_before   = result["rows_before"],
                rows_after    = result["rows_after"],
                error_message = result["error"],
            )
        except Exception as e:
            log.warning(f"  Could not write to refresh_log: {e}")

        if result["status"] == "failed":
            all_success = False
            log.error(f"  Stopping pipeline — {view['label']} failed.")
            log.error(f"  Remaining views NOT refreshed to avoid stale data.")
            break

        # Small pause between views
        if i < len(VIEWS):
            log.info(f"  Waiting 5 seconds before next view...")
            time.sleep(5)

    # ── Summary ───────────────────────────────────────────────────────────────
    total_duration = time.time() - pipeline_start

    log.info("\n" + "=" * 60)
    log.info("  PIPELINE SUMMARY")
    log.info("=" * 60)

    for r in results:
        status_icon = "✓" if r["status"] == "success" else "✗"
        log.info(
            f"  {status_icon} {r['view']:<35} "
            f"{fmt_duration(r['duration']):<10} "
            f"{r['rows_after']:>10,} rows"
        )

    log.info(f"\n  Total duration : {fmt_duration(total_duration)}")
    log.info(f"  Completed at   : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    if all_success:
        log.info("  Status         : ✓ ALL VIEWS REFRESHED SUCCESSFULLY")
    else:
        failed = [r["view"] for r in results if r["status"] == "failed"]
        log.error(f"  Status         : ✗ FAILED — {', '.join(failed)}")

    log.info("=" * 60)

    cur.close()
    conn.close()

    # Exit with error code if failed — Task Scheduler can alert on this
    sys.exit(0 if all_success else 1)


if __name__ == "__main__":
    run()
    
    