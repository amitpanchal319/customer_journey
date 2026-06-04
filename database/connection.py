# database/connection.py
# ----------------------------------------------------------------
# Central DB connection pool using SQLAlchemy.
# All routers import get_db() from here — never hardcode credentials.
# ----------------------------------------------------------------

import os
from urllib.parse import quote_plus
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from dotenv import load_dotenv

load_dotenv()

# ── Build connection URL from .env ────────────────────────────────────────────
PG_HOST     = os.getenv("PG_HOST",     "10.150.0.5")
PG_PORT     = os.getenv("PG_PORT",     "5432")
PG_DATABASE = os.getenv("PG_DATABASE", "Unicorn")
PG_USER     = os.getenv("PG_USER",     "")
PG_PASSWORD = os.getenv("PG_PASSWORD", "")

# quote_plus encodes special characters in password (e.g. @ → %40)
# This is required when password contains @, #, /, etc.
DATABASE_URL = (
    f"postgresql+psycopg2://{quote_plus(PG_USER)}:{quote_plus(PG_PASSWORD)}"
    f"@{PG_HOST}:{PG_PORT}/{PG_DATABASE}"
)

# ── Connection pool ───────────────────────────────────────────────────────────
# pool_size     : persistent connections kept open
# max_overflow  : extra connections allowed under load
# pool_pre_ping : auto-reconnect if connection dropped overnight
engine = create_engine(
    DATABASE_URL,
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,
    pool_recycle=3600,      # recycle connections every 1 hour
    echo=False,             # set True to log SQL in development
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

# ── Dependency for FastAPI routers ────────────────────────────────────────────
def get_db():
    """
    FastAPI dependency — yields a DB session and closes it after request.

    Usage in router:
        from database.connection import get_db
        from sqlalchemy.orm import Session
        from fastapi import Depends

        @router.get("/example")
        def example(db: Session = Depends(get_db)):
            result = db.execute(text("SELECT 1"))
            ...
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ── Health check helper ───────────────────────────────────────────────────────
def check_connection() -> bool:
    """Returns True if DB is reachable, False otherwise."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception as e:
        print(f"[DB] Connection failed: {e}")
        return False