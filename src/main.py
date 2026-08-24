"""
SiteOps Voice Agent — FastAPI entrypoint.

Right now this only proves the environment works end to end:
Python + FastAPI + (later) Docker + (later) Cloud Run all agree on how
to start this app and answer a request.

Do not add agent logic here yet. Agents are built and tested standalone
first (src/agents/*.py, run directly from the terminal) — this file only
grows once each agent already works on its own. See the Working Guide,
Steps 4-7.
"""

import os

from fastapi import FastAPI

app = FastAPI(title="SiteOps Voice Agent", version="0.1.0")


@app.get("/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    # Cloud Run injects PORT; default to 8080 to match the Dockerfile.
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run("src.main:app", host="0.0.0.0", port=port, reload=True)
