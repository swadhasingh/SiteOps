"""
LangGraph orchestrator for the SiteOps incident pipeline.

Graph shape (matches Build Plan V3, Section 3):

  extract -> verify -> check_status --(missing fields?)--> ask_clarification -> [back to check_status]
                              |
                       (nothing missing)
                              v
                            route -> human_review --(edited?)--> [back to route, then human_review]
                                            |
                                   (approved / rejected)
                                            v
                                           END

check_status is where emergency escalation is checked on every pass —
not just once at the end — so a confirmed emergency notifies management
the moment a reporter_name is known, even if category/severity/etc. are
still unanswered. This mirrors the earlier plain-Python Orchestrator's
_maybe_escalate logic exactly, just as a graph node now instead of a
class method. Escalation is fired at most once per incident, guarded by
state["escalation"] staying non-None afterward — route_node passes
skip_escalation=True if check_status already sent it, so completing the
record never sends a duplicate alert.

--- Why interrupt() instead of a custom state machine ---

interrupt() pauses graph execution at that exact point and returns
control to the caller; resuming later with Command(resume=answer)
continues from right after the interrupt() call, with `answer` as its
return value. This is LangGraph's built-in human-in-the-loop primitive,
and it's what makes both the clarification loop and the human-review
step work over separate, stateless HTTP requests: the FastAPI route
that will sit on top of this just needs to invoke() to start, and
invoke(Command(resume=...)) to continue, keyed by a thread_id (the
incident_id).

--- Persistence split ---

The checkpointer below (MemorySaver, swap for a persistent one later)
holds IN-PROGRESS incident state, keyed by thread_id. This replaces what
a custom IncidentStore would otherwise need to do for that purpose.
IncidentStore (src/db/store.py) is now only for APPROVED, final records
— the Firestore write happens after human_review_node reaches "complete",
not before. This matches the plan's own diagram: state lives in
LangGraph until Human Review; Firestore only holds the accepted result.

--- Clarification cycle limit ---

Per the Build Plan's Phase 3 requirement ("clarification loop with a
maximum number of cycles"), MAX_CLARIFICATION_CYCLES caps how many
rounds of questions can be asked before the graph forces the incident
through to routing/review anyway, flagging
clarification_cycle_limit_reached=True so a human reviewer can see the
record is incomplete rather than the graph looping forever on a broken
LLM response or a persistently-missing field.

--- Translation on the review card ---

human_review_node shows the manager a TRANSLATED COPY of location/
description/action_needed (English, even if the original report was in
Hindi/Hinglish) so the review screen reads uniformly. This does NOT
change what's actually stored in state["fields"] — the real record keeps
whatever the extractor/clarification put there. If the manager approves
without editing, Firestore still translates again at save time (see
firestore_store.py) — that's a harmless repeat, not a conflict. If the
manager clicks Edit, their typed value becomes the new real value,
whatever language they typed it in.
"""

from typing import Optional, TypedDict

from langgraph.graph import StateGraph, END
from langgraph.types import interrupt
from langgraph.checkpoint.memory import MemorySaver

from src.agents.extractor_agent import extract, INCIDENT_SCHEMA
from src.agents.verifier_agent import verify
from src.agents.clarification_agent import decide_clarifications, make_groq_llm_call
from src.agents.action_agent import route
from src.translate import translate_fields_to_english

MAX_CLARIFICATION_CYCLES = 10


class IncidentState(TypedDict):
    incident_id: str
    transcript: str
    fields: dict
    status: str  # in_progress | needs_clarification | ready_to_route | complete | rejected | edited
    escalation: Optional[dict]
    routing: Optional[dict]
    clarification_cycles: int
    clarification_cycle_limit_reached: bool
    next_step: Optional[dict]


def _fire_escalation_if_needed(state: IncidentState) -> dict:
    """Shared by check_status_node. Returns a partial state update — empty
    dict if nothing to do. Fires at most once per incident (see module
    docstring)."""
    if state.get("escalation") is not None:
        return {}
    emergency = state["fields"].get("emergency", {}).get("value")
    reporter_name = state["fields"].get("reporter_name", {}).get("value")
    if emergency == "yes" and reporter_name:
        routing_now = route(state["fields"], provider="groq", live=False)
        return {"escalation": routing_now["escalation"]}
    return {}


