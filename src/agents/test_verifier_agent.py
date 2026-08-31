"""
Standalone test for the Verifier Agent. Runs the Extractor first (live), then
feeds its output into the Verifier, so you see the two agents working together
exactly as the orchestrator will chain them later.
"""

import argparse
import json
from extractor_agent import extract, INCIDENT_SCHEMA
from verifier_agent import verify
import time

TEST_TRANSCRIPTS = [
    "cement bag torn near block C, 2 bags wasted, need someone to clean it up",
    "worker slipped near the water tank on level 2, minor injury, ambulance not needed but should report to safety officer",
    "block C ke paas cement bag phat gaya hai, 2 bags waste ho gaye",
    "level 2 pe worker slip ho gaya paani tank ke paas, minor injury hai",
]

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true", help="Actually call the LLM for both agents")
    parser.add_argument("--provider", default="groq", choices=["groq", "gemini"])
    args = parser.parse_args()

    for i, transcript in enumerate(TEST_TRANSCRIPTS, 1):
        print(f"\n{'=' * 60}")
        print(f"Test case {i}")
        print(f"Transcript: {transcript}")

        draft = extract(transcript, provider=args.provider, live=args.live)
        time.sleep(1)  # small gap before the verifier's own calls start
        verified = verify(draft, transcript, INCIDENT_SCHEMA, provider=args.provider, live=args.live)
        time.sleep(2)  # gap before next test case

        print("\n--- Extractor output (draft_json) ---")
        print(json.dumps(draft, indent=2, ensure_ascii=False))

        print("\n--- Verifier output (verified_json) ---")
        print(json.dumps(verified, indent=2, ensure_ascii=False))

        # Quick human-readable summary
        unverified = [f for f, d in verified.items()
                      if isinstance(d, dict) and d.get("verified") is False]
        if unverified:
            print(f"\n⚠️  FLAGGED FIELDS: {unverified}")
        else:
            print("\n✅ All fields passed verification.")