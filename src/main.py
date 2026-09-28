"""
SiteOps Voice Agent — FastAPI entrypoint.

Wraps the LangGraph orchestrator (src/langgraph_orchestrator.py) with
HTTP routes. The graph itself stays the source of truth for an
IN-PROGRESS incident (MemorySaver, in memory, lost on restart).
Firestore only receives a finished incident, once /review reaches
"complete" or "rejected".

Two small in-memory registries support the lightweight worker/manager
split in the frontend (NOT real authentication — see the note on
ReviewRequest.reviewed_by and ProcessIncidentRequest.reporter_employee_id
below):

  _reporter_registry:  incident_id -> employee_id, so a saved record can
                        say who filed it, and a worker's "My Reports"
                        list can be filtered to just their own.
  _pending_review_ids: the set of incident_ids currently paused at
                        human_review, so a manager's dashboard can list
                        "what needs a decision right now" without
                        knowing incident ids in advance. LangGraph's
                        MemorySaver doesn't expose "list every paused
                        thread", so this set is maintained by hand,
                        updated every time a route returns a snapshot.

Also serves the frontend: static/index.html, mounted at "/" as the very
last route below, so it never shadows the API routes.
"""

import os

from dotenv import load_dotenv
load_dotenv()  # must run before firestore_store.get_client() is ever called,
                # so GOOGLE_APPLICATION_CREDENTIALS and FIRESTORE_PROJECT_ID
                # are set in os.environ.

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from src.langgraph_orchestrator import build_incident_graph, start_incident, resume_incident, get_incident_snapshot
from src.db import firestore_store

app = FastAPI(title="SiteOps Voice Agent", version="0.5.0")

# Live mode — makes real Groq calls, so Hinglish/English extraction
# actually fills fields instead of leaving everything null. Requires a
# real GROQ_API_KEY in .env. Flip back to live=False if Groq is
# unreachable (e.g. blocked on the office network) or you want a demo
# that never depends on a live API call succeeding.
graph = build_incident_graph(provider="groq", live=True)

# See module docstring — demo-scope only, reset on every server restart.
_reporter_registry: dict[str, str] = {}
_pending_review_ids: set[str] = set()


# --- Request shapes -------------------------------------------------------

class ProcessIncidentRequest(BaseModel):
    incident_id: str
    transcript: str
    reporter_employee_id: str | None = None  # captured at the lightweight
                                              # role gate, not part of the
                                              # incident schema itself —
                                              # never sent to the agents.


class ClarifyRequest(BaseModel):
    incident_id: str
    answers: dict  # {"emergency": "yes"} or {"category": "...", "severity": "..."}


class ReviewRequest(BaseModel):
    incident_id: str
    decision: str  # "approve" | "edit" | "reject"
    edits: dict | None = None       # only used when decision == "edit"
    reviewed_by: str | None = None  # who made this decision — no login yet,
                                     # so this is typed in by the reviewer.
                                     # Only required (and only saved) on
                                     # approve/reject, not on edit.


# --- Helpers ---------------------------------------------------------------

def _snapshot_response(state: dict) -> dict:
    """Same shape for every route, so the frontend always parses one format."""
    return {
        "incident_id": state.get("incident_id"),
        "status": state.get("status"),
        "fields": state.get("fields"),
        "routing": state.get("routing"),
        "escalation": state.get("escalation"),
        "is_paused": state.get("is_paused"),
        "pending_interrupt": state.get("pending_interrupt"),
    }


def _require_incident(incident_id: str) -> dict:
    state = get_incident_snapshot(graph, incident_id)
    if not state.get("incident_id"):
        raise HTTPException(status_code=404, detail=f"No incident found with id '{incident_id}'")
    return state


def _track_pending(state: dict) -> None:
    """Keeps _pending_review_ids in sync with reality. Call this after
    every start_incident/resume_incident, before returning a response."""
    incident_id = state.get("incident_id")
    if not incident_id:
        return
    pending = state.get("pending_interrupt")
    if pending and pending.get("type") == "human_review":
        _pending_review_ids.add(incident_id)
    else:
        _pending_review_ids.discard(incident_id)


# --- API routes --------------------------------------------------------

@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/process-incident")
def process_incident(req: ProcessIncidentRequest):
    if not req.transcript or not req.transcript.strip():
        raise HTTPException(status_code=400, detail="transcript cannot be empty")
    if not req.incident_id or not req.incident_id.strip():
        raise HTTPException(status_code=400, detail="incident_id cannot be empty")

    if req.reporter_employee_id and req.reporter_employee_id.strip():
        _reporter_registry[req.incident_id] = req.reporter_employee_id.strip()

    state = start_incident(graph, req.incident_id, req.transcript)
    _track_pending(state)
    return _snapshot_response(state)


