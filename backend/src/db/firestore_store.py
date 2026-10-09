"""
Firestore persistence for SiteOps Voice Agent.

This is the ONLY file that talks to Firestore. Everything else (main.py,
the orchestrator) stays unaware of the database — they just call
save_incident() with a finished incident and get back a record.

Collection layout (Native mode, project set by FIRESTORE_PROJECT_ID):

  incidents/{incident_id}
      category, severity, location, description, action_needed,
      emergency, reporter_name        <- plain values, not the nested
                                          {"value": ..., "source_span": ...}
                                          shape the graph uses internally.
                                          Flattened here so Firestore's
                                          console and simple dashboard
                                          queries don't need to unwrap it.
      status            "complete" | "rejected"
      routing_team, routing_action, routing_source
      escalation        dict, as returned by the Router (email/slack/teams)
      reviewed_by       string the reviewer typed in (no auth yet — see
                         Build Plan Section 9, "known limits")
      reviewed_at       Firestore server timestamp (set by the server,
                         not the laptop's clock, so it's trustworthy even
                         if a laptop's clock is wrong)

This flattening is a deliberate, one-way copy for storage and the
dashboard. The graph's own in-memory state (with source_span, verified,
etc.) is untouched and still what /clarify and /review operate on while
an incident is in progress.
"""

import json
import os
from typing import Optional

import requests
from google.cloud import firestore
from src.translate import translate_fields_to_english

_client: Optional[firestore.Client] = None

INCIDENTS_COLLECTION = "incidents"

# Free-text fields that may contain Hinglish and need translating before
# storage. category/severity/emergency are already fixed English enum
# values from the schema, so they're left untouched. reporter_name is a
# proper noun and is also left untouched.
TRANSLATABLE_FIELDS = ["location", "description", "action_needed"]

# Same model your other agents already use (extractor_agent.py,
# verifier_agent.py, action_agent.py, clarification_agent.py) — kept
# consistent rather than introducing a second model/library for one
# feature. Same endpoint style too: plain requests.post, no groq package.
GROQ_MODEL = "openai/gpt-oss-120b"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"


def get_client() -> firestore.Client:
    """Lazy singleton — created on first use, not at import time. This
    means importing this module never fails just because GCP isn't
    configured yet; it only fails when you actually try to save."""
    global _client
    if _client is None:
        project_id = os.environ.get("FIRESTORE_PROJECT_ID")
        if not project_id:
            raise RuntimeError(
                "FIRESTORE_PROJECT_ID is not set in .env — cannot connect to Firestore."
            )
        _client = firestore.Client(project=project_id)
    return _client




def _flatten_fields(fields: dict) -> dict:
    """Converts {"category": {"value": "safety_hazard", ...}, ...} into
    {"category": "safety_hazard", ...} for storage. Firestore CAN store
    nested dicts fine — this is a readability choice, not a technical
    requirement, so simple dashboard queries don't need to reach into
    nested maps."""
    return {k: v.get("value") for k, v in fields.items()}


def save_incident(incident_id: str, state: dict, reviewed_by: str,
                   reporter_employee_id: Optional[str] = None) -> dict:
    """
    Called once, right after a human approves or rejects (main.py's
    /review route, after resume_incident() returns a terminal status).
    Writes one document, merge=True so re-saving the same incident_id
    (e.g. a retry) updates rather than duplicates.

    state is the FULL orchestrator snapshot (get_incident_snapshot's
    return value, not the trimmed _snapshot_response) — it must include
    'transcript', which is preserved verbatim in original_transcript.
    Every other free-text field is translated to English before storage;
    category/severity/emergency/reporter_name are stored as-is.

    reporter_employee_id: who filed the report, captured client-side at
    the lightweight role gate (no real login yet — see Build Plan
    Section 9, "known limits"). Kept separate from reporter_name, which
    is the graph's own emergency-only field.
    """
    client = get_client()
    routing = state.get("routing") or {}
    flat_fields = _flatten_fields(state.get("fields") or {})

    to_translate = {k: flat_fields.get(k) for k in TRANSLATABLE_FIELDS}
    translated = translate_fields_to_english(to_translate)
    flat_fields.update(translated)

    doc = {
        **flat_fields,
        "original_transcript": state.get("transcript"),
        "status": state.get("status"),
        "routing_team": routing.get("team"),
        "routing_action": routing.get("action"),
        "routing_source": routing.get("routing_source"),
        "escalation": state.get("escalation"),
        "reviewed_by": reviewed_by or "unknown",
        "reviewed_at": firestore.SERVER_TIMESTAMP,
        "reporter_employee_id": reporter_employee_id,
    }

    client.collection(INCIDENTS_COLLECTION).document(incident_id).set(doc, merge=True)
    return doc


def list_recent_incidents(limit: int = 20, reporter_employee_id: Optional[str] = None,
                           anonymize: bool = False) -> list[dict]:
    """For the history page and the worker's "My Reports" list. Newest
    first. Returns plain dicts with the document id folded in as
    'incident_id', ready to hand to the frontend as JSON.

    reporter_employee_id: if given, only rows filed by that person are
    returned. Filtered in Python after fetching (not a Firestore `where`)
    so this doesn't require a composite index — fine at demo scale.

    anonymize: strips reporter_employee_id and reviewed_by before
    returning, for a worker-facing view of everyone else's incidents.
    """
    client = get_client()
    fetch_limit = max(limit, 100) if reporter_employee_id else limit
    query = (
        client.collection(INCIDENTS_COLLECTION)
        .order_by("reviewed_at", direction=firestore.Query.DESCENDING)
        .limit(fetch_limit)
    )
    results = []
    for snap in query.stream():
        row = snap.to_dict()
        row["incident_id"] = snap.id
        if row.get("reviewed_at") is not None:
            row["reviewed_at"] = row["reviewed_at"].isoformat()
        results.append(row)

    if reporter_employee_id:
        results = [r for r in results if r.get("reporter_employee_id") == reporter_employee_id]
    results = results[:limit]

    if anonymize:
        for r in results:
            r.pop("reporter_employee_id", None)
            r.pop("reviewed_by", None)

    return results


def get_dashboard_summary() -> dict:
    """Counts for the small dashboard: this calendar month, by severity,
    by category, and approved vs rejected. Firestore has no SQL-style
    GROUP BY, so this pulls this month's documents and counts in Python —
    fine at demo scale (dozens to low hundreds of incidents), not meant
    to scale to millions of rows."""
    import datetime

    client = get_client()
    now = datetime.datetime.now(datetime.timezone.utc)
    month_start = datetime.datetime(now.year, now.month, 1, tzinfo=datetime.timezone.utc)

    query = client.collection(INCIDENTS_COLLECTION).where(
        "reviewed_at", ">=", month_start
    )

    by_severity: dict[str, int] = {}
    by_category: dict[str, int] = {}
    approved = 0
    rejected = 0
    total = 0

    for snap in query.stream():
        row = snap.to_dict()
        total += 1
        if row.get("status") == "complete":
            approved += 1
        elif row.get("status") == "rejected":
            rejected += 1
        sev = row.get("severity") or "unspecified"
        cat = row.get("category") or "unspecified"
        by_severity[sev] = by_severity.get(sev, 0) + 1
        by_category[cat] = by_category.get(cat, 0) + 1

    return {
        "month": now.strftime("%B %Y"),
        "total": total,
        "approved": approved,
        "rejected": rejected,
        "by_severity": by_severity,
        "by_category": by_category,
    }