"""Steps 4-5: the research agent on the Deep Agents harness, with tracing.

Same two tools as raw_loop.py, but the tool loop, planning and message
history are now handled by the harness instead of our own `for` loop.

Docs used: https://docs.langchain.com/oss/python/deepagents/quickstart
Usage: python agent.py "What is the latest stable version of Python?"
"""
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

import uuid

from deepagents import create_deep_agent
from deepagents.backends import CompositeBackend, FilesystemBackend, StateBackend
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

# Reuse the exact tool functions from Step 3 (this also loads .env).
import raw_loop

WORKSPACE_DIR = Path(__file__).parent / "workspace"  # absolute path

MAX_SUBAGENTS = 3  # the orchestrator is told never to delegate more than this

ORCHESTRATOR_PROMPT = f"""You are a research orchestrator. You do not search the web yourself.

1. Split the user's question into 2 to {MAX_SUBAGENTS} distinct subtopics. Never use more than
   {MAX_SUBAGENTS}. A simple single-fact question may use just one.
2. For each subtopic, call the task tool with subagent_type "researcher". In the task
   description give the subtopic and a short file name, for example
   "Research X. Save notes to /workspace/x.md". Start all of them in the same turn.
3. When they finish, read every notes file in /workspace/ with ls and read_file.
4. Write a short answer that combines the notes, based only on them. End it with a
   "Sources" list containing the URLs found in the notes.
5. Call save_report once, with that full answer as the content. A person reviews it
   before it is saved. If they reject it, do not retry: tell them it was not saved.
6. After it is saved, reply with the same answer.
If the notes don't support an answer, say so instead of guessing."""

SUBAGENT_PROMPT = """You research ONE subtopic given in your task. Ignore anything else.

1. Use web_search to find sources for your subtopic.
2. Use fetch_url to read the most relevant pages. Do not rely on search snippets alone.
3. Write your notes to the file named in your task using write_file: each source's URL,
   then the key facts from it. Only record facts from pages you fetched.
4. Reply with one short line saying which file you wrote."""


def web_search(query: str) -> list[dict]:
    """Search the web. Returns up to 5 results, each with a title, URL and
    short snippet. Use this first to find sources for a question. Snippets are
    brief, so call fetch_url on a promising result to read it."""
    return raw_loop.web_search(query)


def fetch_url(url: str) -> str:
    """Download one web page and return its readable text, cut to about 4,000
    characters. Use this to read a page found by web_search before relying on
    it. Only pass URLs that came from web_search results."""
    return raw_loop.fetch_url(url)


REPORT_PATH = Path(__file__).parent / "report.md"


def save_report(content: str) -> str:
    """Save the final research answer to report.md. Call this once, after the
    answer is written, with the full answer text (including Sources) as content.
    A person must approve it before it is saved."""
    REPORT_PATH.write_text(content, encoding="utf-8")
    return f"Report saved to {REPORT_PATH.name}"


def reset_workspace() -> None:
    """Delete and recreate workspace/ so every run starts with no old notes."""
    shutil.rmtree(WORKSPACE_DIR, ignore_errors=True)
    WORKSPACE_DIR.mkdir()


def build_backend() -> CompositeBackend:
    """Only /workspace/ is real files on disk. Everything else stays in memory.

    virtual_mode=True stops the agent from reaching outside workspace/, so it
    cannot read .env or any other project file.
    """
    return CompositeBackend(
        default=StateBackend(),
        routes={
            "/workspace/": FilesystemBackend(root_dir=WORKSPACE_DIR, virtual_mode=True)
        },
    )


RESEARCHER = {
    "name": "researcher",
    "description": (
        "Researches one subtopic on the web and saves notes with sources to a "
        "file in /workspace/. Give it the subtopic and the file name to write."
    ),
    "system_prompt": SUBAGENT_PROMPT,
    "tools": [web_search, fetch_url],  # only the sub-agent gets the web tools
}


def build_agent():
    """Create the orchestrator. It has no web tools, so it must delegate."""
    return create_deep_agent(
        model=f"google_genai:{raw_loop.MODEL}",
        tools=[save_report],
        system_prompt=ORCHESTRATOR_PROMPT,
        subagents=[RESEARCHER],
        backend=build_backend(),
        # Pause before save_report runs, so a person can approve, edit or reject.
        interrupt_on={"save_report": {"allowed_decisions": ["approve", "edit", "reject"]}},
        # A checkpointer saves the run's state at the pause so it can resume.
        checkpointer=MemorySaver(),
    )


