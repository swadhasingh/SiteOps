"""SiteOps FastAPI API.

React is a separate Vite frontend. This service is API-only: Firebase
Authentication verifies identity, Firestore user profiles provide RBAC/site
authorization, and the existing LangGraph/agent pipeline does the incident
work.
"""

import os
import requests

from dotenv import load_dotenv
load_dotenv()

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from src.auth import CurrentUser, get_current_user, require_manager
from src.langgraph_orchestrator import (
    build_incident_graph,
    start_incident,
    resume_incident,
    get_incident_snapshot,
)
from src.db import firestore_store

app = FastAPI(title="SiteOps Voice Agent", version="1.0.0")

frontend_origin = os.environ.get("FRONTEND_ORIGIN", "http://localhost:8443")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[frontend_origin],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

graph = build_incident_graph(provider="groq", live=True)
_pending_review_ids: set[str] = set()


class ProcessIncidentRequest(BaseModel):
    incident_id: str = Field(min_length=1)
    transcript: str = Field(min_length=1)
    site_id: str | None = None


class ClarifyRequest(BaseModel):
    incident_id: str
    answers: dict


class ReviewRequest(BaseModel):
    incident_id: str
    decision: str
    edits: dict | None = None


def _snapshot_response(state: dict) -> dict:
    return {
        "incident_id": state.get("incident_id"),
        "status": state.get("status"),
        "fields": state.get("fields"),
        "routing": state.get("routing"),
        "escalation": state.get("escalation"),
        "is_paused": state.get("is_paused"),
        "pending_interrupt": state.get("pending_interrupt"),
        "reporter_employee_id": state.get("reporter_employee_id"),
        "site_id": state.get("site_id"),
        "original_transcript": state.get("original_transcript"),
        "english_transcript": state.get("transcript"),
    }


def _require_incident(incident_id: str) -> dict:
    state = get_incident_snapshot(graph, incident_id)
    if not state.get("incident_id"):
        raise HTTPException(status_code=404, detail=f"No incident found with id '{incident_id}'")
    return state


def _assert_incident_access(state: dict, user: CurrentUser, *, manager_only: bool = False) -> None:
    if manager_only and not user.is_manager:
        raise HTTPException(status_code=403, detail="Manager access required")

    if user.is_admin:
        return

    if user.is_manager:
        if state.get("site_id") not in user.site_ids:
            raise HTTPException(status_code=403, detail="You are not authorized for this site")
        return

    if state.get("reporter_employee_id") != user.employee_id:
        raise HTTPException(status_code=403, detail="You can only access your own report")


def _track_pending(state: dict) -> None:
    incident_id = state.get("incident_id")
    if not incident_id:
        return
    pending = state.get("pending_interrupt")
    if pending and pending.get("type") == "human_review":
        _pending_review_ids.add(incident_id)
    else:
        _pending_review_ids.discard(incident_id)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/auth/me")
def auth_me(user: CurrentUser = Depends(get_current_user)):
    return {
        "uid": user.uid,
        "employee_id": user.employee_id,
        "role": user.role,
        "site_ids": list(user.site_ids),
        "email": user.email,
    }


@app.post("/transcribe")
def transcribe(file: UploadFile = File(...), user: CurrentUser = Depends(get_current_user)):
    """Convert browser audio to a raw transcript. Translation happens later
    in start_incident, before extraction/verification/clarification."""
    del user  # authentication is the authorization boundary for this endpoint
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise HTTPException(status_code=503, detail="Voice transcription is not configured")

    audio = file.file.read()
    if not audio:
        raise HTTPException(status_code=400, detail="Audio file is empty")
    if len(audio) > 15 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Audio file is too large")

    try:
        response = requests.post(
            "https://api.groq.com/openai/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {api_key}"},
            files={"file": (file.filename or "incident.webm", audio, file.content_type or "audio/webm")},
            data={"model": "whisper-large-v3-turbo", "response_format": "json"},
            timeout=90,
        )
        response.raise_for_status()
        return {"transcript": response.json().get("text", "").strip()}
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"Voice transcription failed: {exc}") from exc


