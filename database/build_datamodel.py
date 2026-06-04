# database/build_datamodel.py
# ----------------------------------------------------------------
# Builds the Customer Journey data model on PostgreSQL.
#
# Usage:
#     cd customer_journey
#     python database/build_datamodel.py
#
# Key fix: executes each SQL section as one atomic block — never
# splits on ";" which breaks dollar-quoted function bodies.
# Safe to re-run — all views use DROP IF EXISTS CASCADE.
# ----------------------------------------------------------------

import os
import sys
import time
import re
import psycopg2
from dotenv import load_dotenv

load_dotenv()

PG = {
    "host"    : os.getenv("PG_HOST",     "10.150.0.5"),
    "port"    : int(os.getenv("PG_PORT", "5432")),
    "dbname"  : os.getenv("PG_DATABASE", "Unicorn"),
    "user"    : os.getenv("PG_USER",     "Amit"),
    "password": os.getenv("PG_PASSWORD", "Amit@23200"),
}

SQL_FILE = os.path.join(os.path.dirname(__file__), "customer_journey_final_datamodel.sql")


def log(msg, level="INFO"):
    sym = {"INFO": "→", "OK": "✓", "WARN": "⚠", "ERROR": "✗"}
    print(f"  {sym.get(level,'·')} [{level}] {msg}")


def split_sql_sections(sql_text):
    """
    Split SQL into sections on SECTION markers in comments.
    Each section is executed as a single string — preserves
    dollar-quoted function bodies and DO $$ blocks intact.
    """
    # Split on the SECTION header comment lines
    pattern = r'(?=-- ={20,}\n-- SECTION \d+)'
    parts = re.split(pattern, sql_text, flags=re.MULTILINE)
    # Filter empty
    return [p.strip() for p in parts if p.strip()]


def run_section(cur, section_sql, label):
    """
    Execute a full section. For sections containing multiple
    independent DDL statements (indexes, SELECT queries) that
    are NOT dollar-quoted, we split carefully on lines that
    start a new top-level statement.
    """
    start = time.time()

    # Sections that must be run as ONE block (contain $$ bodies)
    atomic_keywords = [
        "CREATE OR REPLACE FUNCTION",
        "CREATE MATERIALIZED VIEW",
        "DO $$",
    ]

    is_atomic = any(kw in section_sql.upper() for kw in
                    ["CREATE OR REPLACE FUNCTION", "CREATE MATERIALIZED VIEW"])
    is_do_block = "DO $$" in section_sql or "DO\n$$" in section_sql

    if is_atomic or is_do_block:
        # Execute entire section as one statement
        cur.execute(section_sql)
        elapsed = round(time.time() - start, 1)
        log(f"{label} ({elapsed}s)", "OK")
        return 1, 0   # ok, errors

    # For non-atomic sections (index blocks, SELECT validations)
    # split carefully: only split on lines that start with known DDL/DML
    # keywords at column 0, after a semicolon
    statements = smart_split(section_sql)
    ok = err = 0
    for stmt in statements:
        stmt = stmt.strip()
        if not stmt or stmt.startswith("--"):
            continue
        try:
            cur.execute(stmt)
            ok += 1
        except psycopg2.errors.DuplicateTable:
            ok += 1   # index already exists — fine
        except psycopg2.errors.UndefinedObject:
            ok += 1   # unschedule of non-existent cron job — fine
        except psycopg2.errors.InvalidSchemaName as e:
            log(f"SKIPPED (pg_cron not installed): {stmt[:60]}", "WARN")
            ok += 1
        except psycopg2.errors.UndefinedFunction as e:
            log(f"SKIPPED (cron schema missing): {stmt[:60]}", "WARN")
            ok += 1
        except Exception as e:
            log(f"ERROR: {stmt[:80]}", "ERROR")
            log(f"       {str(e)[:120]}", "ERROR")
            err += 1

    elapsed = round(time.time() - start, 1)
    log(f"{label} — {ok} ok, {err} errors ({elapsed}s)",
        "OK" if err == 0 else "WARN")
    return ok, err


