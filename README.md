# Billing Dispute AI Agent — Local Test Harness

A runnable POC of the two-stage agentic pipeline from the BRD, wired against
mock CRM / Billing / OCS / Contract data so you can test the full
detect → investigate → resolve loop today, without waiting on real system
access.

## What this proves right now

- The **Live Billing Monitor** watching a simulated OCS stream and flagging
  anomalies pre-bill.
- **Stage 1** genuinely deciding which of 4 data sources to query per case
  (verified: a simple case queries 2 sources, a complex one queries all 4 —
  see `output/audit_log.jsonl` after running).
- **Stage 2** producing a root cause, confidence score, and action.
- The **Resolution Decision Matrix** (BRD §10) enforced in code, not prompt
  text — all 5 action types (Auto-Resolve, Bill Correction, Agent-Assist,
  Escalation, Proactive Notice) are exercised by the 5 mock scenarios.
- A **full audit trail** per case: which sources were queried, why, and what
  evidence drove the decision.

## What's mocked vs real

| Component | This POC | Real system |
|---|---|---|
| OCS usage stream | `data/ocs_events.csv`, read once | Live event subscription |
| CRM | `data/crm.json` | CRM API |
| Contract/Promotion terms | `data/contracts.json` | RAG store synced from contract system |
| Billing baseline | `data/billing.json` | Billing API |
| Stage 1 reasoning | Rule-based heuristic in `agent.py` | LLM tool-call (function-calling) |
| Stage 2 reasoning | Rule-based heuristic in `agent.py` | LLM call grounded via RAG |
| Confidence gates / decision matrix | Hard-coded in `agent.py::_decide_action()` | Same — **keep this in code even after Stage 1/2 go live on a real LLM.** This is what makes autonomous execution safe; it should never live in a prompt. |

The rule-based stand-ins are written so their **input/output shape matches
exactly** what an LLM tool-call would receive and return. Swapping either
stage for a real model call is a drop-in change inside `agent.py` — nothing
in `monitor.py`, `orchestrator.py`, or `data_sources.py` needs to change.

## Interface contracts (schemas/)

Before Sprint 2 starts, these are the schemas every layer builds against —
the OCS event stream, the CRM/Billing/Contract fields the agent consumes,
the case object the monitor hands to Stage 1, and the audit record format
required for Ofcom compliance. Each schema file has inline `description`
fields flagging what's a confirmed assumption vs. an open question for the
real system (search for "CONFIRM" / "OPEN QUESTION" in the schema files).

```bash
pip install -r requirements.txt        # only needed for validation, not for running the demo
cd src && python3 validate_schemas.py   # checks all mock data + a fresh audit log against the schemas
```

This is meant to be run in CI going forward: any change to the mock data
shape, or to the schemas themselves, should fail the build if they drift
apart — much cheaper to catch here than after Sprint 2 has built against a
stale contract.

## How to run it

```bash
cd src
python3 run_demo.py                # uses 2026-09-05 (matches the mock data)
python3 run_demo.py 2026-09-05     # or pass any date explicitly

# Then inspect any single case's full reasoning trace:
python3 inspect_case.py CUST-1001
python3 inspect_case.py CUST-1004
```

No dependencies beyond Python 3 standard library — nothing to `pip install`.

## The 5 test scenarios (data/ocs_events.csv)

| Customer | Scenario | Expected action |
|---|---|---|
| CUST-1001 | Accidental one-off PPV rental, genuine first occurrence | Pending Approval — Credit (90%) |
| CUST-1002 | Promo ended, MRC increases exactly as contracted | Proactive Notice (97%) |
| CUST-1003 | Two different charge types in one window, prior dispute on file | Agent-Assist Card (62%) |
| CUST-1004 | Large roaming charge, correctly billed but contested/high-value | Escalation (55%) |
| CUST-1005 | Identical charge posted twice (system duplicate) | Pending Approval — Bill Correction (92%) |
| CUST-1006 | Same charge type as CUST-1001, but a goodwill credit was already used this year | Agent-Assist Card (65%) |

