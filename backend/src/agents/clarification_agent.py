"""
Clarification Agent.

Genuinely agentic responsibility: given which fields are still missing
(value is None) after Extraction and Verification, decide:

  1. The ORDER to ask about them — context matters. A report that reads
     as urgent should be asked about severity before less urgent fields
     like action_needed, even though those come later in the schema's
     fixed field order.
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

--- EMERGENCY HANDLING (hard-coded priority, bypasses the LLM) ---

"emergency" and, once confirmed yes, "reporter_name" are handled OUTSIDE
the normal ordering logic entirely. If either is missing, it is asked
first (emergency), then second (reporter_name), unconditionally — never
merged with anything, never left to LLM discretion, never affected by an
API outage. This is deliberate: emergency detection and the false-alarm
check (knowing who is reporting it) are safety-critical and must not be
delayed or reordered by a network call that might fail, be slow, or
(rarely) make a bad judgment call. Only once both are resolved (or
weren't missing to begin with) does the normal ordering/merging logic
run on whatever fields remain.

NOTE on schema shape: data/schema/incident_schema.json stores "fields"
as a DICT keyed by field name, matching what extractor_agent.py and
verifier_agent.py already expect. This agent reads that same dict shape.

NOTE on conditional fields: a field may carry a "conditional_on":
{"field": "X", "value": "Y"} entry, meaning it should only be treated as
"missing" once field X's current value equals Y. Right now the only such
field is reporter_name (conditional on emergency == "yes") — asking for
a reporter's name on every calm, routine incident would be unnecessary
friction; it's only collected when it actually matters.

NOTE on "missing": a field counts as missing by checking whether its
"value" is None on the combined Extractor+Verifier output — NOT by
looking for an "evidence_status" key, which neither agent produces.
"""

import json
import os
from pathlib import Path

SCHEMA_PATH = Path(__file__).resolve().parents[2] / "data" / "schema" / "incident_schema.json"

# Fixed priority order — always asked first, in this order, never merged,
# never subject to LLM discretion. See module docstring.
PRIORITY_FIELDS = ["emergency", "reporter_name"]


def _load_schema():
    with open(SCHEMA_PATH) as f:
        return json.load(f)


def _condition_met(field_spec: dict, extracted: dict) -> bool:
    """A field with no conditional_on is always relevant. A field WITH one
    is only relevant once the referenced field's current value matches."""
    cond = field_spec.get("conditional_on")
    if cond is None:
        return True
    ref_value = extracted.get(cond["field"], {}).get("value")
    return ref_value == cond["value"]


def _missing_fields(extracted: dict, schema: dict) -> list:
    """Return field-defs (dict, with 'name' injected) for every field that
    is currently relevant (see _condition_met) AND whose value is None."""
    missing = []
    for field_name, field_spec in schema["fields"].items():
        if not _condition_met(field_spec, extracted):
            continue
        entry = extracted.get(field_name, {})
        if entry.get("value") is None:
            field_def = dict(field_spec)
            field_def["name"] = field_name
            missing.append(field_def)
    return missing


def _priority_steps(missing_fields: list) -> tuple:
    """Pulls emergency/reporter_name out of the missing list, in fixed
    order, as their own single-field steps. Returns (priority_steps,
    remaining_missing_fields) — the caller runs normal ordering logic
    only on what's left."""
    by_name = {f["name"]: f for f in missing_fields}
    steps = []
    for name in PRIORITY_FIELDS:
        if name in by_name:
            f = by_name[name]
            steps.append({
                "fields": [name],
                "question": f["clarification_question"],
                "reasoning": f"hard-coded priority: '{name}' is asked immediately, "
                             f"never merged, and never left to LLM ordering — safety-"
                             f"critical fields must not depend on an API call succeeding.",
            })
    remaining = [f for f in missing_fields if f["name"] not in PRIORITY_FIELDS]
    return steps, remaining


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
1. The best ORDER to ask about these missing fields, given the transcript's context. If the transcript sounds urgent or hints at danger, injury, or a full work stoppage, ask about severity-type fields before less urgent ones like action_needed.
2. Whether any TWO missing fields can be combined into ONE natural, non-confusing question. Only combine two fields if both are simple choice-type fields (input_type "choice"). Never combine a free-text field with anything, and never combine more than 2 fields into one question.

