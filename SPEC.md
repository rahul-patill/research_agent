# SPEC: Research Agent

## Goal
Given a question, the agent plans, searches the web, reads sources, and returns a short answer with citations (source URLs).

## Version 1 scope
- One agent.
- Two tools:
  - `web_search(query)`: returns results, each with a title, URL and snippet.
  - `fetch_url(url)`: downloads a page and returns readable text, truncated to about 4,000 characters.
- A single answer with sources.

## Output format
- A short answer in plain text.
- A "Sources" list of the URLs the agent actually fetched and used.
- If the sources don't support an answer, the agent says so instead of guessing.

## Tech
- Language: Python (in a `.venv` virtual environment).
- Model: Google Gemini, using the cheapest suitable model. The exact model name is chosen in Step 3 or 4 after checking the current docs.
- API key: `GOOGLE_API_KEY` in `.env` (never committed).
- Dependencies allowed so far:
  - `deepagents`, `langgraph`, `python-dotenv` (installed in Step 0)
  - A Gemini SDK: `google-genai` for the hand-written loop (Steps 2-3), and `langchain-google-genai` if Deep Agents needs it (Step 4)
  - `httpx` (download pages) and `trafilatura` (extract readable text) for `fetch_url`
  - `tavily-python` for `web_search` (needs `TAVILY_API_KEY` in `.env`)
  - `fastapi` and `uvicorn` for the replay viewer in `demo/` (added after Step 13, approved by the project owner)

## Replay viewer (added after Step 13)
A small FastAPI app in `demo/` that replays recorded runs of the agent as a timeline, with the final answer, a citation check and the eval comparison. It serves pre-built JSON files and a static page. It does not import the agent, call any model or need any API key, so it costs no tokens and is safe to host. Visitors cannot ask their own questions.

## Out of scope for this version
These come in later steps and must not be built early:
- Sub-agents (Step 7)
- A shared filesystem / workspace (Step 6)
- Human approval before saving (Step 8)
- An evaluation suite (Steps 9-12)
- Run tracing to files (Step 5)
- A live web UI where visitors run the agent themselves (it would spend tokens and need rate limits), a database, or hosting the agent itself. The recorded-run replay viewer is in scope, see below.
