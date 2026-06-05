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
from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.prebuilt import create_react_agent

from .tools import build_tools, _jsonable
from .guardrails import sanitize_sql, enforce_store_scope, run_readonly

log = logging.getLogger("agent")

# Primary model: fast and cheap, good for most questions.
GROQ_MODEL = os.getenv("GROQ_AGENT_MODEL", "llama-3.3-70b-versatile")
# Fallback model used ONLY when the primary model emits a malformed tool call
# (Groq 400 "tool call validation failed"). This happens when the SQL argument
# is full of escaped double-quotes (item_master camelCase columns like "itemNo",
# "shopifySKU"). gpt-oss-120b handles structured tool-call JSON far more reliably.
GROQ_FALLBACK_MODEL = os.getenv("GROQ_AGENT_FALLBACK_MODEL", "openai/gpt-oss-120b")
# Model for the single-call text-to-SQL fallback. Deliberately a SMALL, cheap model:
# Groq rate limits are PER-MODEL, so when the big agentic model hits its daily token
# cap (free tier), this one still has its own (much larger) budget and keeps answering.
GROQ_SQL_MODEL = os.getenv("GROQ_SQL_MODEL", "llama-3.1-8b-instant")

_BASE_INSTRUCTIONS = """You are the Libas Customer Intelligence Agent — an expert analyst for an
Indian ethnic-fashion brand selling Online (Shopify) and Offline (EBO stores).

SCOPE & STYLE (STRICT):
- You ONLY answer questions about Libas retail DATA: sales, revenue, quantity, customers, products/SKUs,
  categories, sizes, stores and trends — things answerable from the database.
- If the question is off-topic, personal or behavioural, general knowledge, an opinion, a greeting,
  or NOT answerable from this data (e.g. "how are you", "tell me a joke", weather, write code), do NOT
  call any tool. Reply with ONE short sentence:
  "I can only answer questions about this store's sales, products and customers."
- Keep EVERY answer to 1–2 short sentences. Lead with the number/fact. No preamble, no filler,
  no bullet lists unless the user explicitly asks for a list.

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


_OUT_OF_SCOPE_MSG = "I can only answer questions about this store's sales, products and customers."


class _OutOfScope(Exception):
    """The question is not answerable from the database (off-topic / behavioural / etc.)."""


def _friendly_error(err: str | None) -> str:
    """Map a technical error to a short, user-facing message."""
    s = (err or "").lower()
    if any(k in s for k in ("rate limit", "rate_limit", "tokens per day", "tpd", "429")):
        return "I've reached today's AI usage limit. Please try again later."
    if "timeout" in s or "timed out" in s:
        return "That took too long — please try a simpler question."
    if "groq_api_key" in s or "api key" in s or "401" in s:
        return "The AI service isn't configured right now. Please contact support."
    return "Sorry, I couldn't answer that. Please rephrase and try again."


def _direct_sql(question: str, store_name: str | None, api_key: str):
    """Single-call text-to-SQL fallback used when the agentic (tool-calling) path
    fails. ONE Groq completion returns plain SQL, which we run under the same
    read-only guardrails. No tool-calling and no multi-step loop, so it's robust
    and far kinder to free-tier rate limits. Returns (sql, columns, rows)."""
    try:
        from api.routers.agent import DB_SCHEMA
    except Exception:
        DB_SCHEMA = ""

    sys = (
        "You are an expert PostgreSQL query writer for Libas analytics (Indian ethnic "
        "fashion; Online=Shopify, Offline=EBO stores).\n"
        "Convert the user's question into ONE PostgreSQL SELECT or WITH query.\n"
        "Return ONLY the SQL — no markdown, no ``` fences, no explanation.\n"
        "If the question is NOT answerable from this retail data (off-topic, greeting, "
        "behavioural, general knowledge, opinion), output exactly: OUT_OF_SCOPE\n"
        "item_master has camelCase columns that MUST be double-quoted: \"itemNo\", "
        "\"shopifySKU\", \"itemCategoryCode\", \"subCategory\", \"sizeNew\", \"seasonNew\", "
        "\"designType\", \"occassion\", \"imageUrl\".\n"
        "Use fn_clean_combo() on BOTH sides of customer joins. City/Zone values are UPPERCASE.\n\n"
        "== DATABASE SCHEMA ==\n" + DB_SCHEMA
    )
    if store_name:
        sys += (
            f"\n\nSTORE LOCK (STRICT): Only answer about \"{store_name}\". "
            f"Filter cust_ebo_salescombo_view by TRIM(invoice_associate_name) = '{store_name}' "
            f"and cust_master_profile by primary_store = '{store_name}'. "
            f"Ignore any other store the user names."
        )

    # Single completion on the small SQL model (its own per-model token budget).
    llm = ChatGroq(model=GROQ_SQL_MODEL, temperature=0, api_key=api_key, timeout=60, max_tokens=900)
    resp = llm.invoke([SystemMessage(content=sys), HumanMessage(content=question)])
    raw = _content_to_text(resp.content).strip()

    if not raw or "OUT_OF_SCOPE" in raw.upper():
        raise _OutOfScope()

    clean = sanitize_sql(raw)                       # strip markdown, SELECT-only, allow-list, LIMIT
    clean = enforce_store_scope(clean, store_name)  # hard store isolation
    cols, rows = run_readonly(clean)
    return clean, cols, rows


def _content_to_text(content) -> str:
    """Coerce an LLM message's content to plain text.
    Reasoning models (e.g. gpt-oss) can return content as a list of blocks/objects
    instead of a string; the UI and JSON response need a plain string."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                # skip the model's internal reasoning — only keep visible text
                if block.get("type") in ("reasoning", "thinking"):
                    continue
                parts.append(block.get("text") or block.get("content") or "")
            else:
                parts.append(getattr(block, "text", "") or "")
        return "".join(parts).strip()
    return str(content or "")


