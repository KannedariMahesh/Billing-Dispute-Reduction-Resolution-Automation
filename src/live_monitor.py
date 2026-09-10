"""
live_monitor.py
----------------
The event-driven counterpart to monitor.py.

monitor.py::scan_for_anomalies() answers "as of this date, who looks
anomalous?" by re-reading everything in one batch — fine for the original
POC, wrong shape for a live stream. A real feed doesn't hand you a clean
batch to scan; it hands you one event at a time, forever, and something has
to decide THE MOMENT an anomaly threshold is crossed, not on the next
scheduled scan.

LiveMonitor keeps a running per-customer total in memory and re-evaluates
after every single event. For a real deployment this state belongs in
Redis (already in your stack per SETUP.md) rather than a Python dict, so
state survives a restart and multiple monitor instances can share it — the
in-memory dict here is a deliberate simplification to keep this runnable
without any external services, not a production design.
"""

import os
import sys
from datetime import date, datetime

sys.path.insert(0, os.path.dirname(__file__))
from data_sources import _BILLING

ANOMALY_THRESHOLD_GBP = 3.00


class LiveMonitor:
    def __init__(self):
        # customer_id -> running state for the current cycle
        # PRODUCTION NOTE: replace this dict with a Redis hash per customer
        # (e.g. HINCRBYFLOAT for the running totals) so state isn't lost on
        # restart and isn't scoped to a single process.
        self._state = {}
        self._already_flagged = set()  # avoid re-flagging the same anomaly every subsequent event

    def _get_state(self, customer_id):
        if customer_id not in self._state:
            billing = _BILLING.get(customer_id, {})
            self._state[customer_id] = {
                "variable_spend": 0.0,
                "last_mrc_posted": None,
                "baseline_avg_daily_spend": billing.get("baseline_avg_daily_spend", 0.0),
                "cycle_start": billing.get("current_cycle_start"),
                "last_cycle_mrc": billing.get("current_mrc_billed_last_cycle", 0.0),
                "events_this_cycle": [],
            }
        return self._state[customer_id]

    def process_event(self, event: dict, as_of: date = None) -> dict | None:
        """
        Feed one validated OCS event in. Returns a 'case' dict (same shape
        monitor.py produces, so orchestrator.run_case() doesn't need to
        know or care whether it came from a batch scan or a live stream)
        the MOMENT this event pushes the customer over the anomaly
        threshold — otherwise returns None.
        """
        customer_id = event["customer_id"]
        as_of = as_of or datetime.fromisoformat(event["timestamp"].replace("Z", "")).date()
        state = self._get_state(customer_id)
        state["events_this_cycle"].append(event)

        if event["event_type"] == "MRC_POSTED":
            state["last_mrc_posted"] = event["amount"]
        else:
            state["variable_spend"] += event["amount"]

        cycle_start = state["cycle_start"]
        if not cycle_start:
            return None
        days = max((as_of - date.fromisoformat(cycle_start)).days, 1)
        expected = state["baseline_avg_daily_spend"] * days
        usage_delta = state["variable_spend"] - expected

        flag_key = (customer_id, as_of.isoformat())

        if usage_delta >= ANOMALY_THRESHOLD_GBP and flag_key not in self._already_flagged:
            self._already_flagged.add(flag_key)
            variable_events = [e for e in state["events_this_cycle"] if e["event_type"] != "MRC_POSTED"]
            return {
                "customer_id": customer_id,
                "anomaly_type": "usage_anomaly",
                "delta_gbp": round(usage_delta, 2),
                "contributing_events": variable_events,
                "detected_at": as_of.isoformat(),
            }

        if state["last_mrc_posted"] is not None:
            recurring_delta = state["last_mrc_posted"] - state["last_cycle_mrc"]
            if abs(recurring_delta) >= 1.00 and (customer_id, "mrc") not in self._already_flagged:
                self._already_flagged.add((customer_id, "mrc"))
                mrc_events = [e for e in state["events_this_cycle"] if e["event_type"] == "MRC_POSTED"]
                return {
                    "customer_id": customer_id,
                    "anomaly_type": "recurring_anomaly",
                    "delta_gbp": round(recurring_delta, 2),
                    "contributing_events": mrc_events,
                    "detected_at": as_of.isoformat(),
                }

        return None
