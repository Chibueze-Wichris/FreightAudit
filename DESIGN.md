# FreightAudit AI — design and engineering system

## Tokens
See `REFERENCE.md`; all UI color values derive from that baseline. Type sizes: 28, 22, 16, 14, 12 px. Spacing: 4, 8, 12, 16, 24, 32 px. Borders 1px; radii 6px controls, 10px panels.

## Interface patterns
- **Workspace navigation:** stable routes for Overview, Audits, Contracts, Claims; one active location.
- **Evidence table:** dense, sortable/filterable rows; no color-only status; source-linked detail.
- **Finding detail:** rule, billed/allowed math, contract version, source page, extraction state, reviewer decision.
- **Upload flow:** accepted formats and size stated; visible parse/validation errors; preview extracted fields before audit.
- **Destructive/financial actions:** explicit confirmation; no sending or payment hold in MVP.

## Engineering decisions
- Next.js App Router frontend; FastAPI backend; SQLAlchemy persistence with PostgreSQL in deployment and SQLite for local tests.
- One external audit interface accepts normalized invoice and approved contract terms and returns findings with deterministic evidence. Rule implementations are pure functions; persistence, parsing, and PDF generation are adapters behind separate modules.
- Uploads are local-only and not sent to hosted AI. Text PDFs only initially; scanned/image PDFs fail clearly rather than silently inventing data.
- Invoice ingestion is preview-then-confirm. Contract extraction is proposed, not active, until a human approves terms.
- Auth is single-workspace email/password; secrets are environment variables. No default credentials.
- Decisions to resolve with real fixtures: rate-sheet formats, fuel index source and exact effective-date conventions, duplicate-key policy, accessorial clauses, role model, retention policy, and deployment storage.

## Decision log
- 2026-11-23: MVP agreed as audit + editable dispute PDF; no claim sending/tracking.
- 2026-11-23: deterministic duplicate and fuel checks first; nuanced accessorial rules deferred.
- 2026-11-23: local-only document processing; CSV/XLSX and text PDFs first; scanned OCR deferred.
- 2026-11-23: Finance/controller primary user; deployable single-org pilot; hosted UI + PostgreSQL.
