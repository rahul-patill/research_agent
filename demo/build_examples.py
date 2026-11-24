"""Build the demo's example runs from saved traces and eval results.

Developer tool, run by hand: `python demo/build_examples.py`.
It reads traces/ and evals/results/ (both stay on your machine) and writes
small, self-contained JSON files into demo/examples/, which ARE committed.
The demo server only reads those files, so it never needs the agent code,
the model, or any API key.

Each example holds the run as a list of steps (who did what, with the result
attached to the call that produced it), the final answer, the stats, and the
citation check: which cited URLs the agent had actually fetched.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "evals"))

import run_evals  # noqa: E402  (reuses the eval scoring helpers)

OUT_DIR = Path(__file__).parent / "examples"
MODEL = "gemini-3.5-flash-lite"
BASELINE = "evals/results/2026-11-23_21-59-20.json"
EXPERIMENT = "evals/results/2026-11-24_13-43-53.json"

# (id, tag, title, trace file, [eval result file, question number] or None, note)
EXAMPLES = [
    {
        "id": "latest-python",
        "tag": "Simple lookup",
        "title": "Latest Python version",
        "trace": "traces/2026-11-23_21-52-36.json",
        "result": (BASELINE, 1),
        "recorded": "2026-11-23",
        "note": (
            "The simplest kind of run. The orchestrator hands the question to a "
            "researcher, the researcher searches and reads a page and saves notes, "
            "and the orchestrator answers from those notes. The draft then goes "
            "through the approval step (approved automatically here, because this "
            "run came from the eval suite)."
        ),
    },
    {
        "id": "compare-evals",
        "tag": "Parallel sub-agents",
        "title": "Comparing agent evaluation methods",
        "trace": "traces/2026-11-23_20-43-16.json",
        "result": None,
        "recorded": "2026-11-23",
        "note": (
            "A broad question. The orchestrator splits it into two subtopics and "
            "starts two researchers at the same time. Each writes its own notes "
            "file, and the orchestrator reads both to write one answer. This run "
            "was recorded before the approval step was added. Neither researcher "
            "fetched a page: they worked from search snippets, which is the "
            "behavior the evals later measured."
        ),
    },
    {
        "id": "stale-source",
        "tag": "When it goes wrong",
        "title": "A stale source",
        "trace": "traces/2026-11-24_13-40-30.json",
        "result": (EXPERIMENT, 7),
        "recorded": "2026-11-24",
        "note": (
            "From the experiment where researchers had to fetch a page before "
            "citing it. The agent fetched an old GitHub copy of the TIOBE data "
            "(February 2025) and reported 23.88% instead of the current 20.86%. "
            "Fetching a page does not make it the right page, and this run is why "
            "that change was reverted."
        ),
    },
]


def load_json(relative_path: str):
    return json.loads((ROOT / relative_path).read_text(encoding="utf-8"))


def shape_result(tool: str, text: str) -> dict:
    """Make a tool result easy to show: search results become a list."""
    if tool == "web_search":
        try:
            items = json.loads(text)
            return {"type": "search", "items": [
                {"title": i.get("title", ""), "url": i.get("url", ""),
                 "snippet": i.get("snippet", "")[:240]}
                for i in items if isinstance(i, dict) and "url" in i
            ]}
        except (json.JSONDecodeError, TypeError):
            pass
    return {"type": "text", "text": text[:4500]}


def shape_steps(events: list[dict]) -> list[dict]:
    """Turn raw trace events into steps, attaching each result to its call."""
    names, steps, waiting = {}, [], {}

    def agent_of(source: str) -> str:
        if source == "main":
            return "orchestrator"
        names.setdefault(source, f"researcher-{len(names) + 1}")
        return names[source]

    for event in events:
        if event["type"] == "human":
            kinds = {d["type"] for d in event.get("decisions", [])}
            steps.append({"agent": "human", "kind": "approval", "decision": sorted(kinds)})
        elif event["type"] == "ai":
            who, tokens = agent_of(event["source"]), (event.get("usage") or {}).get("total_tokens", 0)
            if event["text"].strip() and not event["tool_calls"]:
                steps.append({"agent": who, "kind": "says", "text": event["text"], "tokens": tokens})
            for number, call in enumerate(event["tool_calls"]):
                step = {"agent": who, "kind": "tool", "name": call["name"], "args": call["args"],
                        "result": None, "tokens": tokens if number == 0 else 0}
                steps.append(step)
                waiting.setdefault(event["source"], []).append(step)
        elif event["type"] == "tool":
            queue = waiting.get(event["source"], [])
            match = next((s for s in queue if s["name"] == event.get("tool_name")), None)
            if match:
                match["result"] = shape_result(match["name"], event["text"])
                queue.remove(match)
    return merge_approval(steps)


def merge_approval(steps: list[dict]) -> list[dict]:
    """Tidy the approval step.

    After an approval the framework replays the proposed save_report call, so
    it appears twice. Keep the first, drop the unanswered replay, and attach
    the tool's outcome to the approval step, which is when it really happened.
    """
    tidy, last_call = [], None
    for step in steps:
        is_save = step["kind"] == "tool" and step["name"] == "save_report"
        if is_save and last_call and step["result"] is None and step["args"] == last_call["args"]:
            continue  # the replayed duplicate
        if step["kind"] == "approval" and last_call:
            step["outcome"] = last_call["result"]
            last_call["result"] = None
        if is_save:
            last_call = step
        tidy.append(step)
    return tidy


def citation_check(answer: str, events: list[dict]) -> list[dict]:
    """Each distinct cited URL, and whether the agent fetched it during the run."""
    fetched, seen, rows = run_evals.fetched_urls(events), set(), []
    for raw in run_evals.URL_PATTERN.findall(answer):
        url = raw.rstrip(".,;:")
        key = run_evals.normalize_url(url)
        if key not in seen:
            seen.add(key)
            rows.append({"url": url, "fetched": key in fetched})
    return rows


def build_example(spec: dict) -> dict:
    trace = load_json(spec["trace"])
    events = trace["events"]
    answer = run_evals.agent.final_answer(events)
    cost = run_evals.score_cost(events)
    steps = shape_steps(events)
    example = {
        "id": spec["id"], "tag": spec["tag"], "title": spec["title"],
        "question": trace["question"], "note": spec["note"],
        "recorded": spec["recorded"], "model": MODEL,
        "stats": {**cost, "researchers": len({s["agent"] for s in steps if s["agent"].startswith("researcher")})},
        "answer": answer, "citations": citation_check(answer, events),
        "eval": None, "steps": steps,
    }
    if spec["result"]:
        file, number = spec["result"]
        scored = load_json(file)["results"][number - 1]
        facts = load_json("evals/questions.json")[number - 1]["key_facts"]
        example["eval"] = {"correctness": scored["correctness"], "key_facts": facts}
    return example


def build_summary() -> dict:
    """Baseline versus experiment numbers, read from the saved eval results."""
    def totals(path: str) -> dict:
        data = load_json(path)
        rows = data["results"]
        return {
            "correctness": round(data["summary"]["avg_correctness"], 2),
            "citation_accuracy": round(data["summary"]["avg_citation_accuracy"], 2),
            "unfetched_citations": sum(len(r["citations"]["unfetched_citations"]) for r in rows),
            "no_fetch_questions": data["summary"]["questions_with_no_fetch"],
            "tokens_per_question": round(data["summary"]["avg_total_tokens"], -2),
            "questions": data["summary"]["questions"],
        }
    baseline, experiment = totals(BASELINE), totals(EXPERIMENT)
    # 0.71 is the figure from EVALS.md after correcting one scoring false positive.
    experiment["correctness_corrected"] = 0.71
    return {"baseline": baseline, "experiment": experiment, "model": MODEL}


def main() -> None:
    OUT_DIR.mkdir(exist_ok=True)
    index = []
    for spec in EXAMPLES:
        example = build_example(spec)
        (OUT_DIR / f"{spec['id']}.json").write_text(json.dumps(example, ensure_ascii=False), encoding="utf-8")
        index.append({k: example[k] for k in ("id", "tag", "title", "question", "recorded", "stats")})
        size = (OUT_DIR / f"{spec['id']}.json").stat().st_size
        print(f"{spec['id']}: {len(example['steps'])} steps, {size // 1024} KB, "
              f"{sum(c['fetched'] for c in example['citations'])}/{len(example['citations'])} cited URLs fetched")
    (OUT_DIR / "index.json").write_text(json.dumps(index, ensure_ascii=False), encoding="utf-8")
    (OUT_DIR / "summary.json").write_text(json.dumps(build_summary()), encoding="utf-8")
    print("wrote index.json and summary.json")


if __name__ == "__main__":
    main()
