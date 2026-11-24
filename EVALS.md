# Eval results

## Baseline (Step 11)

- **Date:** 2026-11-23
- **Model:** `gemini-3.5-flash-lite` (for the orchestrator and the sub-agents)
- **Code:** commit `e770edb`, unchanged since. No code was changed for this run.
- **Questions:** `evals/questions.json`, 12 questions, facts verified on 2026-11-23
- **Raw results:** `evals/results/2026-11-23_21-59-20.json`. One trace per question is in `traces/` (git-ignored).
- **Approval:** switched off (every answer auto-approved).
- **Errors:** 0 of 12 questions crashed.

### Summary

| Score | Result | What it means |
|-------|--------|---------------|
| Correctness | **0.92** (11 of 12 questions fully correct) | Share of `key_facts` found in the answer, averaged over questions. |
| Citation accuracy | **0.27** | Share of cited URLs the agent actually fetched, averaged over questions. |
| Cost | **12.25 model calls, 10.58 tool calls, 53,485 tokens** per question | Totals over the orchestrator and all sub-agents. All 12 questions used 641,823 tokens. |

Questions where the agent never called `fetch_url`: **3 of 12** (questions 3, 7 and 12).

### Per question

| # | Question (shortened) | Correct | Cited and fetched | Fetch calls | Model calls | Tokens |
|---|----------------------|---------|-------------------|-------------|-------------|--------|
| 1 | Latest stable Python | 1.00 | 1/2 | 1 | 10 | 34,300 |
| 2 | Deep Agents license | 1.00 | 1/3 | 1 | 11 | 40,153 |
| 3 | Latest langgraph on PyPI | 1.00 | 0/1 | 0 | 12 | 49,822 |
| 4 | TIOBE language of the year 2025 | 1.00 | 1/2 | 1 | 10 | 38,276 |
| 5 | Latest stable Rust | 1.00 | 1/2 | 1 | 11 | 41,143 |
| 6 | TIOBE headline, Nov 2026 | 1.00 | 1/2 | 1 | 8 | 31,644 |
| 7 | Python's TIOBE rating | 1.00 | 0/5 | 0 | 11 | 45,276 |
| 8 | Python 3.15 support and latest 3.14 | 1.00 | 1/8 | 1 | 14 | 59,657 |
| 9 | Latest Python and Rust | 1.00 | 0/5 | 1 | 18 | 103,358 |
| 10 | Latest Python and langgraph | 1.00 | 2/3 | 2 | 16 | 67,306 |
| 11 | Python version in Jan 2030 | **0.00** | 1/6 | 1 | 16 | 88,850 |
| 12 | Python 3.99 features | 1.00 | 0/5 | 0 | 10 | 42,038 |

## The three lowest-scoring questions

Ranked by correctness plus citation accuracy. Questions 12 and 3 tie with question 7 on citation (0), with the same cause as question 7. The causes below come from reading the saved answers and traces. They are my reading, so check them against the traces yourself.

### 1. Question 11: "What will the latest stable Python version be in January 2030?" (correct 0.00, cited 1/6)
The agent answered flatly that it **will be Python 3.18**, by extending the annual October release cycle (3.15 in Oct 2026, so 3.18 in Oct 2029). It never said the future can't be known, so the loose key fact `predict` was not found.
Likely cause: the question design, as much as the agent. A schedule-based answer is reasonable, and my "no clear answer" label was debatable. The agent did show no hedging, and it cited 5 pages it never fetched (PEPs 602, 719, 745 and 790 and the devguide).

### 2. Question 9: "What are the latest stable versions of Python and Rust?" (correct 1.00, cited 0/5, 103,358 tokens)
The answer was right (Python 3.15, Rust 1.100.0), but it is the most expensive run, with 7 searches and 18 model calls. The one page it fetched, `blog.rust-lang.org/releases/latest`, was not among the 5 URLs it cited. It cited a Wikipedia page, a HeroDevs blog, a Rust blog URL it had only seen in search results, and others.
Likely cause: the sub-agents read search snippets and write notes from them. Then the orchestrator cites every URL in the notes, whether or not a page was read.

