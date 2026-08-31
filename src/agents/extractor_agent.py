"""
Extractor Agent — turns a raw incident transcript into structured draft_json.
Every extracted field includes a source_span (exact substring from the transcript
that supports it) or null if the model found no direct support. This span is what
the Verifier Agent checks next.
"""

import os
import json
import requests
from dotenv import load_dotenv

load_dotenv()

SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "data", "schema", "incident_schema.json")

with open(SCHEMA_PATH) as f:
    INCIDENT_SCHEMA = json.load(f)["fields"]


def build_prompt(transcript: str) -> str:
    field_lines = []
    for name, spec in INCIDENT_SCHEMA.items():
        enum_note = f" (must be one of: {', '.join(spec['enum'])})" if "enum" in spec else ""
        field_lines.append(f'- "{name}": {spec["description"]}{enum_note}')
    field_block = "\n".join(field_lines)

    return f"""You are extracting structured data from a construction-site incident report. The report may be in English, Hindi, or a Hindi-English mix.

Fields to extract:
{field_block}

Rules:
1. Only extract a value if it is directly supported by the transcript text.
2. Keep "value" in the SAME language/script as the transcript. Do not translate Hindi or Hinglish words into English. If the transcript is code-switched, the value should be too.
3. For every field, also return "source_span": the exact substring from the transcript that supports your extracted value. Copy it verbatim, do not paraphrase.
4. If a field is not mentioned or cannot be determined, set both "value" and "source_span" to null. Do not guess or infer.
5. Return ONLY valid JSON, no markdown formatting, no explanation, in this exact shape:

{{
  "category": {{"value": "...", "source_span": "..."}},
  "severity": {{"value": "...", "source_span": "..."}},
  "location": {{"value": "...", "source_span": "..."}},
  "description": {{"value": "...", "source_span": "..."}},
  "action_needed": {{"value": "...", "source_span": "..."}}
}}

Transcript:
\"\"\"{transcript}\"\"\"
"""


def _extract_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text.strip())


def call_groq(prompt: str) -> dict:
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
    return _extract_json(content)


def call_gemini(prompt: str) -> dict:
    api_key = os.environ["GEMINI_API_KEY"]
    resp = requests.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}",
        json={"contents": [{"parts": [{"text": prompt}]}]},
        timeout=30,
    )
    resp.raise_for_status()
    content = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
    return _extract_json(content)


def fallback_extract(transcript: str) -> dict:
    """No API key / call failed — return an all-null structure so the pipeline
    doesn't crash. Every field explicitly marked as fallback so this is never
    silently mistaken for a real extraction."""
    return {
        field: {"value": None, "source_span": None}
        for field in INCIDENT_SCHEMA
    } | {"_fallback": True}


def extract(transcript: str, provider: str = "groq", live: bool = False) -> dict:
    if not live:
        return fallback_extract(transcript)

    prompt = build_prompt(transcript)
    try:
        if provider == "groq":
            result = call_groq(prompt)
        elif provider == "gemini":
            result = call_gemini(prompt)
        else:
            raise ValueError(f"Unknown provider: {provider}")
        result["_fallback"] = False
        return result
    except Exception as e:
        print(f"[extractor_agent] Live call failed ({e}), returning fallback.")
        return fallback_extract(transcript)