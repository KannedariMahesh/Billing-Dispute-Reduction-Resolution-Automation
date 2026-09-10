"""
validate_schemas.py
--------------------
Sanity-checks the schemas in /schemas against the POC's actual mock data and
a fresh run's audit log. Run this whenever either the schemas or the mock
data change, so drift gets caught immediately rather than discovered by a
developer three sprints from now.

Usage: python3 validate_schemas.py
"""

import csv
import json
import os
import subprocess
import sys

import jsonschema
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

ROOT = os.path.join(os.path.dirname(__file__), "..")
SCHEMA_DIR = os.path.join(ROOT, "schemas")
DATA_DIR = os.path.join(ROOT, "data")
OUTPUT_DIR = os.path.join(ROOT, "output")


def load_schema(name):
    with open(os.path.join(SCHEMA_DIR, name)) as f:
        return json.load(f)


def make_validator(schema_name):
    """Builds a validator with the local schema registry so $ref between
    schema files (e.g. agent_case -> ocs_event) resolves correctly."""
    resources = []
    for fname in os.listdir(SCHEMA_DIR):
        if fname.endswith(".schema.json"):
            schema = load_schema(fname)
            resources.append((fname, Resource.from_contents(schema)))
    registry = Registry().with_resources(resources)
    schema = load_schema(schema_name)
    return Draft202012Validator(schema, registry=registry)


def check(label, validator, instance):
    errors = list(validator.iter_errors(instance))
    if errors:
        print(f"  FAIL  {label}")
        for e in errors:
            print(f"        - {e.message} (at {'/'.join(str(p) for p in e.path)})")
        return False
    print(f"  OK    {label}")
    return True


def main():
    all_ok = True

    # --- OCS events ---
    ocs_validator = make_validator("ocs_event.schema.json")
    with open(os.path.join(DATA_DIR, "ocs_events.csv")) as f:
        for row in csv.DictReader(f):
            event = {
                "event_id": row["event_id"],
                "customer_id": row["customer_id"],
                "timestamp": row["timestamp"] + "Z" if "Z" not in row["timestamp"] else row["timestamp"],
                "event_type": row["event_type"],
                "amount": float(row["amount"]),
                "currency": "GBP",
                "description": row["description"],
            }
            all_ok &= check(f"ocs_events.csv :: {row['event_id']}", ocs_validator, event)

    # --- CRM ---
    crm_validator = make_validator("crm_record.schema.json")
    with open(os.path.join(DATA_DIR, "crm.json")) as f:
        for record in json.load(f):
            record = {k: v for k, v in record.items() if k != "name" and k != "contract_id" or k == "contract_id"}
            # PII fields (name) are stripped here to mirror what the agent
            # actually receives post-masking, per data_sources.py::get_crm()
            masked = {k: v for k, v in record.items() if k != "name"}
            all_ok &= check(f"crm.json :: {masked['customer_id']}", crm_validator, masked)

    # --- Billing ---
    billing_validator = make_validator("billing_record.schema.json")
    with open(os.path.join(DATA_DIR, "billing.json")) as f:
        for record in json.load(f):
            all_ok &= check(f"billing.json :: {record['customer_id']}", billing_validator, record)

    # --- Contracts ---
    contract_validator = make_validator("contract_record.schema.json")
    with open(os.path.join(DATA_DIR, "contracts.json")) as f:
        for record in json.load(f):
            all_ok &= check(f"contracts.json :: {record['contract_id']}", contract_validator, record)

    # --- Fresh run, then validate the audit log it produces ---
    print("\nRunning run_demo.py to generate a fresh audit log...")
    subprocess.run([sys.executable, "run_demo.py"], cwd=os.path.dirname(__file__), capture_output=True)

    audit_validator = make_validator("audit_record.schema.json")
    audit_path = os.path.join(OUTPUT_DIR, "audit_log.jsonl")
    with open(audit_path) as f:
        for line in f:
            record = json.loads(line)
            all_ok &= check(f"audit_log.jsonl :: {record['customer_id']}", audit_validator, record)

    print("\n" + ("ALL SCHEMAS VALID against current mock data + audit log." if all_ok
                   else "SCHEMA VALIDATION FAILED — see FAIL lines above."))
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