@app.post("/process-incident")
def process_incident(req: ProcessIncidentRequest, user: CurrentUser = Depends(get_current_user)):
    site_id = req.site_id
    if site_id is None:
        if len(user.site_ids) != 1:
            raise HTTPException(status_code=400, detail="site_id is required when the account has multiple sites")
        site_id = user.site_ids[0]
    if not user.is_admin and site_id not in user.site_ids:
        raise HTTPException(status_code=403, detail="You are not authorized for this site")

    try:
        state = start_incident(
            graph,
            req.incident_id.strip(),
            req.transcript.strip(),
            reporter_employee_id=user.employee_id,
            site_id=site_id,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    _track_pending(state)
    return _snapshot_response(state)


@app.post("/clarify")
def clarify(req: ClarifyRequest, user: CurrentUser = Depends(get_current_user)):
    state = _require_incident(req.incident_id)
    _assert_incident_access(state, user)

    pending = state.get("pending_interrupt")
    if not state.get("is_paused") or not pending or pending.get("type") != "clarification":
        raise HTTPException(status_code=400, detail="This incident is not waiting for clarification")

    expected_fields = set(pending["step"]["fields"])
    given_fields = set(req.answers.keys())
    if not expected_fields.issubset(given_fields):
        raise HTTPException(
            status_code=400,
            detail=f"Expected answers for {sorted(expected_fields)}, got {sorted(given_fields)}",
        )

    new_state = resume_incident(graph, req.incident_id, req.answers)
    _track_pending(new_state)
    return _snapshot_response(new_state)


@app.post("/review")
def review(req: ReviewRequest, user: CurrentUser = Depends(require_manager)):
    state = _require_incident(req.incident_id)
    _assert_incident_access(state, user, manager_only=True)

    if req.decision not in ("approve", "edit", "reject"):
        raise HTTPException(status_code=400, detail="decision must be 'approve', 'edit' or 'reject'")
    if req.decision == "edit" and not req.edits:
        raise HTTPException(status_code=400, detail="edits must be provided when decision is 'edit'")

    decision_payload = {"decision": req.decision, "edits": req.edits or {}}
    new_state = resume_incident(graph, req.incident_id, decision_payload)
    _track_pending(new_state)

    if new_state.get("status") in ("complete", "rejected"):
        try:
            firestore_store.save_incident(
                req.incident_id,
                new_state,
                reviewed_by_employee_id=user.employee_id,
                reporter_employee_id=new_state.get("reporter_employee_id"),
                site_id=new_state.get("site_id"),
            )
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Decision recorded, but database save failed: {exc}") from exc

    return _snapshot_response(new_state)


@app.get("/incident/{incident_id}")
def get_incident(incident_id: str, user: CurrentUser = Depends(get_current_user)):
    state = _require_incident(incident_id)
    _assert_incident_access(state, user)
    return _snapshot_response(state)


@app.get("/pending-reviews")
def pending_reviews(user: CurrentUser = Depends(require_manager)):
    results = []
    for incident_id in list(_pending_review_ids):
        try:
            state = get_incident_snapshot(graph, incident_id)
        except Exception:
            _pending_review_ids.discard(incident_id)
            continue

        if state.get("site_id") not in user.site_ids and not user.is_admin:
            continue

        pending = state.get("pending_interrupt")
        if not state.get("is_paused") or not pending or pending.get("type") != "human_review":
            _pending_review_ids.discard(incident_id)
            continue

        fields = state.get("fields") or {}
        results.append({
            "incident_id": incident_id,
            "category": (fields.get("category") or {}).get("value"),
            "severity": (fields.get("severity") or {}).get("value"),
            "location": (fields.get("location") or {}).get("value"),
            "emergency": (fields.get("emergency") or {}).get("value"),
            "reporter_employee_id": state.get("reporter_employee_id"),
            "site_id": state.get("site_id"),
        })

    results.sort(key=lambda row: row.get("emergency") != "yes")
    return {"pending": results}


@app.get("/incidents")
def list_incidents(limit: int = 20, user: CurrentUser = Depends(get_current_user)):
    limit = max(1, min(limit, 100))
    if user.is_worker:
        incidents = firestore_store.list_recent_incidents(
            limit=limit,
            reporter_employee_id=user.employee_id,
        )
    else:
        incidents = firestore_store.list_recent_incidents(
            limit=limit,
            site_ids=list(user.site_ids),
        )
    return {"incidents": incidents}


@app.get("/dashboard-summary")
def dashboard_summary(user: CurrentUser = Depends(require_manager)):
    return firestore_store.get_dashboard_summary(list(user.site_ids))
