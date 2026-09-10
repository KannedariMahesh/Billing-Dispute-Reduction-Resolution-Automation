"""
monitor.py
----------
Stand-in for the BRD's "Live Billing Monitor" (Channel layer, Step 1-2 of the
system flow). In production this subscribes to the real OCS event stream; here
it reads the mocked ocs_events.csv and evaluates each customer's cycle-to-date
position against their baseline, "as of" a given evaluation date.

Two anomaly types are detected, matching the two ways a bill can surprise a
customer:
  - usage_anomaly     : cycle-to-date variable spend (PPV, overage, add-ons,
                         roaming...) is running well above the customer's
                         normal baseline.
  - recurring_anomaly : a newly-posted recurring (MRC) charge differs from
                         what was billed last cycle (e.g. a promo lapsed).

Threshold is intentionally simple (absolute GBP delta) so it's easy to reason
about and retune for a real pilot — swap ANOMALY_THRESHOLD_GBP or the
comparison logic without touching the agent.
"""

from datetime import date, datetime
from data_sources import get_ocs_events, _BILLING

ANOMALY_THRESHOLD_GBP = 3.00


def _days_elapsed(cycle_start: str, as_of: date) -> int:
    start = datetime.strptime(cycle_start, "%Y-%m-%d").date()
    return max((as_of - start).days, 1)


def scan_for_anomalies(as_of: date) -> list:
    """Returns one 'case' dict per customer with a flagged anomaly."""
    cases = []

    for customer_id, billing in _BILLING.items():
        events = get_ocs_events(customer_id)
        days = _days_elapsed(billing["current_cycle_start"], as_of)
        expected_variable_spend = billing["baseline_avg_daily_spend"] * days

        variable_events = [e for e in events if e["event_type"] != "MRC_POSTED"]
        actual_variable_spend = sum(float(e["amount"]) for e in variable_events)
        usage_delta = actual_variable_spend - expected_variable_spend

        mrc_events = [e for e in events if e["event_type"] == "MRC_POSTED"]
        recurring_delta = 0.0
        if mrc_events:
            posted = float(mrc_events[-1]["amount"])
            recurring_delta = posted - billing["current_mrc_billed_last_cycle"]

        if usage_delta >= ANOMALY_THRESHOLD_GBP:
            cases.append({
                "customer_id": customer_id,
                "anomaly_type": "usage_anomaly",
                "delta_gbp": round(usage_delta, 2),
                "contributing_events": variable_events,
                "detected_at": as_of.isoformat(),
            })
        elif abs(recurring_delta) >= 1.00:
            cases.append({
                "customer_id": customer_id,
                "anomaly_type": "recurring_anomaly",
                "delta_gbp": round(recurring_delta, 2),
                "contributing_events": mrc_events,
                "detected_at": as_of.isoformat(),
            })

    return cases
