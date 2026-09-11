# Billing Dispute / Anomaly Mock Dataset

Extends your original 6-customer sample (billing.json, contracts.json, crm.json,
ocs_events.csv) to **26 customers**, each built around a distinct dispute or
billing-anomaly scenario. Use it to validate an LLM/agent's triage logic:
does it correctly decide *credit vs. no credit vs. escalate*, and for how much?

## Files

| File | Purpose |
|---|---|
| `contracts.json` | Product, MRC, promo, and term data per contract |
| `billing.json` | Per-customer billing summary for the current cycle |
| `crm.json` | Customer profile: tenure, dispute/credit history, vulnerability flag |
| `ocs_events.csv` | Raw usage/billing event stream (charges, activations, outages, etc.) |
| `scenario_labels.json` | **Answer key** — ground-truth verdict per customer, for scoring the agent. Don't hand this to the agent under test; use it to grade its output. |
| `schema.sql` | Table definitions (SQLite syntax, portable to Postgres/MySQL with minor tweaks) |
| `sample_queries.sql` | Example FETCH / ADD / DELETE / UPDATE statements |
| `billing_disputes.db` | Pre-built SQLite database containing all of the above, ready to query |

## Scenario coverage (customer_id → category)

- CUST-1001 — unauthorized PPV purchase dispute
- CUST-1002 — promo expiry, price increase is correct (no error)
- CUST-1003 — overage charge during an active promo (no error)
- CUST-1004 — roaming charge dispute (contractually correct)
- CUST-1005 — duplicate charge (clear system error)
- CUST-1006 — repeat PPV dispute, prior goodwill credit already used
- CUST-1007 — mid-cycle upgrade, proration not applied
- CUST-1008 — duplicate MRC posting (webhook retry)
- CUST-1009 — early termination fee dispute (contract terms needed)
- CUST-1010 — VAT/tax misconfiguration
- CUST-1011 — stale FX rate on an international account
- CUST-1012 — network outage, SLA credit not issued
- CUST-1013 — disputed direct-debit failure fee (conflicting accounts)
- CUST-1014 — legacy tariff not migrated to current pricing
- CUST-1015 — add-on activated without customer request
- CUST-1016 — charged for a line already cancelled
- CUST-1017 — downgrade requested but not applied before billing
- CUST-1018 — cooling-off period cancellation, refund pending
- CUST-1019 — suspected serial goodwill-credit abuse (fraud signal)
- CUST-1020 — control case: no anomaly, tests false-positive rate
- CUST-1021 — referral credit qualified but never applied
- CUST-1022 — two promos should stack partially; neither was applied
- CUST-1023 — three add-ons activated at once, authorization unclear
- CUST-1024 — vulnerable-customer flag drives routing, not just the charge
- CUST-1025 — chargeback already filed externally; avoid double refund
- CUST-1026 — £0.35 rounding dispute, below minimum adjustment threshold

Each row in `scenario_labels.json` gives: `expected_verdict`
(`valid_dispute_credit_due` / `valid_charge_no_credit` / `needs_human_review`),
`expected_credit_amount` (or `null` when the right call is a process action, not
a fixed number), and `eval_notes` explaining the reasoning — so you can score
an agent automatically or use it as a rubric for human review.

## Using it with an AI agent

1. Feed the agent the joined case file for one `customer_id` from
   `contracts.json` + `billing.json` + `crm.json` + `ocs_events.csv`
   (see `sample_queries.sql`'s FETCH query for the join) — **never** the
   `scenario_labels` data, that's your answer key.
2. Ask it to decide: is this a valid dispute, and if so, what credit/action
   is owed?
3. Compare its answer against `scenario_labels.json` for that customer.

## Using it as a live SQL-backed test harness

`billing_disputes.db` is a ready-to-query SQLite file with five tables:
`contracts`, `billing`, `crm`, `ocs_events`, `scenario_labels`.

- **Fetch** a case: join `billing` + `crm` + `contracts`, then pull matching
  `ocs_events` — see `sample_queries.sql`.
- **Add** a new scenario: insert one row into each of `contracts`, `crm`,
  `billing`, `ocs_events`, and `scenario_labels` (in that order, so foreign
  keys resolve) — a full worked example (`CT-1027` / `CUST-1027`) is in
  `sample_queries.sql`.
- **Delete** a scenario: delete child rows first (`scenario_labels`,
  `ocs_events`, `billing`, `crm`) then `contracts` last.
- **Update** a scenario to simulate a resolved state (e.g. after the agent
  issues a credit) — example included.

Open it with any SQLite client, or in Python:

```python
import sqlite3
conn = sqlite3.connect("billing_disputes.db")
cur = conn.cursor()
cur.execute("SELECT * FROM billing WHERE customer_id = 'CUST-1007'")
print(cur.fetchall())
```

To load the same schema into Postgres/MySQL instead, use `schema.sql` (swap
`TEXT`/`REAL` for `VARCHAR`/`NUMERIC` as needed) and import the JSON/CSV files
with your usual ETL/COPY tooling.