### 3. Question 7: "What is Python's rating on the TIOBE index this month?" (correct 1.00, cited 0/5)
The answer was right (Python #1, 20.86%), and it cites the TIOBE page, but **no `fetch_url` call was made at all**. The number came from search snippets. It also cited 4 extra pages it never opened, including TechRepublic's *October* article.
Likely cause: the search snippets already contained the answer, so the model never saw a reason to fetch.

## The most common failure

**The agent answers from search snippets and cites pages it never read.** It is the same pattern in every weak result:
- 35 of the cited URLs were not fetched, and all 35 did appear in search results, so they are **not invented**, just unread.
- Only 1 fetch call was typical (10 fetch calls over 12 questions, an average of 0.83, and 3 questions had none), even for questions that need two sources.
- Correctness stays high anyway (0.92), because search snippets often contain the answer. So the correctness score cannot show whether pages were read. The citation score is the one that exposes it, and it is the one that is low.
- The prompt already tells the agent to fetch pages and to record only facts from fetched pages. The cheap model ignores that, and nothing enforces it.

## Caveats on these numbers

- **One run, 12 questions.** There is no repeat, so run-to-run noise is unknown. Small differences between this baseline and a later run may be noise.
- **Citation accuracy counts any cited URL that was not fetched**, even a correct one from a real search result. The orchestrator listing every URL from the notes lowers the score even when the answer is right. It measures "did the agent read what it cites", not "is the answer true".
- **A fetched page proves a download, not that the fact is on it**, and `fetch_url` keeps only the first 4,000 characters.
- **Correctness is a text match.** Questions 11 and 12 (no-clear-answer) are unreliable by design. Question 12 scored 1.00 because the answer said "does not exist", and it then went on to describe Python 3.9 features.
- Some facts (versions, TIOBE rating) will change, so re-verify before re-running.

## Change 1 (Step 12): only record URLs of fetched pages (reverted)

- **Date:** 2026-11-24. **Model:** `gemini-3.5-flash-lite`. **Questions:** the same 12, facts re-verified unchanged.
- **Raw results:** `evals/results/2026-11-24_13-43-53.json`
- **The one change** (researcher sub-agent prompt, `SUBAGENT_PROMPT` in `agent.py`). Step 3 of that prompt went from "Only record facts from pages you fetched." to:
  > Only record a URL and facts from pages you fetched with fetch_url. Never record a URL that you only saw in search results. You must fetch at least one page before writing notes.
- **Reason:** the baseline's most common failure was citing pages that were never fetched, and the notes were the source of those citations.
- **Nothing else changed.** The orchestrator prompt, the tools and the questions are the same.

### Before and after

| Measure | Baseline | With the change |
|---------|----------|-----------------|
| Correctness (as scored) | 0.92 | 0.79 |
| Correctness (Q11 corrected, see below) | 0.92 | **0.71** |
| Citation accuracy | 0.27 | **0.69** |
| Unfetched citations (total) | 35 | **13** |
| Questions with no fetch call | 3 | **1** |
| Model calls per question | 12.25 | 13.67 |
| Tool calls per question | 10.58 | 12.00 |
| Tokens per question | 53,485 | **74,954** |
| Tokens, whole run | 641,823 | 899,442 |

### Per question

| # | Correct (before to after) | Cited and fetched | Fetch calls | Tokens |
|---|---------------------------|-------------------|-------------|--------|
| 1 | 1.00 to 1.00 | 1/2 to 1/1 | 1 to 1 | 34,300 to 33,369 |
| 2 | 1.00 to 1.00 | 1/3 to 1/1 | 1 to 1 | 40,153 to 43,911 |
| 3 | 1.00 to 1.00 | 0/1 to 1/2 | 0 to 1 | 49,822 to 55,741 |
| 4 | 1.00 to 1.00 | 1/2 to 1/1 | 1 to 1 | 38,276 to 38,170 |
| 5 | 1.00 to 1.00 | 1/2 to 1/2 | 1 to 2 | 41,143 to 123,106 |
| 6 | 1.00 to 1.00 | 1/2 to 1/1 | 1 to 1 | 31,644 to 38,819 |
| 7 | 1.00 to **0.00** | 0/5 to 0/2 | 0 to 1 | 45,276 to 205,348 |
| 8 | 1.00 to **0.50** | 1/8 to 2/2 | 1 to 2 | 59,657 to 60,192 |
| 9 | 1.00 to **0.50** | 0/5 to 1/4 | 1 to 1 | 103,358 to 68,533 |
| 10 | 1.00 to **0.50** | 2/3 to 2/2 | 2 to 2 | 67,306 to 59,214 |
| 11 | 0.00 to 1.00 (false positive) | 1/6 to 0/6 | 1 to 0 | 88,850 to 126,622 |
| 12 | 1.00 to 1.00 | 0/5 to 1/1 | 0 to 1 | 42,038 to 46,417 |

### Verdict: it hurt the answers, so it was reverted

**The change did what it was meant to do.** Unfetched citations fell from 35 to 13, citation accuracy rose from 0.27 to 0.69, and the number of questions with no fetch call went from 3 to 1.

**But it made the answers worse and the run more expensive.** The stated rule for this step is to revert a change that hurts the scores. Reading the traces:
- **Question 7 (0.00):** the agent fetched a stale third-party CSV (a GitHub copy of the TIOBE index for February 2025) and answered "Python 23.88%", not the current 20.86%. It used 205,348 tokens.
- **Questions 8, 9, 10:** the agent now fetched pages, but the wrong or incomplete ones. Question 8 fetched the devguide and PEP 745, and neither contains "3.14.10", so it answered "3.14.0". Question 9 gave "Rust 1.99.1", which is out of date (it fetched only the Python page). Question 10 gave "Python 3.14.0", from a fetched release page for the old version.
- **Question 11 is a scoring false positive.** The key fact `predict` matched inside the word "predictable". The answer still says "Python 3.18" flatly, with no hedge, as at baseline. Counting it as 0.00, the corrected correctness is 0.71.
- **Cost rose 40%** per question, with two runs over 120,000 tokens (questions 5 and 7).

**Why I think this happened:** the rule makes the agent fetch something, but not the right page. "Fetched" and "correct" are different things. Fetched pages are cut at 4,000 characters, search ranking can put stale or third-party pages first, and the agent has no way to know which page is authoritative. At baseline the search snippets often held the right current number, so skipping the fetch didn't hurt correctness.

**Caveats**
- Each version was run once and LLM runs vary, so I can't say how much of the correctness drop is noise. Questions 7 and 9 fail for specific, visible reasons, which makes pure noise less likely, but a repeat run would be needed to be sure.

**Status:** the line was removed. `agent.py` is back to the committed baseline version, so the baseline numbers are the current ones.

### What I'd try next (not done)
1. **A tool-side fix instead of a prompt rule.** Let `fetch_url` return more of a page, or a later section, so a fact below the 4,000-character cut can be read.
2. **Prefer official sources.** A rule such as "prefer the project's own site (python.org, rust-lang.org, pypi.org)" might stop the stale-CSV failure.
3. **Fix the scoring.** Match key facts on word boundaries so `predict` doesn't match "predictable", and decide how to score the two no-clear-answer questions.
4. **Measure noise.** Rerun the baseline once or twice to see the spread before trusting differences of this size.