CUST-1001 vs. CUST-1006 is worth walking through side by side: same charge
type, same amount range, same "single confirmed charge" pattern — but the
second one doesn't get fast-tracked to a one-click agent approval, because
it checks CRM history before treating it as eligible for goodwill rather
than assuming eligibility. It drops instead to a full Agent-Assist Card,
meaning a human has to actually review it rather than just rubber-stamp a
pre-filled proposal. (Note: as of the current policy, *neither* case
executes without a human either way — no credit or correction is ever
applied without explicit agent approval, regardless of confidence. The
distinction that survives is fast-track-to-approval vs. needs-investigation,
not automatic-vs-manual.) This is also what caught a real bug during
testing: the first version of Stage 1 only fetched CRM for multi-cause or
high-value cases, so a single low-value charge was never checked against
goodwill history at all — meaning it would have incorrectly fast-tracked
CUST-1006 for approval as if it were a clean first occurrence. Fixed by
making CRM a mandatory fetch for any single-charge goodwill candidate, and
making Stage 2 refuse to assume "first occurrence" if CRM evidence wasn't
actually retrieved. Worth
mentioning to your director as a concrete example of why review/testing
matters even for a "simple" case.

Edit `data/ocs_events.csv`, `data/crm.json`, `data/billing.json`, or
`data/contracts.json` directly to add your own test cases — no code changes
needed for new customers as long as they follow the same shape.

## What's required to connect the real OCS (next step, not done here)

This sandbox has no network access to TalkTalk's systems, so this can only
ever be a local mock. To move from this harness to a real pilot:

1. **OCS feed access** — a read-only subscription or export (Kafka topic,
   webhook, or scheduled extract) from the Online Charging System, giving
   per-customer usage/charge events in near real time. Confirm event schema
   (customer identifier, timestamp, charge type, amount) up front — that's
   the one contract `monitor.py` depends on.
2. **CRM/Billing/Contract API credentials** — read access, scoped to the
   fields the agent actually needs (tenure, dispute history, cycle baseline,
   contract/promo terms). PII masking should happen at this boundary, before
   anything reaches the reasoning stage — `data_sources.py::get_crm()` shows
   where that currently happens in the mock.
3. **RAG store** — the contract/promotion text needs to be indexed
   (embeddings + vector store) and kept in sync with the source contract
   system; BRD Section 13 flags staleness as a named risk with a weekly-sync
   mitigation.
4. **LLM platform with function-calling** — whatever model replaces the
   rule-based `stage1_investigate` / `stage2_resolve` needs reliable
   tool-use, since Stage 1's whole job is choosing which tools to call.
5. **A staging environment with the confidence gates live but execution
   disabled** — run Stage 1 + Stage 2 against real (or shadowed) data for a
   period, log what the agent *would* have done, and compare against actual
   agent/customer outcomes before allowing any auto-execution. This is the
   fastest way to validate the ≥85%/≥75% thresholds are calibrated correctly
   before they're allowed to touch a real account.

## File map

```
billing_dispute_ai_poc/
├── data/
│   ├── crm.json            customer profiles (mock CRM)
│   ├── contracts.json      contract + promo terms (mock RAG source)
│   ├── billing.json        baseline spend + last-cycle MRC (mock Billing)
│   └── ocs_events.csv      simulated usage stream (mock OCS)
├── schemas/
│   ├── ocs_event.schema.json       OCS event contract - CONFIRM against real feed first
│   ├── crm_record.schema.json      CRM fields, post-PII-masking
│   ├── billing_record.schema.json  Billing cycle context
│   ├── contract_record.schema.json Contract/promo terms (RAG source, structured half)
│   ├── agent_case.schema.json      What the monitor hands to Stage 1
│   └── audit_record.schema.json    Ofcom-facing audit log format
├── src/
│   ├── data_sources.py     mock API wrappers for all 4 sources
│   ├── monitor.py          Live Billing Monitor — anomaly detection
│   ├── agent.py            Stage 1 + Stage 2 + the decision matrix
│   ├── orchestrator.py     wires monitor -> agent -> audit log
│   ├── run_demo.py         entry point
│   ├── inspect_case.py     pretty-print one case's audit trail
│   └── validate_schemas.py checks mock data + audit log against schemas/
├── output/
│   └── audit_log.jsonl     generated on each run
├── requirements.txt        deps for validate_schemas.py only
└── README.md
```
