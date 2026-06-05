# api/agent_graph/guardrails.py
# ----------------------------------------------------------------
# Safety layer for the agentic AI. Enforces read-only access at the
# application layer (until a read-only Postgres role is provisioned),
# caps result size, sets a statement timeout, and locks store scope.
# ----------------------------------------------------------------

import re
from sqlalchemy import text
from database.connection import engine

# Any of these keywords => reject (write / DDL / dangerous)
_FORBIDDEN = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE|CREATE|GRANT|REVOKE|"
    r"COPY|MERGE|CALL|DO|VACUUM|REINDEX|REFRESH|LOCK|SET|RESET|"
    r"pg_sleep|pg_read_file|pg_ls_dir|dblink|COMMENT)\b",
    re.IGNORECASE,
)

# Tables/views the agent is allowed to read. Anything else => reject.
_ALLOWED_TABLES = {
    "cust_master_profile",
    "cust_ebo_salescombo_view",
    "cust_osdcombo_view",
    "cust_monthly_cohort_mv",
    "cust_monthly_active_mv",
    "store_summary_mv",
    "item_master",
    "refresh_log",
}

# item_master camelCase columns that MUST be double-quoted in Postgres. Weak models
# (e.g. the small SQL-fallback model) often forget the quotes, so we add them here
# deterministically — Postgres folds an unquoted "itemCategoryCode" to lowercase and
# then errors "column ... does not exist".
_CAMEL_COLS = ("itemNo", "shopifySKU", "itemCategoryCode", "subCategory", "sizeNew",
               "seasonNew", "designType", "occassion", "imageUrl")


def quote_camel_columns(sql: str) -> str:
    """Wrap known camelCase item_master columns in double quotes if left unquoted.
    Case-insensitive match, canonical (correct-case) quoted replacement — so it also
    repairs wrong-cased names like 'itemcategorycode'."""
    for col in _CAMEL_COLS:
        sql = re.sub(rf'(?<!")\b{col}\b(?!")', f'"{col}"', sql, flags=re.IGNORECASE)
    return sql


DEFAULT_LIMIT       = 1000
STATEMENT_TIMEOUT_MS = 20000


class GuardrailError(Exception):
    pass


def sanitize_sql(sql: str, default_limit: int = DEFAULT_LIMIT) -> str:
    """Strip markdown, allow only a single SELECT/WITH, block writes/DDL, enforce LIMIT."""
    sql = re.sub(r"```sql\s*", "", sql, flags=re.IGNORECASE)
    sql = re.sub(r"```\s*", "", sql).strip().rstrip(";").strip()
    if not sql:
        raise GuardrailError("Empty SQL.")

    if ";" in sql:
        raise GuardrailError("Multiple statements are not allowed.")

    first = sql.split()[0].upper()
    if first not in ("SELECT", "WITH"):
        raise GuardrailError(f"Only SELECT/WITH queries are allowed (got {first}).")

    # Repair unquoted camelCase columns before any model's SQL reaches Postgres.
    sql = quote_camel_columns(sql)

    if _FORBIDDEN.search(sql):
        raise GuardrailError("Query contains a forbidden (write/DDL/unsafe) keyword.")

    # Table allow-list — every referenced relation must be known
    refs = re.findall(r"(?:FROM|JOIN)\s+(?:public\.)?\"?([a-zA-Z_][a-zA-Z0-9_]*)\"?", sql, re.IGNORECASE)
    unknown = {t.lower() for t in refs} - _ALLOWED_TABLES
    # allow CTE names: anything defined via "name AS (" is fine
    cte_names = {m.lower() for m in re.findall(r"([a-zA-Z_][a-zA-Z0-9_]*)\s+AS\s*\(", sql, re.IGNORECASE)}
    unknown -= cte_names
    if unknown:
        raise GuardrailError(f"Query references tables outside the allow-list: {sorted(unknown)}")

    if not re.search(r"\bLIMIT\s+\d+", sql, re.IGNORECASE):
        sql = f"{sql}\nLIMIT {default_limit}"
    return sql


def enforce_store_scope(sql: str, store_name: str | None) -> str:
    """Force every store filter to the locked store (store-page agent isolation)."""
    if not store_name:
        return sql
    sn = store_name.replace("'", "''")
    sql = re.sub(r"(invoice_associate_name\s*\)?\s*=\s*)'[^']*'", rf"\1'{sn}'", sql, flags=re.IGNORECASE)
    sql = re.sub(r"(primary_store\s*=\s*)'[^']*'",                 rf"\1'{sn}'", sql, flags=re.IGNORECASE)
    return sql


def run_readonly(sql: str, timeout_ms: int = STATEMENT_TIMEOUT_MS):
    """
    Execute inside a READ ONLY transaction with a statement timeout, then roll back.
    Any attempt to write fails at the DB level — defence in depth beyond sanitize_sql.
    Returns (columns, rows).
    """
    conn = engine.connect()
    trans = conn.begin()
    try:
        conn.execute(text("SET TRANSACTION READ ONLY"))
        conn.execute(text(f"SET LOCAL statement_timeout = '{timeout_ms}'"))
        res = conn.execute(text(sql))
        cols = list(res.keys())
        rows = [list(r) for r in res.fetchall()]
        return cols, rows
    finally:
        trans.rollback()
        conn.close()