def build_incident_graph(provider: str = "groq", live: bool = False,
                          use_llm_clarification: bool = True, checkpointer=None):
    """
    Builds and compiles the incident graph. provider/live are baked into
    the node closures (not stored in state) so they don't need to be
    JSON-serializable when a persistent checkpointer is used later.
    """
    llm_call = None
    if use_llm_clarification and live and provider == "groq":
        llm_call = make_groq_llm_call()

    def extract_node(state: IncidentState) -> dict:
        draft = extract(state["transcript"], provider=provider, live=live)
        fields = {k: v for k, v in draft.items() if not k.startswith("_")}
        return {"fields": fields}

    def verify_node(state: IncidentState) -> dict:
        draft_like = {
            k: {"value": v.get("value"), "source_span": v.get("source_span")}
            for k, v in state["fields"].items()
        }
        draft_like["_fallback"] = False
        verified = verify(draft_like, state["transcript"], INCIDENT_SCHEMA, provider=provider, live=live)
        fields = {k: v for k, v in verified.items() if not k.startswith("_")}
        return {"fields": fields}

    def check_status_node(state: IncidentState) -> dict:
        updates = _fire_escalation_if_needed(state)
        fields_after_escalation_check = state["fields"]  # escalation check never mutates fields

        steps = decide_clarifications(fields_after_escalation_check, state["transcript"], llm_call=llm_call)

        if steps and state["clarification_cycles"] < MAX_CLARIFICATION_CYCLES:
            updates["status"] = "needs_clarification"
            updates["next_step"] = steps[0]
        else:
            updates["status"] = "ready_to_route"
            updates["next_step"] = None
            if steps:
                updates["clarification_cycle_limit_reached"] = True
        return updates

    def ask_clarification_node(state: IncidentState) -> dict:
        step = state["next_step"]
        answer = interrupt({"type": "clarification", "step": step})
        # answer: {field_name: value, ...} -- one entry, or two for a merged step
        updated_fields = dict(state["fields"])
        for field_name, value in answer.items():
            updated_fields[field_name] = {
                "value": value, "source_span": None,
                "source": "clarification", "verified": True,
            }
        return {"fields": updated_fields, "clarification_cycles": state["clarification_cycles"] + 1}

    def route_node(state: IncidentState) -> dict:
        already_escalated = state.get("escalation") is not None
        routing = route(state["fields"], provider=provider, live=live, skip_escalation=already_escalated)
        updates = {"routing": routing, "status": "ready_to_route"}
        if routing.get("escalation") is not None and state.get("escalation") is None:
            updates["escalation"] = routing["escalation"]
        return updates

    def human_review_node(state: IncidentState) -> dict:
        # Build a translated COPY just for what the manager sees on screen.
        # This does NOT change the real stored data — see module docstring.
        display_fields = dict(state["fields"])
        to_translate = {
            "location": display_fields.get("location", {}).get("value"),
            "description": display_fields.get("description", {}).get("value"),
            "action_needed": display_fields.get("action_needed", {}).get("value"),
        }
        translated = translate_fields_to_english(to_translate)
        for field_name, new_value in translated.items():
            if field_name in display_fields and display_fields[field_name].get("value"):
                display_fields[field_name] = {**display_fields[field_name], "value": new_value}

        decision = interrupt({
            "type": "human_review",
            "fields": display_fields,
            "routing": state["routing"],
            "clarification_cycle_limit_reached": state.get("clarification_cycle_limit_reached", False),
        })
        # decision: {"decision": "approve"|"reject"|"edit", "edits": {field: value, ...}}
        if decision["decision"] == "edit":
            updated_fields = dict(state["fields"])
            for k, v in decision.get("edits", {}).items():
                updated_fields[k] = {**updated_fields.get(k, {}), "value": v, "source": "human_edit"}
            return {"fields": updated_fields, "status": "edited"}  # re-route, then back to human_review
        elif decision["decision"] == "approve":
            return {"status": "complete"}
        else:
            return {"status": "rejected"}

    def check_status_router(state: IncidentState) -> str:
        return "ask_clarification" if state["status"] == "needs_clarification" else "route"

    def review_router(state: IncidentState) -> str:
        return END if state["status"] in ("complete", "rejected") else ("route" if state["status"] == "edited" else "human_review")

    graph = StateGraph(IncidentState)
    graph.add_node("extract", extract_node)
    graph.add_node("verify", verify_node)
    graph.add_node("check_status", check_status_node)
    graph.add_node("ask_clarification", ask_clarification_node)
    graph.add_node("route", route_node)
    graph.add_node("human_review", human_review_node)

    graph.set_entry_point("extract")
    graph.add_edge("extract", "verify")
    graph.add_edge("verify", "check_status")
    graph.add_conditional_edges("check_status", check_status_router,
                                 {"ask_clarification": "ask_clarification", "route": "route"})
    graph.add_edge("ask_clarification", "check_status")
    graph.add_edge("route", "human_review")
    graph.add_conditional_edges("human_review", review_router,
                                 {"human_review": "human_review", "route": "route", END: END})

    return graph.compile(checkpointer=checkpointer or MemorySaver())


def start_incident(graph, incident_id: str, transcript: str) -> dict:
    """Starts a new incident. Returns the paused (or, rarely, immediately
    complete) state. Always pass the SAME incident_id to resume it later."""
    config = {"configurable": {"thread_id": incident_id}}
    initial_state = {
        "incident_id": incident_id,
        "transcript": transcript,
        "fields": {},
        "status": "in_progress",
        "escalation": None,
        "routing": None,
        "clarification_cycles": 0,
        "clarification_cycle_limit_reached": False,
        "next_step": None,
    }
    graph.invoke(initial_state, config=config)
    return get_incident_snapshot(graph, incident_id)


def resume_incident(graph, incident_id: str, resume_value) -> dict:
    """Resumes a paused incident (clarification answer, or a human-review
    decision) with whatever value the paused interrupt() call is waiting for."""
    from langgraph.types import Command
    config = {"configurable": {"thread_id": incident_id}}
    graph.invoke(Command(resume=resume_value), config=config)
    return get_incident_snapshot(graph, incident_id)


def get_incident_snapshot(graph, incident_id: str) -> dict:
    """Returns the current state plus what (if anything) it's paused on."""
    config = {"configurable": {"thread_id": incident_id}}
    snapshot = graph.get_state(config)
    result = dict(snapshot.values)
    result["is_paused"] = bool(snapshot.next)
    result["pending_interrupt"] = None
    if snapshot.interrupts:
        result["pending_interrupt"] = snapshot.interrupts[0].value
    return result