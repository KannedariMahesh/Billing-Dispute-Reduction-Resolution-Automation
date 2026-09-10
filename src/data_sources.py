"""
data_sources.py
----------------
Mock stand-ins for the five systems the agent can query:
  CRM | Billing | OCS (live usage) | Contract/Promotion (RAG) | (Product - not
  needed for this POC's scenarios, omitted for brevity)

Each function signature mirrors what a real integration would look like, so
swapping the body for a real HTTP/DB call later is a drop-in replacement —
the agent code that calls these never changes.

IMPORTANT: the agent only calls the functions it selected in Stage 1. If a
source isn't selected, its function is never invoked for that case — this
file logs every call it receives so you can see exactly which sources were
actually touched per case (see output/audit_log.jsonl "sources_queried").
"""

import csv
import json
import os
from datetime import datetime, date

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")


def _load_json(name):
    with open(os.path.join(DATA_DIR, name)) as f:
        return json.load(f)


def _load_ocs_events():
    with open(os.path.join(DATA_DIR, "ocs_events.csv")) as f:
        return list(csv.DictReader(f))


# In-memory "connection" — loaded once, mimics a live system being queried
_CRM = {c["customer_id"]: c for c in _load_json("crm.json")}
_CONTRACTS = {c["contract_id"]: c for c in _load_json("contracts.json")}
_BILLING = {b["customer_id"]: b for b in _load_json("billing.json")}
_OCS_EVENTS = _load_ocs_events()


def get_crm(customer_id: str) -> dict:
    """CRM: customer profile, tenure, dispute/goodwill history."""
    record = dict(_CRM.get(customer_id, {}))
    # PII masking, mirroring the BRD's middleware requirement — the agent
    # reasons on tenure/history, never needs the customer's name.
    record.pop("name", None)
    return record


def get_billing(customer_id: str) -> dict:
    """Billing: current cycle baseline and last-cycle recurring charge."""
    return dict(_BILLING.get(customer_id, {}))


def get_ocs_events(customer_id: str) -> list:
    """OCS: raw usage/charge events for the current cycle."""
    return [e for e in _OCS_EVENTS if e["customer_id"] == customer_id]


def get_contract_rag(contract_id: str) -> dict:
    """Contract/Promotion RAG store: live terms, grounding for root-cause."""
    return dict(_CONTRACTS.get(contract_id, {}))


SOURCE_FUNCTIONS = {
    "crm": get_crm,
    "billing": get_billing,
    "ocs": get_ocs_events,
    "contract_rag": get_contract_rag,
}