Do NOT invent, guess, or fill in a value for any field. You only sequence and phrase questions — never answer them.

Respond with ONLY valid JSON: a list of steps in the order they should be asked, each step shaped as:
{"fields": ["field_name"] or ["field_name_a", "field_name_b"], "question": "...", "reasoning": "one short sentence on why this field/order/merge was chosen"}

Every missing field must appear in exactly one step. Output no text outside the JSON.
"""


def decide_clarifications(extracted: dict, transcript: str, llm_call=None) -> list:
    """
    extracted: dict of {field_name: {"value": ..., ...}} — this is the
               Extractor + Verifier agents' combined output (draft_json or
               verified_json), PLUS any answers already folded in from
               earlier clarification steps in this same incident's flow.
               A field counts as missing if its "value" is None (and, for
               conditional fields, its condition is currently met).
    transcript: the original transcript text.
    llm_call: callable(system_prompt, user_prompt) -> raw text.
              Pass None to force the deterministic fallback for non-priority
              fields — this is how the agent's core logic is tested with no
              API key and no network call. Priority fields (emergency,
              reporter_name) NEVER go through llm_call regardless.

    Returns: ordered list of clarification steps. Call this again after
    each answer is folded into `extracted` — e.g. once emergency flips to
    "yes", reporter_name will newly appear as missing on the next call.
    """
    schema = _load_schema()
    missing = _missing_fields(extracted, schema)

    if not missing:
        return []

    priority_steps, remaining = _priority_steps(missing)

    if not remaining:
        return priority_steps

    if llm_call is None:
        return priority_steps + _fallback_order(remaining)

    user_prompt = json.dumps({
        "transcript": transcript,
        "missing_fields": [
            {
                "name": f["name"],
                "clarification_question": f["clarification_question"],
                "input_type": f["input_type"],
                "options": f.get("options"),
            }
            for f in remaining
        ],
    }, indent=2)

    try:
        raw = llm_call(CLARIFICATION_SYSTEM_PROMPT, user_prompt)
        steps = json.loads(raw)

        # Safety check: every remaining (non-priority) field must be covered
        # exactly once. If the model drops or duplicates a field, or tries to
        # sneak a priority field back into a merge, we don't trust the output.
        covered = set()
        for step in steps:
            covered.update(step["fields"])
        expected = {f["name"] for f in remaining}
        if covered != expected:
            raise ValueError(f"LLM output did not cover exactly the remaining fields: got {covered}, expected {expected}")

        return priority_steps + steps
    except Exception as e:
        # Never let a bad or failed LLM call break the clarification flow.
        return priority_steps + _fallback_order(remaining, reason=f"fallback: LLM output rejected ({e})")


def make_groq_llm_call(api_key: str = None, model: str = "openai/gpt-oss-120b"):
    """
    Returns a callable(system_prompt, user_prompt) -> str wired to the real
    Groq API — the same provider extractor_agent.py and verifier_agent.py
    already use, so this needs no new API key if GROQ_API_KEY is already
    set in your .env.
    """
    import requests

    key = api_key or os.environ["GROQ_API_KEY"]

    def call(system_prompt: str, user_prompt: str) -> str:
        resp = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0,
            },
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]

    return call


def make_anthropic_llm_call(api_key: str = None, model: str = "claude-haiku-4-5-20251001"):
    """
    Returns a callable(system_prompt, user_prompt) -> str wired to the real
    Anthropic API. Kept separate from decide_clarifications() so the core
    ordering/merging logic above stays testable without any network call.

    Anthropic has no free tier — this requires a billed API key. Use
    make_gemini_llm_call() or make_groq_llm_call() below instead for
    zero-cost testing.
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