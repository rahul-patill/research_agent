"""Run the research agent on every question in a questions file and score it.

Usage: python evals/run_evals.py [path/to/questions.json]
       (default: evals/questions.json)

Human approval is switched off, so every run is automatic.

Scoring (simple on purpose: no LLM judge yet)
1. Correctness: the fraction of the question's `key_facts` that appear in the
   answer. Match is a case-insensitive substring check, so a fact such as
   "3.15" counts only if that exact text is in the answer.
2. Citation accuracy: of the URLs the answer cites, the fraction the agent
   actually fetched with fetch_url during the run (read from the trace).
   URLs are compared after ignoring case, "www.", a trailing slash and any
   #fragment. An answer that cites no URL scores 0.0, because nothing it
   says can be traced to a page it read.
3. Cost: the number of model calls and tool calls, plus total tokens, counted
   over the orchestrator and all sub-agents.

Each question's trace is saved to traces/ and the full results to
evals/results/<timestamp>.json.
"""
import json
import re
import sys
from datetime import datetime
from pathlib import Path

# Make `import agent` work when this file is run as `python evals/run_evals.py`.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import agent  # noqa: E402  (must come after the sys.path line)

DEFAULT_QUESTIONS = Path(__file__).parent / "questions.json"
RESULTS_DIR = Path(__file__).parent / "results"
URL_PATTERN = re.compile(r"https?://[^\s)\]>\"'`]+")


# --- Scoring ----------------------------------------------------------------
def score_correctness(answer: str, key_facts: list[str]) -> float:
    """Fraction of key facts found in the answer (case-insensitive)."""
    if not key_facts:
        return 0.0
    text = answer.lower()
    return sum(fact.lower() in text for fact in key_facts) / len(key_facts)


def normalize_url(url: str) -> str:
    """Make URLs comparable: lowercase, no #fragment, no www., no trailing slash."""
    url = url.strip().rstrip(".,;:").split("#")[0].lower()
    url = url.replace("://www.", "://")
    return url.rstrip("/")


def cited_urls(answer: str) -> set[str]:
    """All distinct URLs written in the answer."""
    return {normalize_url(u) for u in URL_PATTERN.findall(answer)}


def fetched_urls(events: list[dict]) -> set[str]:
    """URLs passed to fetch_url anywhere in the run, including by sub-agents."""
    return {
        normalize_url(call["args"]["url"])
        for e in events if e["type"] == "ai"
        for call in e["tool_calls"]
        if call["name"] == "fetch_url" and "url" in call["args"]
    }


def score_citations(answer: str, events: list[dict]) -> dict:
    """How many of the cited URLs were actually fetched."""
    cited, fetched = cited_urls(answer), fetched_urls(events)
    verified = cited & fetched
    return {
        "cited": len(cited),
        "cited_and_fetched": len(verified),
        "unfetched_citations": sorted(cited - fetched),
        "score": len(verified) / len(cited) if cited else 0.0,
    }


def score_cost(events: list[dict]) -> dict:
    """Model calls, tool calls and tokens for the whole run."""
    model_events = [e for e in events if e["type"] == "ai"]
    tokens = sum((e.get("usage") or {}).get("total_tokens", 0) for e in model_events)
    return {
        "model_calls": len(model_events),
        "tool_calls": sum(len(e["tool_calls"]) for e in model_events),
        "fetch_calls": sum(
            c["name"] == "fetch_url" for e in model_events for c in e["tool_calls"]
        ),
        "total_tokens": tokens,
    }


def score_run(entry: dict, events: list[dict], answer: str) -> dict:
    """All three scores for one question."""
    return {
        "correctness": score_correctness(answer, entry["key_facts"]),
        "citations": score_citations(answer, events),
        "cost": score_cost(events),
    }


# --- Running ----------------------------------------------------------------
def load_questions(path: Path) -> list[dict]:
    """Load the questions and stop early if an entry is incomplete."""
    entries = json.loads(path.read_text(encoding="utf-8"))
    for number, entry in enumerate(entries, start=1):
        missing = [f for f in ("question", "key_facts", "expected_source") if f not in entry]
        if missing:
            sys.exit(f"Question {number} is missing {missing}. Fix {path} first.")
    return entries


def evaluate_question(entry: dict) -> dict:
    """Run the agent on one question (no human approval) and score it."""
    result = {"question": entry["question"], "expected_source": entry["expected_source"]}
    try:
        events, answer = agent.run_question(entry["question"], auto_approve=True, verbose=False)
    except Exception as error:  # one failing question must not stop the whole run
        return {**result, "error": f"{type(error).__name__}: {error}"}
    trace_path = agent.save_trace(entry["question"], events)
    return {**result, "answer": answer, "trace": str(trace_path),
            **score_run(entry, events, answer)}


def print_line(number: int, total: int, result: dict) -> None:
    """One line per question."""
    if "error" in result:
        print(f"[{number}/{total}] ERROR {result['error'][:100]}")
        return
    cost, cites = result["cost"], result["citations"]
    print(
        f"[{number}/{total}] correct {result['correctness']:.2f} | "
        f"cited {cites['cited_and_fetched']}/{cites['cited']} fetched | "
        f"{cost['model_calls']} model calls, {cost['tool_calls']} tool calls, "
        f"{cost['total_tokens']} tokens | {result['question'][:60]}"
    )


def summarize(results: list[dict]) -> dict:
    """Averages over the questions that ran without an error."""
    ok = [r for r in results if "error" not in r]
    if not ok:
        return {"questions": len(results), "errors": len(results)}
    n = len(ok)
    return {
        "questions": len(results),
        "errors": len(results) - n,
        "avg_correctness": sum(r["correctness"] for r in ok) / n,
        "avg_citation_accuracy": sum(r["citations"]["score"] for r in ok) / n,
        "avg_model_calls": sum(r["cost"]["model_calls"] for r in ok) / n,
        "avg_tool_calls": sum(r["cost"]["tool_calls"] for r in ok) / n,
        "avg_total_tokens": sum(r["cost"]["total_tokens"] for r in ok) / n,
        "questions_with_no_fetch": sum(r["cost"]["fetch_calls"] == 0 for r in ok),
    }


def save_results(summary: dict, results: list[dict]) -> Path:
    """Write everything to evals/results/<timestamp>.json."""
    RESULTS_DIR.mkdir(exist_ok=True)
    path = RESULTS_DIR / f"{datetime.now():%Y-%m-%d_%H-%M-%S}.json"
    data = {"model": agent.raw_loop.MODEL, "summary": summary, "results": results}
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


def main() -> None:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_QUESTIONS
    if not path.exists():
        sys.exit(f"{path} not found. Write the questions first (Step 9).")
    entries = load_questions(path)
    results = []
    for number, entry in enumerate(entries, start=1):
        results.append(evaluate_question(entry))
        print_line(number, len(entries), results[-1])
    summary = summarize(results)
    print("\n=== Summary ===")
    for name, value in summary.items():
        print(f"{name}: {value:.2f}" if isinstance(value, float) else f"{name}: {value}")
    print(f"\nResults saved to {save_results(summary, results)}")


if __name__ == "__main__":
    main()
