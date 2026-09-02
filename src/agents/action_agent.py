"""
Action / Router Agent — the simplest of the three original agents, per the
Working Guide: mostly a rule-based lookup table (category + severity ->
responsible team + recommended action), with an LLM fallback only for
genuinely ambiguous cases (category == "other", or an unmapped combination).

Also owns emergency escalation — the most important piece of the initial
phase: if the verified record's "emergency" field is "yes" AND
"reporter_name" has been collected (see clarification_agent.py's hard-coded
priority ordering, which guarantees both are asked before anything else),
this fires a notification to management immediately, via email AND a
Slack/Teams webhook, sent in parallel and independently logged as
sent/failed. This does NOT wait for human review — real emergencies must
not sit in a review queue. Human review still happens afterward for the
record itself; escalation and record-approval are deliberately decoupled.

--- Microsoft Teams webhook note (current as of Aug 2026) ---
Legacy Teams "Incoming Webhook" connectors (office.com URLs) are FULLY
RETIRED — Microsoft completed that rollout May 18-22, 2026. Do not look
for the old Connectors menu; it's gone. The replacement is a "Workflows"
webhook: in the target channel, use the "Workflows" option (not
"Connectors"), pick the "Send webhook alerts to a channel" template, and
copy the resulting URL (a logic.azure.com-style endpoint). Set that as
TEAMS_WEBHOOK_URL below — the POST body/code needed is identical to
before, just a different URL.

Required .env additions for live notification (all optional individually;
each channel degrades independently if unset — see send_escalation_email
and send_escalation_webhook):
  SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, ALERT_EMAIL_FROM, ALERT_EMAIL_TO
  SLACK_WEBHOOK_URL
  TEAMS_WEBHOOK_URL
"""

import os
import json
import smtplib
from email.mime.text import MIMEText

import requests
from dotenv import load_dotenv

load_dotenv()

# --- Rule-based routing table -------------------------------------------
# (category, severity) -> {"team": ..., "action": ...}
ROUTING_TABLE = {
    ("safety_hazard", "critical"): {"team": "Safety Officer", "action": "Immediate site inspection and hazard containment"},
    ("safety_hazard", "high"):     {"team": "Safety Officer", "action": "Inspect and address within the hour"},
    ("safety_hazard", "medium"):   {"team": "Safety Officer", "action": "Inspect within the shift"},
    ("safety_hazard", "low"):      {"team": "Safety Officer", "action": "Log and review at next safety walk"},

    ("material_damage", "critical"): {"team": "Site Supervisor", "action": "Stop related work, assess loss immediately"},
    ("material_damage", "high"):     {"team": "Site Supervisor", "action": "Assess and replace damaged material"},
    ("material_damage", "medium"):   {"team": "Site Supervisor", "action": "Log damage, arrange replacement"},
    ("material_damage", "low"):      {"team": "Site Supervisor", "action": "Note in daily log"},

    ("equipment_issue", "critical"): {"team": "Maintenance", "action": "Emergency equipment inspection"},
    ("equipment_issue", "high"):     {"team": "Maintenance", "action": "Inspect equipment before further use"},
    ("equipment_issue", "medium"):   {"team": "Maintenance", "action": "Schedule inspection"},
    ("equipment_issue", "low"):      {"team": "Maintenance", "action": "Note for routine maintenance check"},

    ("delay", "critical"): {"team": "Project Manager", "action": "Immediate schedule replanning"},
    ("delay", "high"):     {"team": "Project Manager", "action": "Review schedule impact today"},
    ("delay", "medium"):   {"team": "Project Manager", "action": "Note delay, monitor"},
    ("delay", "low"):      {"team": "Project Manager", "action": "Log for weekly review"},

    ("quality_issue", "critical"): {"team": "QA Lead", "action": "Halt related work pending review"},
    ("quality_issue", "high"):     {"team": "QA Lead", "action": "Review before proceeding"},
    ("quality_issue", "medium"):   {"team": "QA Lead", "action": "Schedule QA review"},
    ("quality_issue", "low"):      {"team": "QA Lead", "action": "Log for QA records"},
}

DEFAULT_ROUTE = {"team": "Site Supervisor", "action": "Manual review required — no matching routing rule"}


def rule_based_route(category: str, severity: str) -> dict:
    """Fast path: direct lookup. Returns None if there's no exact match
    (category == 'other', missing severity, or an unanticipated combo),
    signaling the caller to try the LLM fallback instead."""
    return ROUTING_TABLE.get((category, severity))


LLM_ROUTING_PROMPT = """You are the routing step in a construction site incident system. Given an incident's category, severity, and description, decide which team should handle it and what the immediate recommended action is.

Valid teams: Safety Officer, Site Supervisor, Maintenance, Project Manager, QA Lead.

Incident:
  category: {category}
  severity: {severity}
  description: {description}

Return ONLY valid JSON, no markdown: {{"team": "...", "action": "..."}}
"""


def _parse_routing_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text.strip())


def call_groq_route(category, severity, description) -> dict:
    api_key = os.environ["GROQ_API_KEY"]
    prompt = LLM_ROUTING_PROMPT.format(category=category, severity=severity, description=description)
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
    return _parse_routing_json(content)


