"""
agent.py
--------
The two-stage reasoning loop from the BRD (Section 5 & 6).

*** WHAT'S MOCKED vs REAL ***
Stage 1 and Stage 2 here are deterministic, rule-based stand-ins for the
LLM reasoning calls described in the BRD. They are written so that:
  1) The INPUT/OUTPUT contract of each stage matches exactly what an LLM
     tool-call would receive and return (a case dict in, a decision dict out).
  2) You can swap `stage1_investigate` and `stage2_resolve` for real calls to
     the Anthropic API (or your platform's model of choice) without changing
     `orchestrator.py`, `monitor.py`, or `data_sources.py` at all.
  3) The DECISION LOGIC in Stage 2 (confidence bands, action mapping) is a
     faithful implementation of the BRD's Resolution Decision Matrix (Section
     10), so the *governance* behaviour you're testing is real even though
     the *reasoning* is simulated.

To wire in a real model: replace the body of each function with a call to
your LLM, passing the same `case` / `evidence` dict as context, with a system
prompt that instructs it to return JSON matching the same output shape used
below. Keep the confidence-gate thresholds in `decide_action()` in code, not
in the prompt — that's the "gated autonomy" guarantee from the BRD.
"""

from data_sources import SOURCE_FUNCTIONS, _CRM

ALL_SOURCES = ["crm", "billing", "ocs", "contract_rag"]

# Confidence gates. These now control ROUTING (fast-track approval vs.
# full agent review), never autonomous execution — see _decide_action().
AUTO_RESOLVE_GATE = 85
BILL_CORRECTION_GATE = 75
ASSIST_CARD_FLOOR = 50
GOODWILL_CAP_GBP = 15.00


# ---------------------------------------------------------------------------
# STAGE 1 — Investigate: decide which sources are worth querying
# ---------------------------------------------------------------------------
def stage1_investigate(case: dict) -> dict:
    """
    Reasons on the raw case ONLY (no evidence fetched yet) and decides which
    of the 4 available sources are relevant. This is the "avoid querying
    everything every time" behaviour from BRD Section 5.

    [MOCK->REAL SWAP POINT]: replace this heuristic with an LLM call. Prompt
    should receive `case` (anomaly type, delta, contributing events) and
    return {"sources": [...], "reasoning": "..."}.
    """
    events = case["contributing_events"]
    event_types = {e["event_type"] for e in events}
    reasoning = []
    sources = {"billing"}  # billing context is cheap and almost always useful
    reasoning.append("Billing selected by default: cheapest source, gives cycle context.")

    if case["anomaly_type"] == "recurring_anomaly":
        sources.add("contract_rag")
        reasoning.append("Recurring (MRC) anomaly -> contract/promo terms likely explain it.")
    else:
        sources.add("ocs")
        reasoning.append("Usage anomaly -> need the raw OCS event detail to identify the charge.")

    if "ROAMING_DATA" in event_types or case["delta_gbp"] > GOODWILL_CAP_GBP:
        sources.add("contract_rag")
        reasoning.append("High-value or roaming-type charge -> check contract terms for correct billing rules.")

    if len(event_types) > 1:
        sources.add("crm")
        reasoning.append("Multiple candidate charge types in the same window -> pull CRM history to help disambiguate.")

    if case["delta_gbp"] > GOODWILL_CAP_GBP:
        sources.add("crm")
        reasoning.append("Delta exceeds the auto-goodwill cap -> CRM dispute history needed regardless.")

    if len(events) == 1 and case["delta_gbp"] <= GOODWILL_CAP_GBP:
        sources.add("crm")
        reasoning.append("Single low-value charge is a goodwill-credit candidate -> must check CRM to confirm this is genuinely first occurrence before granting it.")

    return {"sources": sorted(sources), "reasoning": reasoning}


