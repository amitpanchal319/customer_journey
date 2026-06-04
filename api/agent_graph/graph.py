# api/agent_graph/graph.py
# ----------------------------------------------------------------
# LangGraph agentic core for the Libas analytics agent.
#   - ReAct loop (reason -> call tools -> observe -> answer)
#   - Tools: query_database (NL->SQL with self-correction), make_chart (image)
#   - Guardrails: read-only execution, LIMIT/timeout, table allow-list, store lock
#   - Short-term memory: conversation history is threaded into the graph
#   - Observability: structured per-step logging
# Long-term memory (pgvector), Langfuse tracing and the eval suite plug in here.
# ----------------------------------------------------------------

import os
import time
import logging

from langchain_groq import ChatGroq
from langgraph.prebuilt import create_react_agent

from .tools import build_tools

log = logging.getLogger("agent")

GROQ_MODEL = "llama-3.3-70b-versatile"

_BASE_INSTRUCTIONS = """You are the Libas Customer Intelligence Agent — an expert analyst for an
Indian ethnic-fashion brand selling Online (Shopify) and Offline (EBO stores).

HOW YOU WORK:
- To answer ANY data question, call the `query_database` tool with a single PostgreSQL SELECT/WITH query.
- If the tool returns an ERROR, read it and call `query_database` again with corrected SQL. Never give up after one error.
- You may run several queries to build a multi-step answer (e.g. compute a cohort, then analyse it).
- After you have the data, reply in clear plain English with the key numbers (₹ in Indian format, e.g. ₹1.2L, ₹3.4Cr).
- If the user asks for a chart / graph / visual / image of NUMBERS, call `make_chart` AFTER getting the data.
- If the user asks about a PRODUCT / SKU image or "what does X look like", SELECT item_master."imageUrl"
  (plus description/category) — the UI renders image URLs as thumbnails automatically. Join EBO via
  cust_ebo_salescombo_view.barcode = item_master.ean, Shopify via cust_osdcombo_view.client_sku_id_ean = item_master."itemNo".
- Be concise and business-focused. Do not invent numbers — only state what the queries returned.

RULES:
- Read-only: you can only read data (SELECT). Never attempt to modify anything.
- Monetary values are in ₹. City / Zone values are UPPERCASE. Use fn_clean_combo() on BOTH sides of customer joins.
- item_master has camelCase columns created with quotes — you MUST double-quote them in SQL:
  "imageUrl", "shopifySKU", "itemCategoryCode", "subCategory", "sizeNew", "seasonNew", "designType", "occassion".
  (Unquoted imageUrl becomes lowercase 'imageurl' and fails.)
- "this month" / "current month" means the latest month WITH DATA:
  DATE_TRUNC('month', invoice_date) = (SELECT DATE_TRUNC('month', MAX(invoice_date)) FROM public.cust_ebo_salescombo_view)
"""


def _system_prompt(store_name):
    # Lazy import avoids a circular import with api.routers.agent
    try:
        from api.routers.agent import DB_SCHEMA
    except Exception:
        DB_SCHEMA = ""
    prompt = _BASE_INSTRUCTIONS + "\n\n== DATABASE SCHEMA ==\n" + DB_SCHEMA
    if store_name:
        prompt += f"""

== STORE LOCK (STRICT) ==
You can ONLY answer about the store "{store_name}".
- Always filter cust_ebo_salescombo_view by TRIM(invoice_associate_name) = '{store_name}'.
- Always filter cust_master_profile by primary_store = '{store_name}'.
- If the user names any OTHER store, ignore it and still answer only for "{store_name}".
"""
    return prompt


def _to_messages(history):
    msgs = []
    for h in (history or [])[-6:]:
        role = h.get("role")
        content = h.get("content")
        if not role or not content:
            continue
        msgs.append(("user" if role == "user" else "assistant", content))
    return msgs


def run_agent(question: str, store_name: str | None = None, history: list | None = None) -> dict:
    """Run the agentic graph for one question and return a structured, UI-ready result."""
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        return {"status": "error", "error": "GROQ_API_KEY not configured",
                "answer": "", "sql": "", "columns": [], "rows": [], "row_count": 0}

    ctx = {}            # tools write results here
    t0 = time.time()
    llm = ChatGroq(model=GROQ_MODEL, temperature=0, api_key=api_key, timeout=60)
    tools = build_tools(store_name, ctx)
    agent = create_react_agent(llm, tools, prompt=_system_prompt(store_name))

    messages = _to_messages(history) + [("user", question)]

    tool_calls = []
    try:
        result = agent.invoke({"messages": messages}, config={"recursion_limit": 14})
        # collect a light trace of tool usage for observability
        for m in result.get("messages", []):
            for tc in (getattr(m, "tool_calls", None) or []):
                tool_calls.append(tc.get("name"))
        answer = ""
        for m in reversed(result.get("messages", [])):
            if getattr(m, "type", "") == "ai" and getattr(m, "content", ""):
                answer = m.content
                break
        status = "success"
        error = None
    except Exception as e:
        answer, status, error = "", "error", str(e)[:500]

    elapsed = round(time.time() - t0, 2)
    log.info("agent store=%s tools=%s rows=%s %.2fs q=%r",
             store_name or "ALL", tool_calls, len(ctx.get("rows", [])), elapsed, question[:120])

    return {
        "status"     : status,
        "error"      : error if status == "error" else None,
        "answer"     : answer,
        "sql"        : ctx.get("sql", ""),
        "columns"    : ctx.get("columns", []),
        "rows"       : ctx.get("rows", []),
        "row_count"  : len(ctx.get("rows", [])),
        "image"      : ctx.get("image"),          # base64 PNG or None
        "store_scope": store_name,
        "tools_used" : tool_calls,
        "elapsed_s"  : elapsed,
    }
