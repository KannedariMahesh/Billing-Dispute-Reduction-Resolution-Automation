"""
run_live_demo.py
-----------------
The streaming counterpart to run_demo.py. Instead of scanning a batch of
data "as of" a fixed date, this consumes events one at a time as they
arrive and reacts the moment an anomaly crosses the threshold — the same
event-driven shape a real OCS feed would demand.

Usage:
    python3 run_live_demo.py                  # mock stream, ~compressed real-time
    python3 run_live_demo.py --fast           # no delays, for CI/quick checks

To point this at a REAL feed instead of the mock replay, see ocs_stream.py's
EventHubStreamSource and swap the `source = MockFileStreamSource(...)` line
below for:

    source = EventHubStreamSource(
        connection_str=os.environ["EVENTHUB_CONN_STR"],
        eventhub_name=os.environ["EVENTHUB_NAME"],
        consumer_group="billing-dispute-agent",
    )

Nothing else in this file needs to change — that's the point of the
OCSEventSource interface.
"""

import argparse
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))

from ocs_stream import MockFileStreamSource
from live_monitor import LiveMonitor
from orchestrator import run_case

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
    parser = argparse.ArgumentParser()
    parser.add_argument("--fast", action="store_true", help="skip simulated real-time delays")
    args = parser.parse_args()

    speed = 1000.0 if args.fast else 1.0
    min_gap = 0.0 if args.fast else 0.6

    print("Live OCS stream connected (mock replay of data/ocs_events.csv, timestamp order)")
    print("Watching for anomalies as events arrive — no batch scan, no fixed schedule.\n")

    source = MockFileStreamSource(speed_multiplier=speed, min_gap_seconds=min_gap)
    monitor = LiveMonitor()

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    audit_file = open(AUDIT_LOG_PATH, "w")

    event_count = 0
    case_count = 0

    for event in source.stream():
        event_count += 1
        now = datetime.now().strftime("%H:%M:%S")
        print(f"[{now}] event {event_count:>2}  {event['customer_id']:<12} "
              f"{event['event_type']:<18} £{event['amount']:>6.2f}  {event['description']}")

        case = monitor.process_event(event)
        if case is None:
            continue

        case_count += 1
        print(f"           ANOMALY -> case opened for {case['customer_id']} "
              f"(£{case['delta_gbp']:.2f} {case['anomaly_type']})")

        record = run_case(case)
        audit_file.write(json.dumps(record) + "\n")
        audit_file.flush()

        tag = ACTION_TAGS.get(record["final_action"], "")
        print(f"           -> Stage 1 queried: {record['sources_queried']}")
        print(f"           -> Stage 2: {record['stage2']['root_cause_type']} "
              f"({record['stage2']['confidence']}% confidence)")
        print(f"           -> {tag} {record['final_action']}  ({record['stage2']['sla']})\n")

    audit_file.close()
    print(f"Stream ended. {event_count} events processed, {case_count} cases opened.")
    print(f"Full audit trail: {os.path.relpath(AUDIT_LOG_PATH)}")


if __name__ == "__main__":
    main()