# ---------------------------------------------------------------------------
# Targeted fetch — orchestrator calls this with ONLY the sources Stage 1 chose
# ---------------------------------------------------------------------------
def fetch_evidence(case: dict, sources: list) -> dict:
    evidence = {}
    customer_id = case["customer_id"]
    crm_hint = _CRM.get(customer_id, {})
    contract_id = crm_hint.get("contract_id")

    for source in sources:
        if source == "contract_rag":
            evidence["contract_rag"] = SOURCE_FUNCTIONS["contract_rag"](contract_id)
        elif source == "ocs":
            evidence["ocs"] = SOURCE_FUNCTIONS["ocs"](customer_id)
        else:
            evidence[source] = SOURCE_FUNCTIONS[source](customer_id)
    return evidence


# ---------------------------------------------------------------------------
# STAGE 2 — Resolve: root cause, confidence, and recommended action
# ---------------------------------------------------------------------------
def stage2_resolve(case: dict, evidence: dict) -> dict:
    """
    Re-reasons over ONLY the retrieved evidence to reach a root cause and a
    confidence score, then maps that to an action via the Resolution
    Decision Matrix (BRD Section 10) — same trigger-condition + confidence
    gating, not a flat confidence ladder.

    [MOCK->REAL SWAP POINT]: replace the root-cause detection block with an
    LLM call grounded on `evidence["contract_rag"]` (RAG) and the raw events.
    Keep `decide_action()` unchanged — that function IS the guardrail policy
    and should stay in code even after Stage 2 becomes a real model call.
    """
    events = case["contributing_events"]
    delta = case["delta_gbp"]

    root_cause_type, confidence, explanation = _diagnose(case, evidence, events, delta)
    action, sla = _decide_action(root_cause_type, confidence, delta)

    return {
        "root_cause_type": root_cause_type,
        "confidence": confidence,
        "explanation": explanation,
        "action": action,
        "sla": sla,
    }


def _diagnose(case, evidence, events, delta):
    """Rule-based stand-in for the LLM's root-cause reasoning."""

    # --- Recurring / promo-related anomaly ---
    if case["anomaly_type"] == "recurring_anomaly":
        contract = evidence.get("contract_rag", {})
        promo_end = contract.get("promo_end_date")
        if promo_end:
            return (
                "promo_expired_expected",
                97,
                f"Recurring charge increased by £{abs(delta):.2f}, matching the scheduled end of "
                f"'{contract.get('promo_name')}' on {promo_end}. Contract terms confirm this is the "
                f"correct standard rate resuming, not a billing error."
            )
        return ("recurring_unexplained", 40, "Recurring charge changed but no matching contract event found.")

    # --- Duplicate charge detection ---
    if len(events) >= 2:
        amounts = [float(e["amount"]) for e in events]
        descs = [e["description"] for e in events]
        times = [e["timestamp"] for e in events]
        if len(set(amounts)) == 1 and len(set(descs)) == 1 and len(set(times)) == 1:
            return (
                "duplicate_charge",
                92,
                f"Two identical charges of £{amounts[0]:.2f} ('{descs[0]}') posted at the same timestamp "
                f"({times[0]}) — a system duplicate, not two genuine charges."
            )

    # --- Roaming / high-value / contractually-correct-but-contested ---
    event_types = {e["event_type"] for e in events}
    if "ROAMING_DATA" in event_types:
        contract = evidence.get("contract_rag", {})
        return (
            "high_value_contested",
            55,
            f"£{delta:.2f} roaming data charge is consistent with contract terms "
            f"('{contract.get('notes', 'out-of-bundle roaming billed separately')}'), "
            f"but the amount exceeds the agent's auto-resolution authority and the customer "
            f"is disputing it — requires a human judgement call, not just a data match."
        )

    # --- Single, isolated one-off charge (e.g. accidental PPV rental) ---
    if len(events) == 1:
        crm = evidence.get("crm")
        if crm is None:
            # CRM wasn't fetched for this case — cannot confirm first-occurrence
            # eligibility, so this must NOT be treated as a free pass.
            return ("addon_unconfirmed_no_crm", 45, "Confirmed one-off charge, but CRM history was not "
                    "retrieved for this case — cannot verify first-occurrence eligibility.")
        prior_credits = crm.get("prior_goodwill_credits_12mo", 0)
        if delta <= GOODWILL_CAP_GBP and prior_credits == 0:
            return (
                "addon_confirmed_first_occurrence",
                90,
                f"Single confirmed charge of £{delta:.2f} ('{events[0]['description']}'), first occurrence "
                f"on this account (no goodwill credit in the last 12 months) — eligible for a fast-tracked "
                f"goodwill credit, pending agent approval."
            )
        return (
            "addon_confirmed_repeat",
            65,
            f"Single confirmed charge of £{delta:.2f} ('{events[0]['description']}'), but CRM shows "
            f"{prior_credits} goodwill credit(s) already issued in the last 12 months — not a clean "
            f"first-occurrence case, so it shouldn't auto-approve again."
        )

    # --- Multiple, differing candidate causes in the same window (ambiguous) ---
    if len(event_types) > 1:
        crm = evidence.get("crm", {})
        prior_disputes = crm.get("prior_disputes_12mo", 0) if crm else 0
        base_conf = 70 - (prior_disputes * 8)
        return (
            "ambiguous_multi_cause",
            max(base_conf, 50),
            f"£{delta:.2f} increase spans {len(event_types)} different charge types in the same window "
            f"({', '.join(event_types)}) — no single dominant cause identified with high confidence."
        )

    return ("unclassified", 35, "Evidence did not match a known pattern.")


