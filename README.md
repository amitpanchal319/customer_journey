# Customer Journey Tool

Unified customer analytics platform — Shopify (Online) + EBO (Offline).

## Project Structure

```
customer_journey/
├── .env                          # DB credentials — never commit
├── .gitignore
├── requirements.txt
├── database/
│   ├── connection.py             # SQLAlchemy pool + get_db()
│   ├── build_datamodel.py        # One-time data model setup
│   └── customer_journey_final_datamodel.sql
├── api/
│   ├── main.py                   # FastAPI app
│   └── routers/
│       ├── customer.py           # Customer 360 + timeline
│       ├── segments.py           # RFM, churn, category, size
│       ├── cohorts.py            # Cohort retention, MoM
│       ├── stores.py             # Store intelligence
│       └── export.py             # Self-serve CSV export
└── frontend/                     # React / Next.js (next phase)
```

## Setup

### 1. Clone and create virtual environment
```bash
cd customer_journey
python -m venv venv

# Windows
venv\Scripts\activate

# Mac / Linux
source venv/bin/activate
```

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

### 3. Configure credentials
Edit `.env` — credentials are already set for your DB.

### 4. Build the data model (run ONCE)
```bash
python database/build_datamodel.py
```
This runs `customer_journey_final_datamodel.sql` against your PostgreSQL.
Safe to re-run — all views use DROP IF EXISTS CASCADE.
Takes 10–30 minutes on first run (3.8M + rows).

### 5. Start the API
```bash
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
```

### 6. Open Swagger docs
```
http://localhost:8000/docs
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/customer/search?q=email` | Search by email, phone, name |
| GET | `/api/customer/{unq_id}` | Full Customer 360 profile |
| GET | `/api/customer/{unq_id}/timeline` | Transaction history |
| GET | `/api/segments/summary` | Dashboard header counts |
| GET | `/api/segments/rfm` | RFM distribution |
| GET | `/api/segments/churn` | Churn risk breakdown |
| GET | `/api/segments/aov-comparison` | New vs Repeat AOV |
| GET | `/api/segments/frequency` | Order frequency buckets |
| GET | `/api/segments/migration` | Channel migration breakdown |
| GET | `/api/segments/category` | Category-wise repeat behaviour |
| GET | `/api/segments/size` | Size behaviour + combinations |
| GET | `/api/cohorts/retention` | Cohort retention grid |
| GET | `/api/cohorts/mom` | Month-on-month new vs repeat |
| GET | `/api/cohorts/retention-flags` | 30/60/90d retention rates |
| GET | `/api/stores/summary` | All stores ranked |
| GET | `/api/stores/{store_name}` | Store detail + customers |
| GET | `/api/export/count` | Preview filter count |
| GET | `/api/export/csv` | Download filtered CSV |

## Important Notes

- **Data model refresh**: Runs nightly via pg_cron at 2:00 AM IST
- **No LIKE queries**: All frontend filters use indexed equality
- **item_master**: Joined at build time inside the materialized view — no runtime joins
- **B2B exclusion**: Marketplace combos filtered at source during build



