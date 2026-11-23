# FreightAudit AI — working MVP

A local-first, single-workspace freight audit pilot. The database persists invoice records and findings; uploaded bytes are read in memory for preview and are not stored. There is no hosted AI. Claim PDFs are drafts and are never sent.

## Current supported scope
- Email/password single-user workspace initialization (first registration only; password >=12 chars).
- CSV/XLSX invoice previews with required columns `reference,carrier,invoice_date,billed_total`; optional `linehaul,fuel_amount,fuel_percent,lane`.
- Text-PDF rate sheets get a rule-based fuel-rate proposal and page reference; user must confirm/edit the percentage before approval. Manual terms entry is also available.
- Deterministic duplicate exact invoice fingerprint check and fuel amount reconciliation against approved percentage, rounded to cents.
- Finding review states and evidence-bearing dispute PDF draft download.
- Text-based invoice PDFs only receive validation; invoice field extraction and scanned OCR are not supported.
- Editable dispute text can be exported as PDF; claims are not sent. No accessorial, date-tier, fuel-index lookup, or multi-tenant isolation.

## Run locally (PostgreSQL)
1. Start PostgreSQL 16 and create a database; or run `docker compose up --build` after copying `.env.example` to `.env` and changing both secrets.
2. Backend: `cd backend && python -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt`; set `DATABASE_URL=postgresql+psycopg://...`, `JWT_SECRET` to a random secret, then `uvicorn app.main:app --reload --port 8000`.
3. Frontend: `cd frontend && npm install && BACKEND_URL=http://127.0.0.1:8000 npm run dev`.
4. Open `http://localhost:3000`. First-time register initializes the single account. API docs at `http://localhost:8000/docs`.

For lightweight tests, set `DATABASE_URL=sqlite:///./test.db` and run from `backend`: `pip install -r requirements.txt && pytest` (install pytest separately if needed).

## Try the synthetic fixture
In the app, register the single-user workspace, open **Contracts**, enter `Northstar Freight` as the carrier and upload `examples/northstar-sample-rate-sheet.pdf`. Verify the proposed 20% rate and approve it. Then go to **Audits** and preview/confirm `examples/demo-invoices.csv`. It should show a fuel variance and a possible duplicate; both records are intentionally synthetic.

## Import CSV example
```csv
reference,carrier,invoice_date,billed_total,linehaul,fuel_amount,fuel_percent,lane
INV-1001,Northstar Freight,2026-11-01,1250,1000,250,25,ABJ-LAG
```
Create an approved Northstar contract with fuel rate 20%. An audit will flag the $50 difference. Duplicate fingerprint is carrier + invoice reference + invoice date + billed total. Review duplicates carefully: corrected/reissued invoices can be legitimate.

## Safety and limitations
Before production use: add CSRF/rate limiting, account recovery and user management, authorization policy, audit log, file retention controls, malware scanning, backups, schema migrations, robust PDF/XLSX parsing limits, contract version/effective dates, richer validation and security review. Do not treat estimated variances as recovered savings or use them to automatically withhold payment.
