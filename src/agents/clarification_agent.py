"""
Clarification Agent.

Genuinely agentic responsibility: given which of the 7 fixed fields are
still missing (evidence_status == NOT_PROVIDED) after Extraction and
Verification, decide:

  1. The ORDER to ask about them — context matters. A report that reads
     as urgent should be asked about emergency/severity before duration
     or impact, even though those come later in the schema's fixed list.
  2. Whether two missing fields can be safely COMBINED into one natural
     question without confusing the person answering.

It does NOT invent field values, and it does NOT choose the fixed
question wording or valid options for a single field — those always
come straight from data/schema/incident_schema.json. That split matters:
the one genuinely open decision (ordering + merging) is the only thing
this agent controls; the wording and options stay fixed and auditable.

If the LLM call fails, returns malformed output, or is not configured at
all, this falls back to the schema's default field order with no
merging — degraded, but never broken. This fallback is also what makes
the agent's core logic testable with zero API key and zero network call.
"""

import json
import os
from pathlib import Path

SCHEMA_PATH = Path(__file__).resolve().parents[2] / "data" / "schema" / "incident_schema.json"


def _load_schema():
    with open(SCHEMA_PATH) as f:
        return json.load(f)


def _missing_fields(extracted: dict, schema: dict) -> list:
    """Return schema field-defs for every field whose evidence_status is NOT_PROVIDED."""
    missing = []
    for field_def in schema["fields"]:
        entry = extracted.get(field_def["name"], {})
        if entry.get("evidence_status") == "NOT_PROVIDED":
            missing.append(field_def)
    return missing


def _fallback_order(missing_fields: list, reason: str = "fallback: schema default order, LLM unavailable") -> list:
    """Deterministic fallback: schema order, one question per field, no merging."""
    return [
        {"fields": [f["name"]], "question": f["clarification_question"], "reasoning": reason}
        for f in missing_fields
    ]


CLARIFICATION_SYSTEM_PROMPT = """You are the clarification-prioritization step in a construction site incident reporting system.

You will be given:
- the original transcript of what a site worker said
- a list of fields that are still missing (not mentioned in the transcript)
- for each missing field: its clarification question, input type, and options (if any)

Your ONLY job is to decide:
1. The best ORDER to ask about these missing fields, given the transcript's context. If the transcript sounds urgent or hints at danger, injury, or a full work stoppage, ask about emergency/severity-type fields before less urgent ones like duration.
2. Whether any TWO missing fields can be combined into ONE natural, non-confusing question. Only combine two fields if both are simple choice-type fields (input_type "choice"). Never combine a free-text field with anything, and never combine more than 2 fields into one question.

Do NOT invent, guess, or fill in a value for any field. You only sequence and phrase questions — never answer them.

Respond with ONLY valid JSON: a list of steps in the order they should be asked, each step shaped as:
{"fields": ["field_name"] or ["field_name_a", "field_name_b"], "question": "...", "reasoning": "one short sentence on why this field/order/merge was chosen"}

Every missing field must appear in exactly one step. Output no text outside the JSON.
"""


def decide_clarifications(extracted: dict, transcript: str, llm_call=None) -> list:
    """
    extracted: dict of {field_name: {"value": ..., "evidence_status": ...}}
               — this is the Extractor + Verifier agents' combined output.
    transcript: the original transcript text.
    llm_call: callable(system_prompt, user_prompt) -> raw text.
              Pass None to force the deterministic fallback — this is how
              the agent's core logic is tested with no API key and no
              network call.

    Returns: ordered list of clarification steps, e.g.
      [{"fields": ["emergency", "severity"], "question": "...", "reasoning": "..."}]
    """
    schema = _load_schema()
    missing = _missing_fields(extracted, schema)

    if not missing:
        return []

    if llm_call is None:
        return _fallback_order(missing)

    user_prompt = json.dumps({
        "transcript": transcript,
        "missing_fields": [
            {
                "name": f["name"],
                "clarification_question": f["clarification_question"],
                "input_type": f["input_type"],
                "options": f.get("options"),
            }
            for f in missing
        ],
    }, indent=2)

    try:
        raw = llm_call(CLARIFICATION_SYSTEM_PROMPT, user_prompt)
        steps = json.loads(raw)

        # Safety check: every missing field must be covered exactly once.
        # If the model drops or duplicates a field, we don't trust the output.
        covered = set()
        for step in steps:
            covered.update(step["fields"])
        expected = {f["name"] for f in missing}
        if covered != expected:
            raise ValueError(f"LLM output did not cover exactly the missing fields: got {covered}, expected {expected}")

        return steps
    except Exception as e:
        # Never let a bad or failed LLM call break the clarification flow.
        return _fallback_order(missing, reason=f"fallback: LLM output rejected ({e})")


def make_anthropic_llm_call(api_key: str = None, model: str = "claude-haiku-4-5-20251001"):
    """
    Returns a callable(system_prompt, user_prompt) -> str wired to the real
    Anthropic API. Kept separate from decide_clarifications() so the core
    ordering/merging logic above stays testable without any network call.

    Anthropic has no free tier — this requires a billed API key. Use
    make_gemini_llm_call() below instead if you want zero-cost testing.
    """
    from anthropic import Anthropic

    client = Anthropic(api_key=api_key or os.environ.get("LLM_API_KEY"))

    def call(system_prompt: str, user_prompt: str) -> str:
        response = client.messages.create(
            model=model,
            max_tokens=500,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        return response.content[0].text

    return call


def make_gemini_llm_call(api_key: str = None, model: str = "gemini-2.5-flash"):
    """
    Returns a callable(system_prompt, user_prompt) -> str wired to the
    Google Gemini API — genuinely free (no credit card, standing free
    tier as of writing, not a trial that expires), via Google AI Studio.

    Get a key at https://aistudio.google.com/app/apikey — sign in with
    any Google account, no billing setup needed for the free tier.

    Uses raw REST calls (via `requests`) rather than a Google SDK
    package, since SDK package names have changed more than once
    (google-generativeai -> google-genai) and the REST endpoint is the
    stable contract underneath either one.
    """
    import requests

    key = api_key or os.environ.get("GEMINI_API_KEY")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

    def call(system_prompt: str, user_prompt: str) -> str:
        response = requests.post(
            url,
            params={"key": key},
            headers={"Content-Type": "application/json"},
            json={
                "system_instruction": {"parts": [{"text": system_prompt}]},
                "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
            },
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()
        return data["candidates"][0]["content"]["parts"][0]["text"]

    return call
