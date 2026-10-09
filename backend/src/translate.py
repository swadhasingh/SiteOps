"""
One shared place for Hindi/Hinglish -> English translation.

Used by:
  - firestore_store.py, when saving an approved/rejected incident
  - action_agent.py, when building the emergency Slack/Teams/email alert

Both need the exact same behavior, so this logic lives here once instead
of being copied in two files.
"""

import json
import os

import requests

GROQ_MODEL = "openai/gpt-oss-120b"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"


def translate_fields_to_english(values: dict) -> dict:
    """
    values: {"location": "Zameen", "description": "..."} (any value may be
    None -- skipped, not sent to the LLM)

    Returns the same keys, each translated to plain English. If the Groq
    call fails for any reason, this returns the ORIGINAL untranslated
    values instead of raising -- a translation failure should never break
    whatever called this (a save, or an emergency alert).
    """
    to_translate = {k: v for k, v in values.items() if v}
    if not to_translate:
        return values

    prompt = (
        "Translate each of the following incident-report field values into "
        "clear, plain English. Keep the meaning exact — do not add, remove, "
        "or guess at details. Some values may already be in English; return "
        "them unchanged. Some may be Hinglish (mixed Hindi/English); "
        "translate the Hindi parts. Respond with ONLY a JSON object, no "
        "other text, mapping each field name to its English translation.\n\n"
        f"{json.dumps(to_translate, ensure_ascii=False)}"
    )

    try:
        api_key = os.environ["GROQ_API_KEY"]
        resp = requests.post(
            GROQ_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": GROQ_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0,
            },
            timeout=20,
        )
        resp.raise_for_status()
        raw = resp.json()["choices"][0]["message"]["content"].strip()
        raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        translated = json.loads(raw)
        result = dict(values)
        for k in to_translate:
            if k in translated and translated[k]:
                result[k] = translated[k]
        return result
    except Exception as e:
        print(f"[translate] Translation failed, using original text instead: {e}")
        return values