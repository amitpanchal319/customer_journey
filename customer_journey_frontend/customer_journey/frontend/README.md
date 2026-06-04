# Frontend Setup

## Install & Run

```bash
cd frontend
npm install
npm run dev
```

Open: http://localhost:3000

## Pages

| Route        | Page                          |
|--------------|-------------------------------|
| /            | Dashboard (summary + charts)  |
| /customer    | Customer 360 search + profile |
| /online      | Online-only customers         |
| /offline     | Offline (EBO) customers       |
| /both        | Both-channel customers        |
| /rfm         | RFM segments + churn          |
| /cohorts     | Cohort retention grid + MoM   |
| /stores      | Store intelligence            |
| /export      | Self-serve CSV export         |

## Requirements

- Backend API must be running on port 8002
- next.config.js proxies /api/* → http://localhost:8002/api/*
- No CORS issues since all API calls go through Next.js proxy
