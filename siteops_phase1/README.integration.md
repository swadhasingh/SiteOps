# SiteOps Voice Agent

A voice-based site incident assistant that extracts what was actually said,
asks — one question at a time — for anything important that's missing,
verifies every fact against the transcript, and requires human approval
before saving anything.

See the companion docs for full detail:
- Review 0 Proposal (problem, literature, gap, objectives)
- Build Plan & Architecture (pipeline, file structure, day-by-day plan)
- Working Guide & GCP Deployment (exact build order, deploy steps)

## Where things stand

- [x] Step 1 — Repo skeleton + incident schema (`data/schema/incident_schema.json`)
- [x] Step 2 — Bare FastAPI `/health` endpoint
- [ ] Step 3 — Local Postgres via Docker Compose
- [ ] Step 4 — Extractor Agent (tested standalone)
- [ ] Step 5 — Verifier Agent
- [x] Step 6 — Clarification Agent — built + fallback-tested standalone (`src/agents/clarification_agent.py`)
- [ ] Step 7 — Action/Router Agent
- [ ] Step 8 — Orchestrator (chain all four)
- [ ] Step 9 — Database wiring
- [ ] Step 10 — Frontend (review form + dashboard)
- [ ] Step 11 — ASR (voice input) — added last, deliberately
- [ ] Step 12 — Eval script (Extractor-alone vs Extractor+Verifier)
- [ ] Step 13 — Deploy to GCP Cloud Run

## Why Clarification is a 4th agent, not just orchestration

It was built out of order (before Extractor/Verifier) to settle a design
question first: does it do any real reasoning, or is it just a fixed
loop over the schema? As specced, deciding *which* missing field to ask
about first — and whether two can be combined into one question — based
on how urgent the transcript sounds, requires judgment a lookup table
can't do. The question wording and valid options themselves stay fixed
from `incident_schema.json` — only the order/merge decision is agentic.
It falls back to safe schema-default order if the LLM call fails.

Test it yourself:
```bash
python3 -m src.agents.test_clarification_agent          # fallback, no API key needed
python3 -m src.agents.test_clarification_agent --live    # real reasoning, needs GEMINI_API_KEY in .env (free — no billing)
```
Compare the two test cases in `--live` mode — the "urgent" one should
reorder emergency/severity ahead of duration, and may merge them into
one question. If it doesn't behave any differently from the fallback,
that's a real finding worth reporting, not something to hide.


## Quickstart (local)

```bash
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env              # fill in real values later, not needed for /health yet

uvicorn src.main:app --reload --port 8000
```

In another terminal:

```bash
curl http://localhost:8000/health
# {"status":"ok"}
```

If that works, your Python + FastAPI environment is confirmed working
before any agent logic gets added.
