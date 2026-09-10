"""
run_demo.py
-----------
Entry point. Run with:  python3 run_demo.py [YYYY-MM-DD]

Simulates the Live Billing Monitor scanning the OCS stream as-of a given
date (defaults to 2026-09-05, matching the mock data), then runs every
flagged case through the two-stage agent and prints a decision summary
matching the BRD's Resolution Decision Matrix columns.

Full per-case reasoning traces are written to ../output/audit_log.jsonl.
"""

import json
import os
import sys
from datetime import date

from monitor import scan_for_anomalies
from orchestrator import run_all

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "output")
AUDIT_LOG_PATH = os.path.join(OUTPUT_DIR, "audit_log.jsonl")

ACTION_TAGS = {
    "Pending Approval — Credit": "[PENDING-CREDIT]",
    "Pending Approval — Bill Correction": "[PENDING-CORRECTION]",
    "Agent-Assist Card": "[ASSIST]",
    "Escalation": "[ESCALATE]",
    "Proactive Notice": "[NOTICE]",
}


def main():
    as_of = date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else date(2026, 9, 5)

    print(f"\nLive Billing Monitor — scanning OCS stream as of {as_of.isoformat()}\n" + "-" * 78)
    cases = scan_for_anomalies(as_of)
    print(f"{len(cases)} anomalies flagged pre-bill.\n")

    records = run_all(cases)

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(AUDIT_LOG_PATH, "w") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")

    header = f"{'CUSTOMER':<12} {'DELTA':>8}  {'ROOT CAUSE':<28} {'CONF':>5}  {'ACTION':<24} SLA"
    print(header)
    print("-" * len(header))
    for r in records:
        tag = ACTION_TAGS.get(r["final_action"], "")
        print(
            f"{r['customer_id']:<12} "
            f"£{r['anomaly']['delta_gbp']:>6.2f}  "
            f"{r['stage2']['root_cause_type']:<28} "
            f"{r['stage2']['confidence']:>4}%  "
            f"{tag} {r['final_action']:<17} {r['stage2']['sla']}"
        )

    print(f"\nFull reasoning trace for every case written to: {os.path.relpath(AUDIT_LOG_PATH)}")
    print("Run `python3 inspect_case.py <CUSTOMER_ID>` to see one case's full audit trail.\n")


if __name__ == "__main__":
    main()
