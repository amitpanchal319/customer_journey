# Libas Agentic AI (LangGraph)

Production-oriented agentic analyst for the Libas warehouse. Replaces the single-shot
text-to-SQL agent with a reasoning + tool-calling loop.

## Architecture

```
POST /api/agent/v2/query  { question, store_name?, history[] }
        │
        ▼
  run_agent()  (graph.py)
        │   build per-request:  ChatGroq(llama-3.3-70b)  +  tools  +  system prompt(schema [+ store lock])
        ▼
  LangGraph create_react_agent  ── ReAct loop ──┐
        │  reason → call tool → observe → repeat │ (recursion_limit=14, self-corrects on SQL errors)
        ▼                                        │
   TOOLS (tools.py)                              │
     • query_database(sql)  → guardrails → read-only execute → rows (preview to model, full to ctx)
     • make_chart(type,title)→ matplotlib → base64 PNG into ctx["image"]
        │
        ▼
  Response: { answer, sql, columns, rows, row_count, image?, tools_used, elapsed_s, status }
```

## Components
- **graph.py** — LLM, system prompt (schema + optional store lock), ReAct graph, orchestration, logging.
- **tools.py** — `query_database` (NL→SQL, self-correcting) and `make_chart` (image output).
- **guardrails.py** — app-layer safety: SELECT/WITH only, blocks write/DDL/unsafe keywords,
  table allow-list, auto `LIMIT`, `statement_timeout`, **READ ONLY transaction**, store-scope lock.
- **eval.py** — golden-set regression harness (`python -m api.agent_graph.eval`).

## Endpoints (api/routers/agent.py)
- `POST /api/agent/v2/query` — agentic answer + table + sql + chart image + metadata.
- `POST /api/agent/v2/export-csv` — CSV of a result, re-run under the same read-only guardrails.

## Capabilities delivered
- ✅ Reasoning + tool calling + multi-step + self-correction (ReAct via LangGraph)
- ✅ Intelligent SQL generation across all sources (Shopify/EBO/Customer360/Cohorts/Migration/RFM/Churn/New/Repeat — one warehouse)
- ✅ Short-term memory (conversation history threaded in)
- ✅ Guardrails / safety (read-only, allow-list, timeout, row cap, store isolation)
- ✅ Image output (server-rendered charts) + CSV download
- ✅ Observability (structured per-request logging: tools used, rows, latency)
- ✅ Eval harness

## Roadmap / next phases
- **Read-only Postgres role** — swap `run_readonly` to connect as a least-privilege role (currently
  app-layer read-only + READ ONLY txn; role makes it physically impossible to write).
- **Long-term memory** — `pgvector` store for schema docs, business glossary, past successful Q→SQL,
  user preferences (retrieve top-k into the prompt instead of the full static schema).
- **Tracing** — Langfuse/OpenTelemetry spans per node (cost, latency, errors, full traces).
- **HITL** — approve/edit SQL before run; agent asks clarifying questions when ambiguous.
- **LangGraph Postgres checkpointer** — durable cross-turn state + resumable runs.
- **Prebuilt-metric tools** — wrap our analytics endpoints (summary/rfm/churn/cohorts/migration)
  as tools so common asks skip SQL generation entirely (faster + guaranteed-correct).