@app.post("/clarify")
def clarify(req: ClarifyRequest):
    state = _require_incident(req.incident_id)

    if not state.get("is_paused") or not state.get("pending_interrupt") or state["pending_interrupt"]["type"] != "clarification":
        raise HTTPException(
            status_code=400,
            detail=f"Incident '{req.incident_id}' is not waiting for a clarification answer right now."
        )

    expected_fields = set(state["pending_interrupt"]["step"]["fields"])
    given_fields = set(req.answers.keys())
    if not expected_fields.issubset(given_fields):
        raise HTTPException(
            status_code=400,
            detail=f"Expected answers for {sorted(expected_fields)}, got {sorted(given_fields)}"
        )

    new_state = resume_incident(graph, req.incident_id, req.answers)
    _track_pending(new_state)
    return _snapshot_response(new_state)


@app.post("/review")
def review(req: ReviewRequest):
    state = _require_incident(req.incident_id)

    if not state.get("is_paused") or not state.get("pending_interrupt") or state["pending_interrupt"]["type"] != "human_review":
        raise HTTPException(
            status_code=400,
            detail=f"Incident '{req.incident_id}' is not waiting for a review decision right now."
        )

    if req.decision not in ("approve", "edit", "reject"):
        raise HTTPException(status_code=400, detail="decision must be 'approve', 'edit' or 'reject'")
    if req.decision == "edit" and not req.edits:
        raise HTTPException(status_code=400, detail="edits must be provided when decision is 'edit'")
    if req.decision in ("approve", "reject") and not (req.reviewed_by and req.reviewed_by.strip()):
        raise HTTPException(status_code=400, detail="reviewed_by is required to approve or reject")

    decision_payload = {"decision": req.decision, "edits": req.edits or {}}
    new_state = resume_incident(graph, req.incident_id, decision_payload)
    _track_pending(new_state)
    response = _snapshot_response(new_state)

    # Save to Firestore only once the incident reaches a terminal state.
    # "edit" loops back to human_review (see orchestrator), so it never
    # lands here — nothing is saved until approve or reject.
    if new_state.get("status") in ("complete", "rejected"):
        try:
            firestore_store.save_incident(
                req.incident_id, new_state, req.reviewed_by,
                reporter_employee_id=_reporter_registry.get(req.incident_id),
            )
        except Exception as e:
            # The graph's decision already succeeded — don't lose that
            # just because the database write failed. Report it clearly
            # instead of pretending it saved (TC-DB-005's spirit).
            raise HTTPException(
                status_code=502,
                detail=f"Decision recorded, but saving to the database failed: {e}"
            )

    return response


@app.get("/incident/{incident_id}")
def get_incident(incident_id: str):
    """Not in your original scope, but the frontend needs this: a way to
    reload an incident's current state on page refresh, or for a manager
    to open a specific pending item from the queue. Read-only, no side
    effects. Only looks at the graph's in-progress state, not Firestore —
    use /incidents for saved history."""
    return _snapshot_response(_require_incident(incident_id))


@app.get("/pending-reviews")
def pending_reviews():
    """Manager dashboard: everything currently waiting for a decision,
    across all incidents — not just one the caller already knows the id
    of. Emergencies are sorted to the top."""
    results = []
    for incident_id in list(_pending_review_ids):
        try:
            state = get_incident_snapshot(graph, incident_id)
        except Exception:
            _pending_review_ids.discard(incident_id)
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
            "reporter_employee_id": _reporter_registry.get(incident_id),
        })
    results.sort(key=lambda r: r.get("emergency") != "yes")  # "yes" (emergencies) first
    return {"pending": results}


@app.get("/incidents")
def list_incidents(limit: int = 20, reporter_employee_id: str | None = None, anonymize: bool = False):
    """History page (manager, full detail) and 'My Reports' (worker,
    filtered to their own employee id). anonymize=true strips who filed
    and who reviewed — used for a worker viewing incidents they didn't
    file themselves."""
    incidents = firestore_store.list_recent_incidents(
        limit=limit, reporter_employee_id=reporter_employee_id, anonymize=anonymize
    )
    return {"incidents": incidents}


@app.get("/dashboard-summary")
def dashboard_summary():
    """Manager dashboard: this month's counts by severity/category and
    approved-vs-rejected totals."""
    return firestore_store.get_dashboard_summary()


# --- Frontend ------------------------------------------------------------
# Must be the LAST route registered. StaticFiles(html=True) serves
# static/index.html for "/" and any unmatched path, so if this were
# mounted earlier it would swallow requests meant for the API routes above.
app.mount("/", StaticFiles(directory="static", html=True), name="static")


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run("src.main:app", host="0.0.0.0", port=port, reload=True)