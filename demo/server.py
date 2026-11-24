"""FastAPI server for the trace viewer: replays recorded runs, calls no model.

Run from the project root:  python demo/server.py   (then open http://127.0.0.1:8000)

It only reads the JSON files in demo/examples/ and serves the page in
demo/static/. It does not import the agent and needs no API key, so it can be
hosted anywhere without exposing keys or spending tokens.

    GET /api/examples        list of the example runs
    GET /api/examples/{id}   one full recorded run
    GET /api/summary         baseline versus experiment eval numbers
    GET /api/health          liveness check
"""
import json
import os
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles

DEMO_DIR = Path(__file__).parent
EXAMPLES_DIR = DEMO_DIR / "examples"

app = FastAPI(title="Research Agent trace viewer", docs_url="/api/docs", redoc_url=None)


def read_json(path: Path):
    """Read one of the pre-built JSON files, or fail with a clear 404."""
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Not found. Run demo/build_examples.py first.")
    return json.loads(path.read_text(encoding="utf-8"))


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "mode": "replay (no model is called)"}


@app.get("/api/examples")
def list_examples() -> list[dict]:
    return read_json(EXAMPLES_DIR / "index.json")


@app.get("/api/examples/{example_id}")
def get_example(example_id: str) -> dict:
    # Only ids listed in the index are served, so the id can never be used as a file path.
    known = {item["id"] for item in read_json(EXAMPLES_DIR / "index.json")}
    if example_id not in known:
        raise HTTPException(status_code=404, detail="Unknown example.")
    return read_json(EXAMPLES_DIR / f"{example_id}.json")


@app.get("/api/summary")
def get_summary() -> dict:
    return read_json(EXAMPLES_DIR / "summary.json")


# The page itself. Mounted last so the /api routes above take priority.
app.mount("/", StaticFiles(directory=DEMO_DIR / "static", html=True), name="static")


if __name__ == "__main__":
    # Port 8000 by default. Set PORT to change it, for example when another app uses 8000.
    # Set HOST=0.0.0.0 when deploying, so the server is reachable from outside.
    uvicorn.run(app, host=os.environ.get("HOST", "127.0.0.1"), port=int(os.environ.get("PORT", "8000")))
