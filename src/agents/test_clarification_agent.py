"""
Standalone test for the Clarification Agent — run directly from the
terminal, no orchestrator, no API server, no other agent required.
This matches the Working Guide's rule: test each agent alone before
chaining anything.

Two modes:

  python -m src.agents.test_clarification_agent
      Deterministic fallback only — no API key, no network call needed.
      Proves the field-detection and safety-check logic works.

  python -m src.agents.test_clarification_agent --live
      Real LLM call, using Google Gemini (free tier — no billing needed).
      Needs GEMINI_API_KEY set in your .env. Get one at
      https://aistudio.google.com/app/apikey
      This is what actually demonstrates the agentic behavior: compare
      the two test cases below and check whether the urgent one reorders
      emergency/severity ahead of duration, and whether anything gets
      merged.
"""

import argparse
import json

from dotenv import load_dotenv

from src.agents.clarification_agent import decide_clarifications, make_gemini_llm_call

load_dotenv()

# Two cases with the same *number* of missing fields but different context.
# The interesting question isn't whether it works — the fallback always
# "works" — it's whether the LLM path actually reorders/merges differently
# between a calm report and an urgent one. If it doesn't, the agent isn't
# earning its keep and Option A (fold it into the orchestrator) was right.
CASES = [
    {
        "name": "calm / low-urgency report",
        "transcript": "Block B mein concrete pump ka problem hai.",
        "extracted": {
            "location":  {"value": "Block B", "evidence_status": "SUPPORTED"},
            "issue":     {"value": "Equipment problem", "evidence_status": "SUPPORTED"},
            "equipment": {"value": "Concrete Pump", "evidence_status": "SUPPORTED"},
            "severity":  {"value": None, "evidence_status": "NOT_PROVIDED"},
            "emergency": {"value": None, "evidence_status": "NOT_PROVIDED"},
            "duration":  {"value": None, "evidence_status": "NOT_PROVIDED"},
            "impact":    {"value": None, "evidence_status": "NOT_PROVIDED"},
        },
    },
    {
        "name": "urgent-sounding report",
        "transcript": "Ek worker Block C mein gir gaya hai, bahut jaldi madad chahiye, kaam ruk gaya hai.",
        "extracted": {
            "location":  {"value": "Block C", "evidence_status": "SUPPORTED"},
            "issue":     {"value": "Worker fell", "evidence_status": "SUPPORTED"},
            "equipment": {"value": None, "evidence_status": "NOT_PROVIDED"},
            "severity":  {"value": None, "evidence_status": "NOT_PROVIDED"},
            "emergency": {"value": None, "evidence_status": "NOT_PROVIDED"},
            "duration":  {"value": None, "evidence_status": "NOT_PROVIDED"},
            "impact":    {"value": "Work stopped", "evidence_status": "SUPPORTED"},
        },
    },
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true", help="Use the real LLM API instead of the deterministic fallback")
    args = parser.parse_args()

    llm_call = make_gemini_llm_call() if args.live else None
    print(f"Mode: {'LIVE (real LLM call)' if args.live else 'FALLBACK (no API key needed)'}")

    for case in CASES:
        print(f"\n=== {case['name']} ===")
        print(f"Transcript: {case['transcript']}")
        steps = decide_clarifications(case["extracted"], case["transcript"], llm_call=llm_call)
        print(json.dumps(steps, indent=2))


if __name__ == "__main__":
    main()
