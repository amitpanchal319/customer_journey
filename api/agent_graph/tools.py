# api/agent_graph/tools.py
# ----------------------------------------------------------------
# Tools the agent can call. Built per-request via build_tools() so they
# can record results into a request-scoped context (ctx) for the API
# response (table, sql, image, csv).
# ----------------------------------------------------------------

import io
import json
import base64
from datetime import date, datetime
from decimal import Decimal

from langchain_core.tools import tool

from .guardrails import sanitize_sql, enforce_store_scope, run_readonly, GuardrailError


def _jsonable(v):
    if isinstance(v, Decimal):            return float(v)
    if isinstance(v, (date, datetime)):   return str(v)
    return v


def build_tools(store_name, ctx):
    """ctx: a dict the tools populate (sql, columns, rows, image) for the API layer."""

    @tool
    def query_database(sql: str) -> str:
        """Run ONE read-only PostgreSQL SELECT (or WITH) query against the Libas warehouse
        and return the rows as JSON. Write the SQL using the schema in the system prompt.
        Use fn_clean_combo() on both sides of customer joins. If the result is an ERROR,
        read the message and call this tool again with corrected SQL."""
        try:
            clean = sanitize_sql(sql)
            clean = enforce_store_scope(clean, store_name)
            cols, rows = run_readonly(clean)
        except GuardrailError as e:
            return f"ERROR (blocked by guardrail): {e}"
        except Exception as e:
            return f"ERROR (sql failed): {str(e)[:400]}"

        # record full result for the API response / CSV / chart
        ctx["sql"]     = clean
        ctx["columns"] = cols
        ctx["rows"]    = [[_jsonable(v) for v in r] for r in rows]

        # return a compact preview to the model (keep tokens small)
        preview = ctx["rows"][:25]
        return json.dumps(
            {"columns": cols, "row_count": len(rows), "rows_preview": preview},
            default=str,
        )[:4000]

    @tool
    def make_chart(chart_type: str = "bar", title: str = "") -> str:
        """Render the MOST RECENT query result as a chart image (chart_type: bar | line | pie).
        Call this only after query_database, when the user asks for a chart / graph / visual / image."""
        cols = ctx.get("columns")
        rows = ctx.get("rows")
        if not cols or not rows:
            return "ERROR: no query result to chart yet — run query_database first."
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt

            # label = first text column; values = first numeric column
            label_idx = next((i for i, c in enumerate(cols)
                              if any(isinstance(r[i], str) for r in rows[:5])), 0)
            num_idx = next((i for i in range(len(cols))
                            if i != label_idx and all(isinstance(r[i], (int, float)) or r[i] is None
                                                      for r in rows[:5])), None)
            if num_idx is None:
                return "ERROR: result has no numeric column to chart."

            labels = [str(r[label_idx]) for r in rows[:20]]
            values = [float(r[num_idx] or 0) for r in rows[:20]]

            fig, ax = plt.subplots(figsize=(7, 4), dpi=110)
            if chart_type == "line":
                ax.plot(labels, values, marker="o", color="#617038")
            elif chart_type == "pie":
                ax.pie(values, labels=labels, autopct="%1.0f%%")
            else:
                ax.bar(labels, values, color="#617038")
            ax.set_title(title or f"{cols[num_idx]} by {cols[label_idx]}")
            if chart_type != "pie":
                ax.tick_params(axis="x", rotation=45, labelsize=8)
            fig.tight_layout()

            buf = io.BytesIO()
            fig.savefig(buf, format="png", bbox_inches="tight")
            plt.close(fig)
            ctx["image"] = base64.b64encode(buf.getvalue()).decode()
            return f"Chart created ({chart_type}) from {len(rows)} rows."
        except Exception as e:
            return f"ERROR (chart failed): {str(e)[:300]}"

    return [query_database, make_chart]
