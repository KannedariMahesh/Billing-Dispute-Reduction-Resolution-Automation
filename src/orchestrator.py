"""
orchestrator.py
----------------
Runs the full lifecycle from BRD Fig. 1 for a single case:

  Step 1-2  Detect         -> handled by monitor.py before this is called
  Step 3    Stage 1        -> agent.stage1_investigate()
  Step 4    Targeted fetch -> agent.fetch_evidence() using ONLY Stage 1's sources
  Step 5    Stage 2        -> agent.stage2_resolve()
  Step 6    Output         -> resolution action + full audit record

Every case produces one audit record, matching the BRD's "full reasoning
chain + tool calls + evidence logged per case" requirement (Section 5, 10.3).
"""

import json
import os
import uuid
from datetime import datetime, timezone

# Set USE_LLM=true in your environment to route Stage 1 and Stage 2 through
# Ollama instead of the rule-based stand-ins. fetch_evidence and _decide_action
# are always the same regardless of which path is active.
#
#   export USE_LLM=true
#   export OLLAMA_MODEL=gemma          # or: qwen2:3.4b
#   python3 run_demo.py
#
USE_LLM = os.environ.get("USE_LLM", "false").lower() == "true"

if USE_LLM:
    from llm_agent import stage1_investigate, stage2_resolve
    print("[orchestrator] LLM mode active — using Ollama for Stage 1 and Stage 2.")
else:
    from agent import stage1_investigate, stage2_resolve

from agent import fetch_evidence


def run_case(case: dict) -> dict:
    correlation_id = str(uuid.uuid4())[:8]

    stage1_output = stage1_investigate(case)
    evidence = fetch_evidence(case, stage1_output["sources"])
    stage2_output = stage2_resolve(case, evidence)

    audit_record = {
        "correlation_id": correlation_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "customer_id": case["customer_id"],  # PII already masked at source
        "anomaly": {
            "type": case["anomaly_type"],
            "delta_gbp": case["delta_gbp"],
            "detected_at": case["detected_at"],
        },
        "stage1": {
            "sources_selected": stage1_output["sources"],
            "reasoning": stage1_output["reasoning"],
        },
        "sources_queried": list(evidence.keys()),
        "stage2": stage2_output,
        "final_action": stage2_output["action"],
    }
    return audit_record


def run_all(cases: list) -> list:
    return [run_case(c) for c in cases]
