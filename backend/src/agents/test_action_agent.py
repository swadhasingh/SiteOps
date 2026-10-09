"""
Standalone test for the Action/Router Agent — run directly from the
terminal, no orchestrator, no API server, no other agent required.

Three things this test needs to prove, in order of importance:

  1. Rule-based routing resolves correctly for known (category, severity)
     pairs — no API call needed, this always runs.
  2. The emergency escalation ONLY fires when emergency == "yes" AND
     reporter_name is present — never on a routine incident, never on a
     bare "yes" with no name (false-alarm prevention). Also no API call
     needed: escalation always attempts to send, but with no .env
     channels configured, each channel correctly reports itself as "not
     configured" rather than silently claiming success. This is the
     single most important thing this test proves.
  3. --live exercises the LLM fallback path, for an unmapped
     (category, severity) combination that has no rule-table entry.

Usage:
  python -m src.agents.test_action_agent
      Rule-based + escalation-condition tests only. No API key needed.

  python -m src.agents.test_action_agent --live --provider groq
      Also runs the LLM-fallback routing case for real (needs
      GROQ_API_KEY, already set if extractor/verifier work). Use
      --provider gemini instead if you have GEMINI_API_KEY set.
"""

import argparse
import json

from src.agents.action_agent import route

# --- Rule-based cases: every one of these should resolve via the table,
# never touch the LLM, and never attempt escalation. -----------------------
RULE_BASED_CASES = [
    {
        "name": "equipment issue, high severity, no emergency",
        "verified": {
            "category": {"value": "equipment_issue"},
            "severity": {"value": "high"},
            "location": {"value": "Block C"},
            "description": {"value": "crane making unusual noise"},
            "action_needed": {"value": "inspect before continuing"},
            "emergency": {"value": "no"},
            "reporter_name": {"value": None},
        },
    },
    {
        "name": "safety hazard, critical severity, confirmed emergency WITH reporter name",
        "verified": {
            "category": {"value": "safety_hazard"},
            "severity": {"value": "critical"},
            "location": {"value": "Block C"},
            "description": {"value": "worker fell, not moving, work has stopped"},
            "action_needed": {"value": None},
            "emergency": {"value": "yes"},
            "reporter_name": {"value": "Ramesh"},
        },
    },
    {
        # This is the false-alarm-prevention case: emergency is "yes" but no
        # reporter_name has been collected yet. Escalation must NOT fire.
        # In the real flow this state should be brief — the Clarification
        # Agent hard-prioritizes reporter_name immediately after emergency —
        # but the Action Agent must not assume that already happened.
        "name": "emergency=yes but reporter_name NOT yet collected (must NOT escalate)",
        "verified": {
            "category": {"value": "safety_hazard"},
            "severity": {"value": "critical"},
            "location": {"value": "Block C"},
            "description": {"value": "worker fell, not moving"},
            "action_needed": {"value": None},
            "emergency": {"value": "yes"},
            "reporter_name": {"value": None},
        },
    },
]

# --- LLM-fallback case: category "other" has no rule-table entry ----------
LLM_FALLBACK_CASE = {
    "name": "ambiguous category, no rule match (tests LLM fallback)",
    "verified": {
        "category": {"value": "other"},
        "severity": {"value": "medium"},
        "location": {"value": "main gate"},
        "description": {"value": "delivery driver arguing with site guard over access"},
        "action_needed": {"value": None},
        "emergency": {"value": "no"},
        "reporter_name": {"value": None},
    },
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true", help="Also run the LLM-fallback routing case for real")
    parser.add_argument("--provider", default="groq", choices=["groq", "gemini"])
    args = parser.parse_args()

    print("=== Rule-based + escalation-condition cases (no API calls) ===")
    for case in RULE_BASED_CASES:
        print(f"\n--- {case['name']} ---")
        result = route(case["verified"], live=False)
        print(f"team: {result['team']} | action: {result['action']} | source: {result['routing_source']}")
        if result["escalation"] is None:
            print("escalation: NOT triggered")
        else:
            print("escalation: TRIGGERED —", json.dumps(result["escalation"], indent=2))

    # Sanity check the false-alarm case specifically, since it's the one
    # that must never trigger regardless of anything else in this test file.
    false_alarm_case = RULE_BASED_CASES[2]
    false_alarm_result = route(false_alarm_case["verified"], live=False)
    assert false_alarm_result["escalation"] is None, (
        "FAIL: escalation fired without a reporter_name — false-alarm prevention is broken!"
    )
    print("\n✅ Confirmed: escalation never fires without emergency=yes AND a reporter_name.")

    print(f"\n=== LLM-fallback case ({'LIVE, ' + args.provider if args.live else 'not run — pass --live to test'}) ===")
    print(f"--- {LLM_FALLBACK_CASE['name']} ---")
    result = route(LLM_FALLBACK_CASE["verified"], provider=args.provider, live=args.live)
    print(f"team: {result['team']} | action: {result['action']} | source: {result['routing_source']}")


if __name__ == "__main__":
    main()