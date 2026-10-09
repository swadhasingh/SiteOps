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
      Real LLM call. Defaults to --provider groq (reuses GROQ_API_KEY,
      already set in your .env — no new key needed). Pass --provider gemini
      to use Google Gemini instead (needs GEMINI_API_KEY; free tier, get one
      at https://aistudio.google.com/app/apikey).
      This is what actually demonstrates the agentic behavior: compare
      the two test cases below and check whether the urgent one reorders
      severity ahead of action_needed, and whether category+severity ever
      get merged (both are input_type "choice", so they're eligible).

NOTE: these "extracted" dicts below are shaped like real Extractor/Verifier
output — {"value": ..., "source_span": ...} per field — matching the actual
5-field schema (category, severity, location, description, action_needed),
not the old placeholder 7-field shape. A field counts as "missing" purely
by having value=None; that's what decide_clarifications() checks now.
"""

import argparse
import json

from dotenv import load_dotenv

from src.agents.clarification_agent import decide_clarifications, make_groq_llm_call, make_gemini_llm_call

load_dotenv()

# Two cases with a similar number of missing fields but different context.
# The interesting question isn't whether it works — the fallback always
# "works" — it's whether the LLM path actually reorders/merges differently
# between a calm report and an urgent one. If it doesn't, the agent isn't
# earning its keep.
CASES = [
    {
        "name": "calm / low-urgency report",
        "transcript": "cement bag torn near block C, 2 bags wasted",
        "extracted": {
            "category":      {"value": "material_damage", "source_span": "cement bag torn near block C"},
            "location":      {"value": "near block C", "source_span": "near block C"},
            "description":   {"value": "cement bag torn near block C, 2 bags wasted", "source_span": "cement bag torn near block C, 2 bags wasted"},
            "severity":      {"value": None, "source_span": None},
            "action_needed": {"value": None, "source_span": None},
        },
    },
    {
        "name": "urgent-sounding report",
        "transcript": "worker fell near block C, not moving, work has stopped, need help fast",
        "extracted": {
            "category":      {"value": "safety_hazard", "source_span": "worker fell"},
            "location":      {"value": "near block C", "source_span": "near block C"},
            "description":   {"value": "worker fell near block C, not moving, work has stopped", "source_span": "worker fell near block C, not moving, work has stopped"},
            "severity":      {"value": None, "source_span": None},
            "action_needed": {"value": None, "source_span": None},
        },
    },
    {
        # This is the only case where an ordering/merging decision is actually
        # possible: 3 fields missing, and 2 of them (category, severity) are
        # both input_type "choice" — so a merge is legal per the prompt's own
        # rule, and there's more than one field to sequence. The first two
        # cases above only ever have exactly one valid ordering (choice before
        # text), so they can't distinguish "the LLM is reasoning" from "there
        # was only one possible answer." This case can.
        "name": "multi-field missing, urgent (tests real merge/reorder)",
        "transcript": "worker fell near block C, not moving, work has stopped, need help fast",
        "extracted": {
            "location":      {"value": "near block C", "source_span": "near block C"},
            "description":   {"value": "worker fell near block C, not moving, work has stopped", "source_span": "worker fell near block C, not moving, work has stopped"},
            "category":      {"value": None, "source_span": None},
            "severity":      {"value": None, "source_span": None},
            "action_needed": {"value": None, "source_span": None},
        },
    },
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true", help="Use the real LLM API instead of the deterministic fallback")
    parser.add_argument("--provider", default="groq", choices=["groq", "gemini"])
    args = parser.parse_args()

    if not args.live:
        llm_call = None
    elif args.provider == "groq":
        llm_call = make_groq_llm_call()
    else:
        llm_call = make_gemini_llm_call()

    print(f"Mode: {'LIVE (' + args.provider + ')' if args.live else 'FALLBACK (no API key needed)'}")

    for case in CASES:
        print(f"\n=== {case['name']} ===")
        print(f"Transcript: {case['transcript']}")
        steps = decide_clarifications(case["extracted"], case["transcript"], llm_call=llm_call)
        print(json.dumps(steps, indent=2))


if __name__ == "__main__":
    main()