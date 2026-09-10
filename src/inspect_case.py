"""
inspect_case.py
---------------
Pretty-prints one customer's full reasoning trace from audit_log.jsonl.
Useful for a live walkthrough: "show me exactly why the agent did that."

Usage: python3 inspect_case.py CUST-1001
"""

import json
import os
import sys

AUDIT_LOG_PATH = os.path.join(os.path.dirname(__file__), "..", "output", "audit_log.jsonl")


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 inspect_case.py <CUSTOMER_ID>")
        return

    target = sys.argv[1]
    if not os.path.exists(AUDIT_LOG_PATH):
        print("No audit log found — run `python3 run_demo.py` first.")
        return

    with open(AUDIT_LOG_PATH) as f:
        for line in f:
            record = json.loads(line)
            if record["customer_id"] == target:
                print(json.dumps(record, indent=2))
                return

    print(f"No case found for {target} in the current audit log.")


if __name__ == "__main__":
    main()
