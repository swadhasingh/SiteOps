"""Firestore persistence for SiteOps.

Firestore stores final incident records plus SiteOps user profiles.
Worker identity is always the employee_id; worker names are never persisted
in incident documents. The emergency-only reporter_name remains in the
in-memory workflow long enough to send Slack/email alerts, but is removed
before persistence.
"""

import datetime
import os
from typing import Optional

from google.cloud import firestore

from src.translate import translate_fields_to_english

_client: Optional[firestore.Client] = None

INCIDENTS_COLLECTION = "incidents"
USERS_COLLECTION = "users"
TRANSLATABLE_FIELDS = ["location", "description", "action_needed"]


def get_client() -> firestore.Client:
    global _client
    if _client is None:
        project_id = os.environ.get("FIRESTORE_PROJECT_ID") or os.environ.get("FIREBASE_PROJECT_ID")
        if not project_id:
            raise RuntimeError("FIRESTORE_PROJECT_ID/FIREBASE_PROJECT_ID is not set")
        _client = firestore.Client(project=project_id)
    return _client


def get_user_profile(uid: str) -> Optional[dict]:
    """Return the authorization profile for a verified Firebase UID."""
    snap = get_client().collection(USERS_COLLECTION).document(uid).get()
    return snap.to_dict() if snap.exists else None


def _flatten_fields(fields: dict) -> dict:
    return {k: v.get("value") for k, v in fields.items()}


def save_incident(
    incident_id: str,
    state: dict,
    reviewed_by_employee_id: str,
    reporter_employee_id: str,
    site_id: str,
) -> dict:
    client = get_client()
    routing = state.get("routing") or {}
    flat_fields = _flatten_fields(state.get("fields") or {})

    # Structured free-text values are normalized to English before storage.
    translated = translate_fields_to_english({k: flat_fields.get(k) for k in TRANSLATABLE_FIELDS})
    flat_fields.update(translated)

    doc = {
        **flat_fields,
        "site_id": site_id,
        "reporter_employee_id": reporter_employee_id,
        "original_transcript": state.get("original_transcript"),
        "english_transcript": state.get("transcript"),
        "status": state.get("status"),
        "routing_team": routing.get("team"),
        "routing_action": routing.get("action"),
        "routing_source": routing.get("routing_source"),
        "escalation": state.get("escalation"),
        "reviewed_by_employee_id": reviewed_by_employee_id,
        "reviewed_at": firestore.SERVER_TIMESTAMP,
    }

    # Deliberately DO NOT persist reporter_name. It is emergency-only and is
    # used transiently to construct the notification message.
    doc.pop("reporter_name", None)

    client.collection(INCIDENTS_COLLECTION).document(incident_id).set(doc, merge=True)
    return doc


def list_recent_incidents(
    limit: int = 20,
    reporter_employee_id: Optional[str] = None,
    site_ids: Optional[list[str]] = None,
) -> list[dict]:
    client = get_client()
    query = client.collection(INCIDENTS_COLLECTION).order_by(
        "reviewed_at", direction=firestore.Query.DESCENDING
    ).limit(max(limit, 100) if reporter_employee_id or site_ids else limit)

    results = []
    for snap in query.stream():
        row = snap.to_dict()
        row["incident_id"] = snap.id
        if row.get("reviewed_at") is not None:
            row["reviewed_at"] = row["reviewed_at"].isoformat()
        results.append(row)

    if reporter_employee_id:
        results = [r for r in results if r.get("reporter_employee_id") == reporter_employee_id]
    if site_ids:
        allowed = set(site_ids)
        results = [r for r in results if r.get("site_id") in allowed]

    return results[:limit]


def get_dashboard_summary(site_ids: list[str]) -> dict:
    client = get_client()
    now = datetime.datetime.now(datetime.timezone.utc)
    month_start = datetime.datetime(now.year, now.month, 1, tzinfo=datetime.timezone.utc)

    query = client.collection(INCIDENTS_COLLECTION).where("reviewed_at", ">=", month_start)
    allowed_sites = set(site_ids)

    by_severity: dict[str, int] = {}
    by_category: dict[str, int] = {}
    approved = rejected = total = 0

    for snap in query.stream():
        row = snap.to_dict()
        if allowed_sites and row.get("site_id") not in allowed_sites:
            continue
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
