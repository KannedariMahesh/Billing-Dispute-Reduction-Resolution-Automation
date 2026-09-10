# Billing Dispute AI Gateway

Run from this directory:

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Endpoints:

- `GET /health`
- `GET /api/v1/anomalies?as_of=2026-09-05`
- `POST /api/v1/cases`
- `GET /api/v1/audits`
- `GET /api/v1/audits/{correlation_id}`

Every request receives an `X-Correlation-ID`. Processed cases are appended to
the configured JSONL audit log.
