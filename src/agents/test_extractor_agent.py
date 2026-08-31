"""
Standalone test for the Extractor Agent. Run without --live to confirm the
fallback path never crashes. Run with --live to actually call the LLM.
"""

import argparse
import json
from extractor_agent import extract

SAMPLE_TRANSCRIPTS = [
    "cement bag torn near block C, 2 bags wasted, need someone to clean it up",
    "worker slipped near the water tank on level 2, minor injury, ambulance not needed but should report to safety officer",
    "delivery truck for steel rods hasn't arrived yet, was supposed to come this morning, blocking today's schedule",
    "crane near gate 2 making unusual noise, operator stopped work, needs inspection before continuing",
    "block C ke paas cement bag phat gaya hai, 2 bags waste ho gaye",
    "level 2 pe worker slip ho gaya paani tank ke paas, minor injury hai",
]


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true", help="Actually call the LLM instead of using fallback")
    parser.add_argument("--provider", default="groq", choices=["groq", "gemini"])
    args = parser.parse_args()

    for i, transcript in enumerate(SAMPLE_TRANSCRIPTS, 1):
        print(f"\n=== Test case {i} ===")
        print(f"Transcript: {transcript}")
        result = extract(transcript, provider=args.provider, live=args.live)
        print(json.dumps(result, indent=2))