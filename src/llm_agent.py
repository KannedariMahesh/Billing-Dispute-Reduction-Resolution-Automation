"""
llm_agent.py
------------
LLM-backed drop-in replacements for stage1_investigate and stage2_resolve
from agent.py. Everything else (fetch_evidence, _decide_action, the confidence
gates) stays in agent.py and is reused here unchanged.

IMPORTANT: _decide_action() is NEVER replaced by the LLM. The model only
supplies root_cause_type and confidence. The decision matrix stays in code —
that is the governance guarantee.

Swap in by setting USE_LLM=true in the environment (see orchestrator.py).

The prompts are written to be strict about output shape so small models
(gemma, qwen2:3.4b) produce usable JSON reliably. If a model call fails or
returns bad JSON, both functions fall back to the rule-based versions in
agent.py with a logged warning — so a bad LLM response never crashes a case.
"""

import json

from llm_client import chat_json
from agent import (
    stage1_investigate  as _rule_stage1,
    stage2_resolve      as _rule_stage2,
    _decide_action,
    ALL_SOURCES,
    GOODWILL_CAP_GBP,
)

# ---------------------------------------------------------------------------
# STAGE 1 — LLM decides which sources to query
# ---------------------------------------------------------------------------

_STAGE1_SYSTEM = """
You are Stage 1 of a billing dispute AI agent. Your only job is to decide
which data sources are worth querying for a given billing anomaly case, before
any data has been fetched.

The 4 available sources are:
  - "billing"       : customer's current cycle baseline and last-cycle MRC
  - "crm"           : customer profile, tenure, dispute history, goodwill credits used
  - "ocs"           : raw usage and charge events for the current cycle
  - "contract_rag"  : contract and promotion terms (use for recurring/MRC anomalies,
                       roaming charges, or when contract terms may explain the charge)

Rules you must follow:
  1. Always include "billing" — it is cheap and always useful for context.
  2. For a usage_anomaly, include "ocs" to see the raw charge detail.
  3. For a recurring_anomaly, include "contract_rag" to check promo/contract terms.
  4. If the delta_gbp exceeds 15.00, include both "crm" and "contract_rag".
  5. If there are multiple different event types in contributing_events, include "crm".
  6. If there is exactly one event and delta_gbp is 15.00 or less, include "crm"
     to verify this is genuinely a first-occurrence goodwill candidate.
  7. Do NOT include sources that are clearly irrelevant to save latency.

You MUST respond with valid JSON only, in exactly this shape:
{
  "sources": ["billing", "crm"],
  "reasoning": ["reason for including billing", "reason for including crm"]
}

The "sources" array must contain only values from: billing, crm, ocs, contract_rag.
The "reasoning" array must have one entry per source, explaining why it was selected.
Do not include any text outside the JSON object.
""".strip()


def stage1_investigate(case: dict) -> dict:
    """
    LLM-backed Stage 1. Asks the model which sources to query for this case.
    Falls back to the rule-based version if the LLM call fails or returns
    invalid/unexpected output.
    """
    user_message = (
        f"Here is the billing anomaly case:\n\n"
        f"{json.dumps(case, indent=2, default=str)}\n\n"
        f"Decide which sources to query. Reply with JSON only."
    )

    try:
        result = chat_json(system=_STAGE1_SYSTEM, user=user_message, label="Stage 1")
        sources = result.get("sources", [])
        reasoning = result.get("reasoning", [])

        # Validate — sources must be a non-empty list of known values
        valid = set(ALL_SOURCES)
        sources = [s for s in sources if s in valid]
        if not sources:
            raise ValueError("LLM returned no valid sources")

        # Ensure billing is always present (safety net)
        if "billing" not in sources:
            sources.insert(0, "billing")
            reasoning.insert(0, "billing added as mandatory fallback by safety check")

        return {"sources": sorted(set(sources)), "reasoning": reasoning}

    except Exception as exc:
        print(f"[llm_agent] Stage 1 LLM call failed ({exc}), falling back to rule-based.")
        return _rule_stage1(case)