def _is_tool_call_error(e: Exception) -> bool:
    """True when Groq rejected a malformed tool call (recoverable by a model swap)."""
    s = str(e).lower()
    return ("tool call validation failed" in s
            or "tool_use_failed" in s
            or "failed_generation" in s)


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
    prompt = _system_prompt(store_name)
    messages = _to_messages(history) + [("user", question)]

    # Try the primary model first; if Groq rejects the tool call as malformed
    # (heavily-escaped SQL the small model can't serialise), retry once on the
    # more capable fallback model. temperature=0 means a plain retry on the same
    # model would just fail identically — only a model swap can recover.
    models = [GROQ_MODEL]
    if GROQ_FALLBACK_MODEL and GROQ_FALLBACK_MODEL != GROQ_MODEL:
        models.append(GROQ_FALLBACK_MODEL)

    result, answer, status, error = None, "", "error", None
    used_model = GROQ_MODEL
    for i, model in enumerate(models):
        ctx.clear()                       # discard any partial state from a failed attempt
        used_model = model
        try:
            llm = ChatGroq(model=model, temperature=0, api_key=api_key, timeout=60)
            agent = create_react_agent(llm, build_tools(store_name, ctx), prompt=prompt)
            result = agent.invoke({"messages": messages}, config={"recursion_limit": 14})
            status, error = "success", None
            break
        except Exception as e:
            error = str(e)[:500]
            is_last = i == len(models) - 1
            log.warning("agent attempt %d/%d model=%s failed: %s",
                        i + 1, len(models), model, error)
            # Only fall through to the fallback for malformed-tool-call (400) errors;
            # other failures (timeout, auth, recursion limit) won't be helped by a swap.
            if is_last or not _is_tool_call_error(e):
                break

    tool_calls = []
    if result is not None:
        # collect a light trace of tool usage for observability
        for m in result.get("messages", []):
            for tc in (getattr(m, "tool_calls", None) or []):
                tool_calls.append(tc.get("name"))
        for m in reversed(result.get("messages", [])):
            if getattr(m, "type", "") == "ai" and getattr(m, "content", ""):
                answer = _content_to_text(m.content)
                break

    # Keep both paths: if the agentic (tool-calling) path failed entirely — tool-call
    # validation, free-tier rate limit, recursion limit, etc. — fall back to a single
    # text-to-SQL call so the user still gets the data (table/SQL/CSV/chart).
    if status != "success":
        agentic_error = error
        try:
            sql, cols, rows = _direct_sql(question, store_name, api_key)
            ctx["sql"]     = sql
            ctx["columns"] = cols
            ctx["rows"]    = [[_jsonable(v) for v in r] for r in rows]
            status, error  = "success", None
            used_model    += " → direct-sql"
            log.info("recovered via direct-sql fallback (agentic error: %s)",
                     (agentic_error or "")[:160])
        except _OutOfScope:
            # Off-topic question — answer politely, don't surface a scary error.
            answer, status, error = _OUT_OF_SCOPE_MSG, "success", None
        except Exception as e:
            log.warning("direct-sql fallback also failed: %s", str(e)[:300])
            # keep the original agentic error for the user

    elapsed = round(time.time() - t0, 2)
    log.info("agent store=%s model=%s tools=%s rows=%s %.2fs q=%r",
             store_name or "ALL", used_model, tool_calls,
             len(ctx.get("rows", [])), elapsed, question[:120])

    return {
        "status"     : status,
        "error"      : _friendly_error(error) if status == "error" else None,
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