def call_gemini_route(category, severity, description) -> dict:
    api_key = os.environ["GEMINI_API_KEY"]
    prompt = LLM_ROUTING_PROMPT.format(category=category, severity=severity, description=description)
    resp = requests.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}",
        json={"contents": [{"parts": [{"text": prompt}]}]},
        timeout=30,
    )
    resp.raise_for_status()
    content = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
    return _parse_routing_json(content)


def route(verified_json: dict, provider: str = "groq", live: bool = False) -> dict:
    """
    Main entry point. Takes verified_json (Extractor+Verifier+Clarification-
    filled combined record) and returns:
      {"team": ..., "action": ..., "routing_source": "rule"|"llm"|"default",
       "escalation": None or the result of send_emergency_escalation()}

    If the record's emergency field is "yes" and reporter_name is present,
    this ALSO fires the emergency escalation as a side effect before
    returning — see send_emergency_escalation().
    """
    category = verified_json.get("category", {}).get("value")
    severity = verified_json.get("severity", {}).get("value")
    description = verified_json.get("description", {}).get("value") or ""

    result = rule_based_route(category, severity)
    if result is not None:
        routing = {**result, "routing_source": "rule"}
    elif live:
        try:
            if provider == "groq":
                llm_result = call_groq_route(category, severity, description)
            elif provider == "gemini":
                llm_result = call_gemini_route(category, severity, description)
            else:
                raise ValueError(f"Unknown provider: {provider}")
            routing = {**llm_result, "routing_source": "llm"}
        except Exception as e:
            print(f"[action_agent] LLM routing failed ({e}), using default route.")
            routing = {**DEFAULT_ROUTE, "routing_source": "default"}
    else:
        routing = {**DEFAULT_ROUTE, "routing_source": "default"}

    emergency = verified_json.get("emergency", {}).get("value")
    reporter_name = verified_json.get("reporter_name", {}).get("value")
    escalation = None
    if emergency == "yes" and reporter_name:
        escalation = send_emergency_escalation(verified_json, routing)

    routing["escalation"] = escalation
    return routing


# --- Emergency escalation -------------------------------------------------

def _build_escalation_message(verified_json: dict, routing: dict) -> str:
    location = verified_json.get("location", {}).get("value") or "not stated"
    description = verified_json.get("description", {}).get("value") or "not stated"
    reporter = verified_json.get("reporter_name", {}).get("value") or "unknown"
    team = routing.get("team", "unknown")

    return (
        f"🚨 EMERGENCY reported on site\n"
        f"Reported by: {reporter}\n"
        f"Location: {location}\n"
        f"What happened: {description}\n"
        f"Routed to: {team}\n"
        f"This was reported via the SiteOps Voice Agent and requires immediate attention."
    )


def send_escalation_email(message: str) -> dict:
    """Returns {"sent": bool, "error": str|None}. Degrades independently —
    a missing/misconfigured SMTP setup never crashes the pipeline, and
    never gets silently reported as sent."""
    required = ["SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD", "ALERT_EMAIL_FROM", "ALERT_EMAIL_TO"]
    missing = [k for k in required if not os.environ.get(k)]
    if missing:
        return {"sent": False, "error": f"email not configured, missing: {missing}"}

    try:
        msg = MIMEText(message)
        msg["Subject"] = "🚨 SiteOps Emergency Alert"
        msg["From"] = os.environ["ALERT_EMAIL_FROM"]
        msg["To"] = os.environ["ALERT_EMAIL_TO"]

        with smtplib.SMTP(os.environ["SMTP_HOST"], int(os.environ["SMTP_PORT"])) as server:
            server.starttls()
            server.login(os.environ["SMTP_USER"], os.environ["SMTP_PASSWORD"])
            server.send_message(msg)
        return {"sent": True, "error": None}
    except Exception as e:
        return {"sent": False, "error": str(e)}


def send_escalation_webhook(message: str, url_env_var: str, channel_label: str) -> dict:
    """Shared logic for Slack and Teams — both currently accept a simple
    {"text": "..."} POST body. Returns {"sent": bool, "error": str|None}."""
    url = os.environ.get(url_env_var)
    if not url:
        return {"sent": False, "error": f"{url_env_var} not set"}

    try:
        resp = requests.post(url, json={"text": message}, timeout=10)
        resp.raise_for_status()
        return {"sent": True, "error": None}
    except Exception as e:
        return {"sent": False, "error": f"{channel_label} webhook failed: {e}"}


def send_emergency_escalation(verified_json: dict, routing: dict) -> dict:
    """Fires all configured channels for a confirmed emergency. Each channel
    is attempted independently — one failing (e.g. no SMTP configured yet)
    never blocks or hides the status of the others. Returns per-channel
    results so the caller/audit log can see exactly what did and didn't go
    out, rather than a single collapsed True/False."""
    message = _build_escalation_message(verified_json, routing)

    return {
        "email": send_escalation_email(message),
        "slack": send_escalation_webhook(message, "SLACK_WEBHOOK_URL", "Slack"),
        "teams": send_escalation_webhook(message, "TEAMS_WEBHOOK_URL", "Teams"),
    }