# ---------------------------------------------------------------------------
# STAGE 2 — LLM diagnoses root cause and confidence
# ---------------------------------------------------------------------------

_STAGE2_SYSTEM = """
You are Stage 2 of a billing dispute AI agent. Your job is to analyse the
retrieved evidence for a billing anomaly and identify the root cause and your
confidence level.

You will receive the original case and the evidence fetched from the relevant
data sources. Reason carefully over ALL of the evidence provided.

Valid root_cause_type values (use exactly one of these strings):
  - "promo_expired_expected"        : MRC increase matches a scheduled promo end date in the contract
  - "duplicate_charge"              : two identical charges posted at the same timestamp
  - "addon_confirmed_first_occurrence" : single one-off charge, CRM confirms no prior goodwill credits
  - "addon_confirmed_repeat"        : single one-off charge, but CRM shows prior goodwill credits used
  - "addon_unconfirmed_no_crm"      : single one-off charge but CRM was not available to confirm
  - "high_value_contested"          : charge is contractually correct but customer is disputing it
  - "ambiguous_multi_cause"         : multiple charge types, no single dominant cause
  - "recurring_unexplained"         : recurring charge changed but no contract event explains it
  - "unclassified"                  : evidence does not match any known pattern

Confidence scoring guide:
  - 90-100 : strong evidence, clear match to a known pattern, no ambiguity
  - 70-89  : good evidence but minor uncertainty (e.g. one data point missing)
  - 50-69  : moderate evidence, some ambiguity between possible causes
  - 30-49  : weak evidence, significant uncertainty
  - 0-29   : very little evidence, mostly speculation

IMPORTANT: Do NOT decide what action to take. Only identify root cause and confidence.
The action decision is handled separately by a policy engine.

You MUST respond with valid JSON only, in exactly this shape:
{
  "root_cause_type": "duplicate_charge",
  "confidence": 92,
  "explanation": "Two charges of £8.99 with identical description and timestamp detected..."
}

Do not include any text outside the JSON object.
""".strip()


def stage2_resolve(case: dict, evidence: dict) -> dict:
    """
    LLM-backed Stage 2. Asks the model to diagnose root cause and confidence.
    Then passes those values to the UNCHANGED _decide_action() from agent.py
    to enforce the Resolution Decision Matrix in code.

    Falls back to the rule-based version if the LLM call fails.
    """
    user_message = (
        f"Billing anomaly case:\n{json.dumps(case, indent=2, default=str)}\n\n"
        f"Evidence retrieved:\n{json.dumps(evidence, indent=2, default=str)}\n\n"
        f"Identify the root cause and your confidence. Reply with JSON only."
    )

    try:
        result = chat_json(system=_STAGE2_SYSTEM, user=user_message, label="Stage 2")

        root_cause_type = result.get("root_cause_type", "").strip()
        confidence      = result.get("confidence", 0)
        explanation     = result.get("explanation", "No explanation provided.")

        # Validate
        valid_causes = {
            "promo_expired_expected", "duplicate_charge",
            "addon_confirmed_first_occurrence", "addon_confirmed_repeat",
            "addon_unconfirmed_no_crm", "high_value_contested",
            "ambiguous_multi_cause", "recurring_unexplained", "unclassified",
        }
        if root_cause_type not in valid_causes:
            raise ValueError(f"Unknown root_cause_type from LLM: '{root_cause_type}'")
        if not isinstance(confidence, int) or not (0 <= confidence <= 100):
            raise ValueError(f"Invalid confidence value: {confidence}")

        # Decision matrix stays in code — LLM only supplies the inputs
        delta = case["delta_gbp"]
        action, sla = _decide_action(root_cause_type, confidence, delta)

        return {
            "root_cause_type": root_cause_type,
            "confidence": confidence,
            "explanation": explanation,
            "action": action,
            "sla": sla,
        }

    except Exception as exc:
        print(f"[llm_agent] Stage 2 LLM call failed ({exc}), falling back to rule-based.")
        return _rule_stage2(case, evidence)