def _decide_action(root_cause_type, confidence, delta):
    """
    This IS the Resolution Decision Matrix, enforced in code. An LLM never
    sees or sets these thresholds — it only supplies root_cause_type and
    confidence; this function decides what happens next.

    *** POLICY: NO MONETARY ADJUSTMENT EXECUTES WITHOUT HUMAN APPROVAL ***
    This was a hard requirement change: the agent is never allowed to apply
    a credit or correction on its own, regardless of confidence. Confidence
    still does real work here — it controls HOW a case reaches the agent,
    not WHETHER a human is involved:

      - High-confidence, clean-pattern cases (>= AUTO_RESOLVE_GATE /
        BILL_CORRECTION_GATE) arrive as a "Pending Approval" case with the
        exact proposed action pre-filled — a one-click approval for the
        agent, not an investigation.
      - Everything else that isn't clearly explainable (ambiguous, low
        confidence, high value, or contractually-correct-but-contested)
        still requires the agent to actually review the evidence, via
        Agent-Assist Card or Escalation, exactly as before.

    Nothing in this function can return an action that executes a credit or
    correction by itself. If a future case type needs to, that's a policy
    change to make explicitly here — not something Stage 2 can opt into on
    its own via a confidence score.
    """
    if root_cause_type == "promo_expired_expected":
        # No money moves here — purely informational, safe to remain automatic.
        return "Proactive Notice", "Customer informed before bill issued (N/A confidence gate)"

    if root_cause_type == "high_value_contested" or delta > GOODWILL_CAP_GBP:
        return "Escalation", "Routed to human, 15-minute escalation SLA (exceeds auto-authority or flagged)"

    if root_cause_type == "duplicate_charge" and confidence >= BILL_CORRECTION_GATE:
        return (
            "Pending Approval — Bill Correction",
            f"Proposed: reverse duplicate charge of £{delta:.2f}. Awaiting agent approval before execution — not executed automatically.",
        )

    if root_cause_type.startswith("addon_confirmed") and confidence >= AUTO_RESOLVE_GATE:
        return (
            "Pending Approval — Credit",
            f"Proposed: apply £{delta:.2f} goodwill credit. Awaiting agent approval before execution — not executed automatically.",
        )

    if confidence < ASSIST_CARD_FLOOR:
        return "Escalation", "Routed to human, 15-minute escalation SLA (confidence below floor)"

    return "Agent-Assist Card", "Human review, same business day (confidence 50-84%, ambiguous root cause)"
