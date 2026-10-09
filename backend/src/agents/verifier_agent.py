"""
Verifier Agent — checks the Extractor Agent's draft_json against the original
transcript. Two layers of checking:

  1. Rule-based checks (fast, free, no API call): does source_span actually
     appear in the transcript verbatim, and is it suspiciously broad for a
     field that should be specific?
  2. LLM-based semantic check: does source_span actually SUPPORT value, in
     meaning, not just in substring presence? This catches subtler mismatches
     (e.g. severity mislabeled, or a span that's real text but doesn't
     actually justify the extracted value).

Output: verified_json, where every field gets an added "verified" bool and
a "flags" list explaining any problems found. Nothing here modifies the
Extractor's original value/source_span — the Verifier only annotates.
"""

import os
import json
import time
import requests
from dotenv import load_dotenv

load_dotenv()

# Fields where citing a broad chunk of the transcript is semantically correct
# (a summary is supposed to draw from the whole sentence), so breadth alone
# isn't suspicious for these.
SUMMARY_FIELDS = {"description"}

BROAD_SPAN_THRESHOLD = 0.7  # span covering >70% of transcript = flag, for non-summary fields


def check_span_exists(source_span: str, transcript: str) -> bool:
    """Rule 1: is source_span a real, verbatim substring of the transcript?"""
    if source_span is None:
        return True  # nothing claimed, nothing to check
    return source_span in transcript


def check_span_not_lazy(field_name: str, source_span: str, transcript: str) -> bool:
    """Rule 2: for non-summary fields, is the span suspiciously broad (i.e. the
    model citing 'the whole sentence' instead of pointing at something specific)?"""
    if source_span is None or field_name in SUMMARY_FIELDS:
        return True
    return len(source_span) <= BROAD_SPAN_THRESHOLD * len(transcript)


def check_value_has_evidence(value, source_span) -> bool:
    """Rule 3: if a value is claimed, there must be a source_span backing it.
    A value with no span at all is an unsupported claim by definition."""
    if value is None:
        return True
    return source_span is not None


def rule_based_check(field_name: str, field_data: dict, transcript: str) -> list:
    """Runs all rule-based checks for one field. Returns a list of flag strings
    (empty list = no rule-based issues found)."""
    value = field_data.get("value")
    source_span = field_data.get("source_span")
    flags = []

    if not check_value_has_evidence(value, source_span):
        flags.append("value_without_span")
    if not check_span_exists(source_span, transcript):
        flags.append("span_not_in_transcript")
    if not check_span_not_lazy(field_name, source_span, transcript):
        flags.append("span_too_broad")

    return flags


def build_semantic_check_prompt(field_name: str, description: str, value, source_span: str, transcript: str) -> str:
    return f"""You are verifying whether an extracted field is genuinely supported by evidence, for a construction-site incident report. The transcript may be in English, Hindi, or a Hindi-English mix.

Field being checked: "{field_name}" — {description}
Extracted value: {json.dumps(value)}
Cited evidence (source_span): {json.dumps(source_span)}
Full transcript: \"\"\"{transcript}\"\"\"

Question: does the cited evidence actually, specifically support the extracted value? Consider meaning, not just whether the text appears somewhere in the transcript. A span can be real text and still fail to justify the value (e.g. wrong severity level, mismatched category, or a value that overstates/understates what the evidence says).

Return ONLY valid JSON, no markdown, in this exact shape:
{{"supported": true/false, "reason": "one short sentence explaining why"}}
"""


def call_groq_verify(prompt: str) -> dict:
    api_key = os.environ["GROQ_API_KEY"]
    resp = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": "openai/gpt-oss-120b",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0,
        },
        timeout=30,
    )
    resp.raise_for_status()
    content = resp.json()["choices"][0]["message"]["content"]
    text = content.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text.strip())


def call_gemini_verify(prompt: str) -> dict:
    api_key = os.environ["GEMINI_API_KEY"]
    resp = requests.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}",
        json={"contents": [{"parts": [{"text": prompt}]}]},
        timeout=30,
    )
    resp.raise_for_status()
    content = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
    text = content.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text.strip())


def semantic_check(field_name: str, field_desc: str, value, source_span: str, transcript: str,
                    provider: str = "groq", live: bool = False, max_retries: int = 3) -> dict:
    """Rule 4 (the real verifier agent, not just rule-based checks): does the
    evidence actually semantically support the value? Every return includes a
    "status" field so callers can distinguish 'legitimately nothing to check'
    (skipped_no_value / skipped_not_live) from 'we tried and it broke' (error)
    versus 'we actually checked' (checked) — collapsing these into one null
    was the bug that let failed checks silently count as verified."""
    if value is None or source_span is None:
        return {"supported": None, "status": "skipped_no_value", "reason": "no value/span claimed, skipped"}

    if not live:
        return {"supported": None, "status": "skipped_not_live", "reason": "semantic check skipped (not live)"}

    prompt = build_semantic_check_prompt(field_name, field_desc, value, source_span, transcript)

    for attempt in range(max_retries):
        try:
            if provider == "groq":
                result = call_groq_verify(prompt)
            elif provider == "gemini":
                result = call_gemini_verify(prompt)
            else:
                raise ValueError(f"Unknown provider: {provider}")
            result["status"] = "checked"
            return result
        except requests.exceptions.HTTPError as e:
            if e.response is not None and e.response.status_code == 429 and attempt < max_retries - 1:
                wait = 2 ** (attempt + 1)  # 2s, 4s, 8s
                print(f"[verifier_agent] Rate limited on '{field_name}', retrying in {wait}s...")
                time.sleep(wait)
                continue
            return {"supported": None, "status": "error", "reason": f"semantic check failed: {e}"}
        except Exception as e:
            return {"supported": None, "status": "error", "reason": f"semantic check failed: {e}"}

    return {"supported": None, "status": "error", "reason": "semantic check failed: retries exhausted"}


def verify(draft_json: dict, transcript: str, schema: dict, provider: str = "groq", live: bool = False) -> dict:
    """
    Runs the full Verifier pipeline over one Extractor output.
    Returns verified_json: same shape as draft_json, but every field gets
    "flags" (rule-based issues) and "semantic" (LLM judgment) added.
    """
    if draft_json.get("_fallback"):
        # Extractor never actually ran — nothing to verify, pass through as-is.
        result = dict(draft_json)
        result["_verifier_skipped"] = True
        return result

    verified = {}
    for field_name, field_data in draft_json.items():
        if field_name == "_fallback":
            continue
        field_desc = schema.get(field_name, {}).get("description", "")
        flags = rule_based_check(field_name, field_data, transcript)
        sem = semantic_check(
            field_name, field_desc,
            field_data.get("value"), field_data.get("source_span"),
            transcript, provider=provider, live=live,
        )

        verified[field_name] = {
            **field_data,
            "flags": flags,
            "semantic": sem,
            # A field only counts as verified if: no rule-based flags, AND the
            # semantic check either wasn't needed or genuinely passed — a
            # failed/errored check ("status" == "error") must NOT count as verified.
            "verified": (len(flags) == 0) and (sem.get("status") != "error") and (sem.get("supported") is not False),
        }

    verified["_fallback"] = False
    verified["_verifier_skipped"] = False
    return verified