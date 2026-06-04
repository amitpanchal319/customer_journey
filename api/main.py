# api/main.py
# ----------------------------------------------------------------
# FastAPI application entry point.
# All routers are registered here.
#
# Run:
#     cd customer_journey
#     uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
# ----------------------------------------------------------------

import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

from database.connection import check_connection
from api.routers import customer, segments, cohorts, stores, export, agent

load_dotenv()

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Customer Journey Tool",
    description="Unified customer analytics — Shopify (Online) + EBO (Offline)",
    version="1.0.0",
    docs_url="/docs",           # Swagger UI at /docs
    redoc_url="/redoc",
)

# ── CORS (allow frontend dev server) ─────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(customer.router,  prefix="/api/customer",  tags=["Customer 360"])
app.include_router(segments.router,  prefix="/api/segments",  tags=["Segments"])
app.include_router(cohorts.router,   prefix="/api/cohorts",   tags=["Cohorts"])
app.include_router(stores.router,    prefix="/api/stores",    tags=["Stores"])
app.include_router(export.router,    prefix="/api/export",    tags=["Export"])
app.include_router(agent.router,     prefix="/api/agent",     tags=["AI Agent"])


# ── Root health check ─────────────────────────────────────────────────────────
@app.get("/", tags=["Health"])
def root():
    db_ok = check_connection()
    return {
        "service" : "Customer Journey Tool",
        "status"  : "ok",
        "db"      : "connected" if db_ok else "unreachable",
        "docs"    : "/docs",
    }


@app.get("/health", tags=["Health"])
def health():
    db_ok = check_connection()
    return {"db_connected": db_ok}