def smart_split(sql):
    """
    Split SQL text into individual statements by finding semicolons
    that are NOT inside dollar-quoted strings or single-quoted strings.
    """
    statements = []
    current    = []
    in_dollar  = False
    dollar_tag = ""
    i          = 0

    lines = sql.split("\n")
    for line in lines:
        stripped = line.strip()

        # Track dollar-quoting ($$  or $tag$)
        dollar_matches = re.findall(r'\$[A-Za-z0-9_]*\$', line)
        for dm in dollar_matches:
            if not in_dollar:
                in_dollar  = True
                dollar_tag = dm
            elif dm == dollar_tag:
                in_dollar  = False
                dollar_tag = ""

        current.append(line)

        # A line ending with ; outside dollar-quote = statement boundary
        if not in_dollar and stripped.endswith(";"):
            stmt = "\n".join(current).strip().rstrip(";")
            if stmt and not stmt.startswith("--"):
                statements.append(stmt)
            current = []

    # Catch any remainder without trailing semicolon
    remainder = "\n".join(current).strip()
    if remainder and not remainder.startswith("--"):
        statements.append(remainder)

    return statements


def run_build():
    if not os.path.exists(SQL_FILE):
        log(f"SQL file not found: {SQL_FILE}", "ERROR")
        log("Copy customer_journey_final_datamodel.sql into the database/ folder.", "ERROR")
        sys.exit(1)

    print("\n" + "=" * 60)
    print("  CUSTOMER JOURNEY — DATA MODEL BUILD")
    print("=" * 60)
    print(f"  Host     : {PG['host']}:{PG['port']}")
    print(f"  Database : {PG['dbname']}")
    print(f"  User     : {PG['user']}")
    print("=" * 60 + "\n")

    # ── Connect ───────────────────────────────────────────────────────────────
    try:
        conn = psycopg2.connect(**PG, connect_timeout=15)
        conn.autocommit = True
        cur  = conn.cursor()
        log("Connected to PostgreSQL", "OK")
    except Exception as e:
        log(f"Connection failed: {e}", "ERROR")
        sys.exit(1)

    # ── Read SQL ──────────────────────────────────────────────────────────────
    with open(SQL_FILE, "r", encoding="utf-8") as f:
        raw_sql = f.read()

    sections = split_sql_sections(raw_sql)
    log(f"Found {len(sections)} sections in SQL file\n", "INFO")

    total_ok  = 0
    total_err = 0

    section_labels = {
        1: "Section 1 : Utility Functions  (fn_clean_combo, fn_size_group)",
        2: "Section 2 : cust_master_profile  ← heaviest, may take 10–20 min",
        3: "Section 3 : cust_monthly_cohort_mv",
        4: "Section 4 : store_summary_mv",
        5: "Section 5 : pg_cron schedule  (skipped if not installed)",
        6: "Section 6 : Validation queries",
    }

    for i, section in enumerate(sections, 1):
        # Extract section number from header comment
        m = re.search(r'SECTION (\d+)', section)
        sec_num = int(m.group(1)) if m else i
        label = section_labels.get(sec_num, f"Section {sec_num}")

        print(f"\n  ── {label}")

        # Skip pg_cron section gracefully if cron schema missing
        if sec_num == 5:
            log("Checking if pg_cron is installed...", "INFO")
            try:
                cur.execute("SELECT 1 FROM pg_extension WHERE extname = 'pg_cron'")
                has_cron = cur.fetchone() is not None
            except Exception:
                has_cron = False

            if not has_cron:
                log("pg_cron not installed — skipping schedule setup.", "WARN")
                log("To enable: run  CREATE EXTENSION pg_cron;  as superuser, then re-run this script.", "WARN")
                total_ok += 1
                continue

        # Skip Section 6 validation queries — user runs these manually in pgAdmin
        if sec_num == 6:
            log("Validation queries — run manually in pgAdmin after build.", "INFO")
            total_ok += 1
            continue

        ok, err = run_section(cur, section, label)
        total_ok  += ok
        total_err += err

    # ── Final summary ─────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print(f"  BUILD COMPLETE")
    print(f"  ✓ Sections succeeded : {total_ok}")
    print(f"  ✗ Errors             : {total_err}")
    print("=" * 60)

    if total_err == 0:
        print("""
  ✓ Data model built successfully.

  Next steps:
  1. Open pgAdmin → run the validation queries from Section 6
     of customer_journey_final_datamodel.sql to verify row counts.
  2. Start the API:
         uvicorn api.main:app --reload --host 0.0.0.0 --port 8002
  3. Open Swagger UI:
         http://localhost:8002/docs
""")
    else:
        print(f"\n  ⚠ {total_err} error(s) above. Fix and re-run.\n")

    cur.close()
    conn.close()


if __name__ == "__main__":
    run_build()