def message_to_event(message, source: str) -> dict:
    """Turn one LangChain message into a small, JSON-friendly trace event.

    `source` is "main" for the orchestrator or a sub-agent's graph path.
    """
    event = {"source": source, "type": message.type, "text": message.text}
    if message.type == "ai":  # a model call; may ask for tools
        event["tool_calls"] = [
            {"name": c["name"], "args": c["args"]} for c in message.tool_calls
        ]
        event["usage"] = message.usage_metadata
    elif message.type == "tool":  # a tool result
        event["tool_name"] = message.name
    return event


def print_event(event: dict) -> None:
    """Print one trace event on a few lines (long text is shortened)."""
    short = event["text"][:300].replace("\n", " ")
    who = "model" if event["source"] == "main" else "  sub-agent"
    if event["type"] == "ai":
        for call in event["tool_calls"]:
            print(f"[{who}] calls {call['name']}({call['args']})")
        if short:
            print(f"[{who}] says: {short}")
    elif event["type"] == "tool":
        print(f"[{who} tool result: {event['tool_name']}] {short}...")


def read_edited_text() -> str:
    """Read the replacement report from the terminal, up to a line saying END."""
    print("Type the new report. Finish with a line containing only END.")
    lines = []
    while (line := input()).strip() != "END":
        lines.append(line)
    return "\n".join(lines)


def ask_human(request: dict) -> dict:
    """Show the draft and return the person's decision for the paused action."""
    print("\n=== Draft report (not saved yet) ===")
    print(request["args"]["content"])
    print("====================================")
    while True:
        choice = input("approve / reject / edit > ").strip().lower()
        if choice == "approve":
            return {"type": "approve"}
        if choice == "reject":
            return {"type": "reject", "message": "The user rejected the report. Do not save it."}
        if choice == "edit":
            args = {"content": read_edited_text()}
            return {"type": "edit", "edited_action": {"name": request["name"], "args": args}}
        print("Please type approve, reject or edit.")


def run_with_trace(question: str, auto_approve: bool = False, verbose: bool = True) -> list[dict]:
    """Run the agent, printing and collecting every new message as it appears.

    auto_approve=True approves every draft without asking (used by the evals).
    verbose=False collects the trace without printing it.
    """
    events = []
    agent = build_agent()
    # The thread_id names this run's saved state. Resuming must reuse it.
    config = {"configurable": {"thread_id": str(uuid.uuid4())}}
    stream_input = {"messages": [{"role": "user", "content": question}]}
    while True:
        pending = None
        stream = agent.stream(
            stream_input,
            config=config,
            stream_mode="updates",  # one chunk per graph step, only new messages
            subgraphs=True,  # also stream what happens inside each sub-agent
        )
        for namespace, chunk in stream:  # namespace is () for the orchestrator
            source = "main" if not namespace else "/".join(namespace)
            if "__interrupt__" in chunk:  # the run paused and is waiting for us
                pending = chunk["__interrupt__"][0]
            for update in chunk.values():
                messages = update.get("messages") if isinstance(update, dict) else None
                if not isinstance(messages, list):
                    continue
                for message in messages:
                    events.append(message_to_event(message, source))
                    if verbose:
                        print_event(events[-1])
        if pending is None:  # no pause: the run is finished
            return events
        requests = pending.value["action_requests"]
        if auto_approve:
            decisions = [{"type": "approve"} for _ in requests]
        else:
            decisions = [ask_human(request) for request in requests]
        events.append({"source": "human", "type": "human", "text": "", "decisions": decisions})
        stream_input = Command(resume={"decisions": decisions})  # continue the run


def save_trace(question: str, events: list[dict]) -> Path:
    """Write the full trace to traces/<timestamp>.json."""
    Path("traces").mkdir(exist_ok=True)
    path = Path("traces") / f"{datetime.now():%Y-%m-%d_%H-%M-%S}.json"
    path.write_text(json.dumps({"question": question, "events": events}, indent=2, default=str), encoding="utf-8")
    return path


def final_answer(events: list[dict]) -> str:
    """The orchestrator's last reply that made no tool call, or '' if none."""
    answers = [  # only the orchestrator's own replies, not sub-agents'
        e["text"] for e in events
        if e["source"] == "main" and e["type"] == "ai" and not e["tool_calls"]
    ]
    return answers[-1] if answers else ""


def run_question(question: str, auto_approve: bool = False, verbose: bool = True) -> tuple[list[dict], str]:
    """Run one question from a clean workspace. Returns (trace events, answer)."""
    reset_workspace()
    events = run_with_trace(question, auto_approve, verbose)
    return events, final_answer(events)


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit('Usage: python agent.py "your question"')
    question = " ".join(sys.argv[1:])
    events, answer = run_question(question)
    print("\n=== Final answer ===\n" + (answer or "(none)"))
    print(f"\nTrace saved to {save_trace(question, events)}")


if __name__ == "__main__":
    main()
