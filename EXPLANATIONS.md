# Explanations: what each step did and why

One section per step, written in plain language. Read the matching step in `build_step.md` alongside it.

---

## Step 0: Set up the project

**What was done**
1. `git init` created a git repository. Git records snapshots (commits) of your work, so you can compare or undo changes.
2. `python -m venv .venv` created a virtual environment, a private copy of Python for this project. Packages installed here don't affect other projects or your system Python.
3. Installed three packages into `.venv`:
   - `deepagents`: the agent harness we'll use from Step 4 (planning, filesystem, sub-agents).
   - `langgraph`: the graph/workflow library underneath it. We use its interrupts in Step 8.
   - `python-dotenv`: loads variables from `.env` into the program.
4. Created `.gitignore` listing `.venv/`, `.env` and `__pycache__/`, so git never tracks them.
5. Created `.env` with a placeholder key. (It was `ANTHROPIC_API_KEY` at first; in Step 1 we switched to Gemini, so it is now `GOOGLE_API_KEY`.)

**Why it matters**
- The virtual environment avoids version conflicts between projects.
- Keeping the key in `.env`, which git ignores, means you can't accidentally publish it.

**Versions installed:** deepagents 0.7.41, langgraph 1.2.24, python-dotenv 1.2.4, Python 3.13.1.

**What you need to do**
- Replace `paste-your-key-here` in `.env` with your Gemini API key (from Google AI Studio).
- Set a spending limit in your provider's dashboard.
- To activate the environment in your own terminal: `.\.venv\Scripts\Activate.ps1`.

**Not done yet:** the first commit. Run `git status` to confirm `.env` and `.venv/` aren't listed. Tell me when you want me to commit.

---

## Step 1: Write the spec and the project rules

**What was done**
- Switched the model provider to Gemini. `.env` now holds `GOOGLE_API_KEY`.
- Created `SPEC.md`, which defines what we're building:
  - **Goal:** question in, short answer with source URLs out.
  - **Version 1 scope:** one agent, two tools (`web_search`, `fetch_url`), one answer with sources.
  - **Out of scope:** sub-agents, shared filesystem, human approval, evals, tracing to files. Each arrives in its own later step.
  - **Dependencies:** the packages we expect to use. Anything else needs your approval.
- Created `CLAUDE.md`, which holds the rules I follow in every step: small steps, no secrets in output or commits, explain each file, ask before adding dependencies, keep functions short, update the README and this file after each step, and don't commit unless you ask.

**Why it matters**
- `SPEC.md` is the scope fence. When a new idea comes up, we check it against the spec and decide on purpose whether to change it, instead of drifting.
- `CLAUDE.md` is read at the start of every session, so you don't have to repeat the rules.
- Both files become the basis of the final README.

**Things worth knowing**
- I did not pick the exact Gemini model name. Model names change, so I'll check the current docs and ask you before using one (Step 3 or 4).
- The search API (Tavily, Brave, etc.) is still undecided. We'll choose it together in Step 3.
- Gemini needs its own SDK (`google-genai`) for the hand-written loop in Step 2. It's listed in `SPEC.md`, but not installed yet.

**Check for you:** read `SPEC.md` and `CLAUDE.md` and confirm the out-of-scope list and the rules match how you want to work. Change anything you disagree with.

---

## Step 2: Build a tool-calling loop by hand

**What was done**
- Installed `google-genai`, Google's SDK for Gemini (version 3.6.1).
- Created `raw_loop.py`. It has no agent framework, just the SDK.

**How the loop works (read `raw_loop.py` alongside this)**
1. **The tool** is `add_numbers`, an ordinary Python function.
2. **The tool description** (`add_numbers_declaration`) is the only thing the model sees about it: a name, a description and the parameters. The model can't see the Python code.
3. **`history`** is a list of messages. It starts with your question.
4. Each pass through the `for` loop sends the whole history to the model. The model remembers nothing between calls, so we resend everything every time.
5. If the reply contains a `function_call`, the model is asking us to run a tool. **The tool really runs in `run_tool_call`, on the line `TOOLS[call.name](**call.args)`.** The model never runs it.
6. We wrap the result as a `function_response` and append it to the history, then loop again so the model can use it.
7. If the reply has no tool call, it is the final answer and we stop.
8. `MAX_STEPS = 5` stops the loop if the model never finishes, so a bug can't cost you unlimited money.

I turned off the SDK's automatic function calling (`automatic_function_calling` disabled). Otherwise the SDK would run this loop for you and hide the very thing we want to see.

**Why it matters:** every agent framework, including Deep Agents in Step 4, is this loop plus extras (planning, files, memory). Seeing it in plain code means the framework won't feel like magic.

**Model choice:** the model name is read from `GEMINI_MODEL` in `.env`. If it isn't set, it defaults to `gemini-3.5-flash-lite`. My web search suggested that is the cheapest current Gemini model, but the results conflicted, so check Google's pricing page and change it if needed.

**Not tested yet:** `.env` still holds the placeholder key, so I could only check that the script's syntax is valid and `add_numbers` returns the right value (6912). I haven't run the model.

**What you need to do**
1. Put your real key in `.env`.
2. Run `.\.venv\Scripts\python.exe raw_loop.py`. You should see the model call `add_numbers`, probably twice (1234 + 5678, then + 10), then a final answer of 6922.
3. Check you can point to where the tool runs and explain why the history is resent.

---

## Step 3: Add real tools for web search and fetching pages

**What was done**
- You chose Tavily (search) and httpx + trafilatura (reading pages). I installed `tavily-python`, `httpx` and `trafilatura` and added them to `SPEC.md`.
- In `raw_loop.py` I replaced `add_numbers` with two tools. The loop itself did not change.
  - `web_search(query)` asks Tavily for 5 results and returns each one's title, URL and snippet.
  - `fetch_url(url)` downloads a page with `httpx`, uses `trafilatura` to strip menus, ads and scripts, and returns the text cut to 4,000 characters.
- Both tools catch errors and return them as text (for example "Fetch failed: 404"). The model can then read the error and try something else, instead of the whole script crashing.
- The test question is now "What is the latest stable version of Python? Cite the URLs you used."

**Why the tool descriptions matter:** the model never sees your Python code. It decides which tool to call from the name, the description and the parameters alone. The descriptions say what each tool does and when to use it: search first, then fetch a promising result. The `fetch_url` description also says to only use URLs from search results, so the model doesn't invent links.

**Why the fetched page is truncated:** a model can only read a limited amount of text per request, and the whole history is resent on every step, so a long page would be paid for again each time. 4,000 characters keeps the context small and the cost low. The cost is that the answer might sit past the cut-off, which is a limitation we can measure later with evals.

**What I tested:** `fetch_url` on python.org returned exactly 4,000 characters of real text, and a 404 page returned a clear error message. `web_search` is not tested yet: Tavily rejected the request because there is no key.

**What you need to do**
1. Sign up at tavily.com (free) and put the key in `.env` as `TAVILY_API_KEY`.
2. Run `.\.venv\Scripts\python.exe raw_loop.py`. You should see `web_search`, then `fetch_url` on one of the results, then an answer that cites a URL.
3. Check you can say why the fetched text is truncated.

---

## Step 4: Move the loop into the Deep Agents harness

**What was done**
- Created `agent.py`. It uses `create_deep_agent` from the `deepagents` package.
- **Docs page used:** https://docs.langchain.com/oss/python/deepagents/quickstart
- No new package was needed. `langchain-google-genai`, which lets Deep Agents talk to Gemini, was installed together with `deepagents`.

**How `agent.py` works**
1. `web_search` and `fetch_url` are plain Python functions. They call the Step 3 versions in `raw_loop.py`, so the tool code isn't duplicated. The harness reads each function's name, parameters and **docstring** and builds the tool description for the model. That is the same job `FunctionDeclaration` did by hand in Step 2.
2. `create_deep_agent(model=..., tools=[...], system_prompt=...)` builds the agent. The model is a `"google_genai:<model name>"` string, using the same `GEMINI_MODEL` setting as before.
3. `agent.invoke({"messages": [...]})` runs the whole thing. It returns the full list of messages, and the last one is the final answer.
4. The system prompt tells the agent to search, then read pages with `fetch_url`, then answer with a Sources list.

**What the harness does that `raw_loop.py` didn't**
- It runs the tool loop for you: call the model, run the tools it asks for, append the results, repeat. In Step 2 that was your own `for` loop and `history` list.
- It adds built-in planning (a to-do list tool), a virtual filesystem and sub-agent support. We aren't using those yet. Steps 6 and 7 turn them on.

**A small gotcha:** Gemini returns its answer as a list of content blocks, not a plain string, so printing `.content` shows raw data. `.text` joins the text parts into a string, which is what the script prints.

**Result:** for "What is the latest stable version of Python?" the agent answered Python 3.15.2 and cited python.org pages. The system prompt makes it read pages first, so this was a better result than the hand-written loop's.

**Caveat:** the docs' example model name (`gemini-4-hydrogen`) couldn't be verified, so we still use the model from `GEMINI_MODEL`, which works.

**Check for you:** run `python agent.py "your question"` and compare it with `raw_loop.py`. You should be able to say in a sentence or two what the harness handles for you.

---

## Step 5: Look at the trace

**What was done**
- `agent.py` now uses `agent.stream(..., stream_mode="updates")` instead of `agent.invoke(...)`. LangGraph's streaming gives one chunk per graph step containing only the new messages, so I didn't write custom logging.
- Each message becomes a small event: model calls (with any tool calls and token usage), tool results, and the final answer. Events are printed live and saved in full to `traces/<timestamp>.json`.
- `traces/` was added to `.gitignore`.

**How to read a trace**
- `[model] calls web_search({...})`: the model asked for a tool. This is the same "function call" you saw in `raw_loop.py`.
- `[tool result: web_search] ...`: what the tool returned. The printout is cut to 300 characters, and the JSON file keeps the full text.
- `[model] says: ...`: a model reply with no tool call. That is the final answer.
- The `usage` field in the JSON shows input and output tokens for each model call. That is the raw data for the cost score in Step 10.

**What the first trace showed (your Step 5 check)**
The agent answered "Python 3.15.2" and cited two python.org URLs, but:
- It made **two `web_search` calls and zero `fetch_url` calls**.
- Both cited URLs appeared in the search results, so they were not made up. But the agent never read them, so the "3.15.2" answer came from search snippets.
- That fails the check "cited URLs match URLs the agent actually fetched", despite the prompt saying to fetch pages. (The cheap model sometimes skips the instruction.) My earlier note that the answer was better because of the prompt was wrong: the trace shows the prompt did not make it fetch.

This is exactly why traces matter: the answer looked fine, and only the trace showed it hadn't read its sources. The Step 10 citation score will measure this, and Step 12 is where we'd fix it with one measured change.

**Check for you:** open the newest file in `traces/` and pick one tool call. Say what it asked for, what came back, and what the model did next.

---

## Step 6: Add a shared filesystem

**What was done**
- The agent gets file tools (`write_file`, `read_file`, `ls`, `edit_file`, `glob`, `grep`), and notes are saved in `workspace/` on your disk.
- At the start of every run, `reset_workspace()` deletes and recreates `workspace/`, so old notes never leak into a new run.
- The system prompt now says: save each source's URL and key facts to `/workspace/`, read them back, and write the answer from those notes.
- `workspace/` is in `.gitignore`.
- **Docs page used:** https://docs.langchain.com/oss/python/deepagents/backends

**Which backend I chose, and why**
Deep Agents offers several "backends", which decide where the agent's files live:
- `StateBackend` (the default): files exist only in memory for the run. Nothing appears on disk.
- `FilesystemBackend`: real files on disk under a folder you choose.
- `CompositeBackend`: sends different path prefixes to different backends.

I used a `CompositeBackend`: `/workspace/` goes to a `FilesystemBackend`, and everything else goes to `StateBackend`. Reasons:
1. You can open `workspace/` and see the notes, which the step requires.
2. The docs warn that `FilesystemBackend` gives the agent real read/write access, including to secrets such as `.env`. I set its root to the `workspace/` folder with `virtual_mode=True`, so the agent cannot reach `.env` or any other project file.
3. The docs recommend this pattern, because the harness's own internal files would otherwise also land on disk.

**Why offloading helps long research**
Everything in the conversation is re-sent to the model on every step. If the agent keeps full page text in the conversation, the context grows and costs more each step, and the model can lose track. Writing short notes to a file means the agent can keep only what it needs and read the notes back when writing the answer. Step 7 also relies on this: sub-agents will pass their findings to the orchestrator through these files.

**What the test run showed (honest result)**
The filesystem part works. The trace shows `write_file` creating `workspace/source_1.md` and `read_file` reading it back, and the answer came from that note.

The research quality is a problem, though:
- The agent made three searches and **again no `fetch_url` call**, even though the prompt says to read pages.
- The note it wrote says "Python.org lists ... Python 3.15.2" for `python.org/downloads/`. That page was never fetched, so the note is not based on reading it.
- One search snippet it saw said "Python 3.14.10 - Oct. 25, 2026", which conflicts with its answer. I can't tell which version is correct from this run.

So the notes are only as good as the research behind them. The cheap model ignores the "fetch pages" instruction. This is the failure Steps 10-12 are built to measure and fix, and I haven't changed it here because it's outside this step. A good candidate for the Step 12 change: tighter tool descriptions or a prompt rule such as "never cite or write notes about a URL you did not fetch".

**Check for you:** run a question, open `workspace/` and read the notes. Then say why writing notes helps with long research.

---

## Step 7: Add sub-agents

**What was done**
- **Docs used:** https://docs.langchain.com/oss/python/deepagents/subagents (plus the `SubAgent` type in the installed package).
- `agent.py` now has two kinds of agent:
  - The **orchestrator** (the main agent). It has no web tools at all (`tools=[]`), so it has to delegate. Its prompt says to split the question into 2-3 subtopics, start one `researcher` per subtopic, read the notes files they wrote, and combine them into one answer with sources.
  - The **researcher** sub-agent, defined as a dictionary: `name`, `description`, `system_prompt` and `tools`. The orchestrator reads the `description` to decide when to use it. The researcher gets `web_search` and `fetch_url` and is told to research only its own subtopic and write notes to the file named in its task.

**How delegation works**
The orchestrator calls a built-in tool named `task` with `subagent_type="researcher"` and a description such as "Research X. Save notes to /workspace/x.md". That starts the sub-agent with a fresh, empty context: it sees only that description, not the orchestrator's conversation. When it finishes, the orchestrator receives only its last message, here just the file name. The orchestrator can issue several `task` calls in one turn, and they run in parallel.

**Why sub-agents keep the orchestrator's context smaller**
Each researcher does many searches and reads long pages, and all of that stays inside its own context. The orchestrator never sees any of it. It only sees one short line per sub-agent, then reads the notes it chooses to read. If one agent did everything, its context would hold every search result and page for every subtopic, and it would be resent on every step.
The tradeoff is cost: each sub-agent makes its own model calls, so total tokens go up. Step 9-12 evals are how we find out whether it's worth it.

**How I limited it to three**
The docs show no setting to cap the number of sub-agents, so the cap is an instruction in the orchestrator's prompt (`MAX_SUBAGENTS = 3`). That is a request to the model, not a hard guarantee. Deep Agents also adds a built-in `general-purpose` sub-agent. The prompt tells the orchestrator to use only `researcher`.

**Trace changes**
Sub-agent steps happen inside the `task` tool, so a normal trace would only show the `task` call and its result. I turned on `subgraphs=True` in the stream, and each trace event now has a `source` field (`main` or the sub-agent's path). Sub-agent lines are indented in the printout. The final answer is taken only from the orchestrator's own replies.

**Test run** ("Compare the main approaches to evaluating LLM agents.")
- The orchestrator started 2 `researcher` sub-agents at the same time, one on benchmark-based and automated evaluation, one on human and simulation-based evaluation.
- `workspace/` ended up with one file per subtopic (`benchmarks_automated.md`, `human_simulation.md`). The orchestrator listed and read both, and the final answer combines them, with a Sources list.
- Totals for the run: 15 model calls, about 88,000 tokens.

**Honest problems**
- The sub-agents made 7 `web_search` calls and **no `fetch_url` calls**. Their notes (about 6,000 characters each) were written from search snippets and the model's own background knowledge, not from pages they read. That is the same issue as in Steps 5 and 6.
- Some entries in the Sources list (for example the AgentBench and WebArena papers) did show up in search results. But since nothing was fetched, I can't say the answer's details came from them. Treat the answer as plausible, not verified.
- The cap of 3 is only a prompt rule.
- I've still left the "fetch before citing" problem alone, because it belongs in the measured fix in Step 12.

**Check for you:** open `workspace/` and the newest trace. Find the two `task` calls, then follow one sub-agent's `source` events down to its `write_file`. Then say in your own words why the orchestrator's context stays smaller.

---

## Step 8: Add human approval before saving

**What was done**
- **Docs used:** https://docs.langchain.com/oss/python/deepagents/human-in-the-loop. This is the Deep Agents wrapper around LangGraph's interrupt feature, so I used it instead of writing raw interrupts.
- Added a `save_report(content)` tool that writes `report.md`. The orchestrator's prompt now ends with: write the answer, call `save_report` once with it, and if rejected, don't retry.
- Passed two new settings to `create_deep_agent`:
  - `interrupt_on={"save_report": {"allowed_decisions": ["approve", "edit", "reject"]}}`: pause before this tool runs.
  - `checkpointer=MemorySaver()`: keep the run's state at the pause.
- The research steps are untouched.

**How the pause and resume work**
1. The agent decides to call `save_report`. Before it runs, the harness stops the graph and the stream reports an `__interrupt__` containing the pending call, including the draft in its arguments.
2. `ask_human` prints the draft and reads your choice.
3. Your choice is sent back as `Command(resume={"decisions": [...]})`, using the **same `thread_id`**. The graph continues from where it stopped:
   - `approve`: the tool runs with the original text, so `report.md` is written.
   - `edit`: the tool runs with your replacement text, so `report.md` holds what you typed.
   - `reject`: the tool does not run. The agent receives a message saying it was rejected and tells you nothing was saved.

**What the checkpoint stores**
A checkpoint is a snapshot of the graph's state at a step: the full message history, which node was running, the files in the in-memory state, and the pending (interrupted) tool call. The `thread_id` is the key it is saved under. On resume, LangGraph loads the snapshot for that `thread_id` and continues. Nothing is redone, so no searches or model calls are repeated.
`MemorySaver` keeps snapshots in memory only, so the pause survives only while the program is running. If you close the terminal at the prompt, the run is lost. A database-backed checkpointer would let you resume later; we don't need that here.

**What I tested**
- **Approve:** `report.md` was written with the draft's text.
- **Reject:** the agent said "The report was not saved." and no `report.md` existed.
- **Edit:** `report.md` contained exactly the text I typed, not the model's draft.

**Caveats**
- The model sometimes calls `save_report` twice in one run, so you may get a second draft to review. This happened once in testing. That's the model's choice, and each call is a new review.
- The draft you approve is only as reliable as the research behind it. As in Steps 5-7, the agent still tends to skip `fetch_url`, so approval is a good place to check the Sources list yourself.
- `report.md` is in `.gitignore`, because it is generated output.
- There is no switch yet to turn approval off. Step 10's eval runner needs one, and we'll add it then.

**Check for you:** run `python agent.py "your question"`. Try approve, then run again and reject, and confirm nothing was saved. Then explain what the checkpoint stores.

---

## Step 9: Write the test questions (your part)

**What happens in this step**
This is the one step where you do the work and I only check it. Nothing was built. I confirmed that `evals/questions.json` doesn't exist yet and wrote no questions, on purpose.

**Why you write them**
An evaluation compares the agent's answers with what you know is right. If I wrote the questions, I'd also be deciding what "correct" means, and you couldn't tell a real failure from a bad question. The fixed set also lets you compare runs fairly in Steps 11 and 12.

**The file format**
Create `evals/questions.json`: a list of entries, each with three fields.
```json
[
  {
    "question": "Who won the 2022 FIFA World Cup?",
    "key_facts": ["Argentina", "beat France", "penalty shootout"],
    "expected_source": "https://en.wikipedia.org/wiki/2022_FIFA_World_Cup"
  }
]
```
(That is only a format example. Don't copy it.) `key_facts` are short strings that must appear in a correct answer. Step 10's first scoring method is a simple text match, so write each fact as a short phrase that a correct answer would contain word for word, such as "3.15" or "Argentina".

**What to include (10 to 15 total)**
- A few **easy** single-fact questions you can verify in one page.
- A few that need **two sources** to answer.
- At least one with **no clear answer**, where the right behavior is to say so. For that one, use `key_facts` such as "no clear answer" or "not enough information", and think about how you'll score it.
- Prefer questions where the answer **changes over time** or that you already know well, so you can judge the result.
- Avoid facts the model can answer from memory without searching. Those won't test the tools.
- Keep in mind what we've seen: the agent often skips `fetch_url`. Questions whose answer is only on a specific page will show that clearly.

**What I'll check once you've written it**
Every entry has all three fields, and every `expected_source` URL is reachable. I'll report anything missing or broken and won't change your questions.

**Done when:** the file has 10-15 entries with all three fields, every URL works, and you can say what a good answer to each question looks like.

---

## Step 10: Build the eval runner

**Where we are in the guide:** Step 9 (your questions file) is still not done, but this runner only needs the file when it runs, so I built it first and tested it on a two-question throwaway file kept outside `evals/`. Step 11 (the baseline) needs your real questions, so it is blocked until you write them.

**What was done**
- Created `evals/run_evals.py` (about 200 lines, in small functions).
- Made a small change to `agent.py`: `run_with_trace` now accepts `auto_approve=True` (approve every draft without asking) and `verbose=False` (don't print). I also split `main` into `final_answer` and `run_question` so the runner can reuse them. Running `python agent.py "..."` behaves as before.

**How a question is scored**
1. **Correctness.** For each entry in `key_facts`, check whether that text appears in the answer, ignoring case. The score is the share found, so 2 of 3 facts is 0.67. It is simple on purpose: easy to explain and to debug, but strict. "3.15" matches, while "three point fifteen" would not.
2. **Citation accuracy.** Find every URL written in the answer. Then check each one against the URLs the agent actually passed to `fetch_url`, read from the trace (including calls made inside sub-agents). The score is the share of cited URLs that were fetched. URLs are compared ignoring case, `www.`, a trailing slash and `#fragments`. If the answer cites no URL, the score is 0, since nothing can be traced to a page that was read.
   Caveat: "fetched" shows the page was downloaded, not that the claim is on it. And `fetch_url` cuts pages to 4,000 characters.
3. **Cost.** Count model calls, tool calls and total tokens from the trace. Tokens come from the model's own usage report, and they include the sub-agents.

**Other things the runner does**
- Resets `workspace/` for every question, saves each question's trace in `traces/`, and wraps each question in a try/except, so one crash records an `error` and the run continues.
- Prints one line per question and a summary (average correctness, citation accuracy, calls, tokens, and how many questions made no fetch at all).
- Stops early with a clear message if an entry is missing a field or the questions file doesn't exist.
- Saves everything to `evals/results/<timestamp>.json`.
- Eval runs overwrite `report.md`, since approval is off and every answer is saved.

**What I tested**
- The scoring functions, with hand-made inputs: partial fact matches, URL normalization, a cited-but-not-fetched URL, and no URLs. All passed.
- An end-to-end run on two throwaway questions (Australia's capital, the Python version): both found their key fact, one answer's cited URLs were only partly fetched (1 of 2), and runs used about 37,000 to 51,000 tokens each. I deleted those results because the questions were not yours and they must not be mistaken for a baseline.
- Two questions are too few to say anything about the agent in general. In this smoke test the agents did fetch pages, unlike the earlier runs. Whether that's reliable is what your question set will show.

**Cost warning:** one question costs roughly 40,000 to 90,000 tokens, because of the sub-agents. A full run of 10 to 15 questions is a real spend, so check your Gemini limit first.

**Check for you:** you should be able to explain each of the three scores in one sentence.

---

## Step 9 (completed): The test questions

**What changed from the plan**
The guide says you should write the questions yourself. You asked to draft them together, so I proposed candidates and you approved the list. The important part still holds: the facts were checked against real pages before the file was written, and you decide what counts as correct.

**How the facts were verified (2026-11-23)**
I downloaded each source page in full (without the agent's 4,000-character cut) and read the value off it:
- Python 3.15.2 is the newest release on python.org (Oct 25, 2026), and the same page lists 3.14.10 and "3.15 ... 2031-10".
- `langgraph` 1.2.24 on PyPI, Rust 1.100.0 as GitHub's latest release, MIT license in the Deep Agents LICENSE file, and the TIOBE November 2026 page (Python #1 at 20.86%, "Dart" in the headline, C# as 2025's language of the year).

**The 12 questions**
- 1-7: easy, single fact on one page.
- 8: needs a detail far down the page, so it is a real test of the 4,000-character truncation.
- 9-10: two sources each. `expected_source` is a list of two URLs.
- 11-12: no clear answer. The right behavior is to say so: the future Python version can't be known, and Python 3.99 doesn't exist.

**Step 9 check result:** 12 entries, all three fields present in every one, and every distinct source URL returned HTTP 200. I did not change any question.

**Known weak spots in the set**
- **Staleness.** A new Python, Rust or langgraph release, or TIOBE's next monthly update, makes questions 1, 3, 5, 7, 9 and 10 wrong. Re-verify them right before the baseline run.
- **Questions 11 and 12 score unreliably.** The text match looks for `predict` or `does not exist`, but a correct "I can't tell" could be worded differently, such as "no such version" or "impossible to know". A low score there may not mean a bad answer, so read those two by hand.
- **Question 4 and 6 and 7 all use the same TIOBE page**, so a TIOBE fetch problem would hit three questions at once.
- There are no hard multi-hop questions. This set mostly tests whether the agent looks things up and cites pages it read.

**Check for you:** pick any question and say what a good answer looks like, and what would make the score wrong even though the answer is right.

---

## Step 11: Record the baseline

**What was done**
- Ran `python evals/run_evals.py` once on all 12 questions, with no code changes. It took a few minutes, used 641,823 tokens and finished with no errors.
- Wrote `EVALS.md`: the date, model, the three scores, a per-question table, the three worst questions, and the most common failure. No code was changed.

**What the numbers say**
- **Correctness 0.92.** 11 of 12 answers contained every key fact. The one miss was question 11, and that one is partly a question-design problem (see below).
- **Citation accuracy 0.27.** On average, only about a quarter of the URLs in an answer were pages the agent had actually fetched.
- **Cost:** about 12 model calls and 53,500 tokens per question, with the two-source question (9) the highest at 103,358 tokens.

**Why the two scores disagree**
The agent is right most of the time because search snippets often contain the answer. It then lists every URL from its notes as a source, even for pages it never opened. So correctness is high and citation accuracy is low. This is the pattern we saw by eye in Steps 5, 6 and 7, and now it has a number on it.

**Two checks I made before writing the analysis**
1. **Are the unfetched citations made up?** No. All 35 appeared in some search result. They are unread, not invented.
2. **Is the low score caused by my URL matching?** No. In question 1 the agent fetched `python.org` (the home page) but cited `python.org/downloads`. The pages really are different.

**The most common failure, in one sentence:** the agent answers from search snippets and cites pages it never read.

**Honest limits of this baseline**
- It is one run. LLM runs vary, so a later difference of a few points may be noise, which is worth remembering in Step 12.
- Question 11 scored 0 because the agent confidently predicted "Python 3.18" from the annual release cycle. That is a reasonable answer, so the question is a weak "no clear answer" test.
- The 0.27 punishes the orchestrator for listing every URL in its notes, even when the answer is true.

**Check for you:** open two or three files in `traces/` (the paths are in the results file) and see whether you agree with the failure analysis. Then say what the most common failure is, in one sentence.

---

## Step 12: Make one change and measure it

**What was done**
1. Picked the change from the baseline's most common failure: citing pages that were never fetched. The citations came from the sub-agents' notes, so I changed one line of `SUBAGENT_PROMPT`: record only URLs of pages fetched with `fetch_url`, never URLs seen only in search results, and fetch at least one page first.
2. Re-checked the time-sensitive facts (Python, Rust, langgraph, TIOBE). Nothing had changed, so the questions were still valid.
3. Reran all 12 questions and compared with the baseline in `EVALS.md`.
4. Read the traces of the questions that got worse.
5. Reverted the change with `git checkout -- agent.py`, because it hurt the scores.

**The result**
- It worked on its target: citation accuracy 0.27 to 0.69, and unfetched citations 35 to 13.
- It hurt correctness: 0.92 to 0.79 as scored, 0.71 once one false positive is corrected.
- It cost about 40% more tokens per question.

**Why a "fix" can make things worse**
The rule forced the agent to fetch pages, but nothing made it fetch the right ones. In question 7 it fetched an old copy of the TIOBE data and trusted it. In questions 8, 9 and 10 the fetched pages didn't hold the current fact, or the fact sat past the 4,000-character cut. At baseline the answers were often right because the search snippets held the current number. Forcing a fetch took that away without adding a better source. Without the second metric, the citation gain alone would have looked like a clear win.

**Two other lessons**
- **A scorer can be fooled.** Question 11 jumped from 0.00 to 1.00 only because `predict` is a substring of "predictable". Reading the answer showed it hadn't improved at all. Read the changed cases before trusting a number.
- **One run is weak evidence.** I ran each version once. The failures in questions 7 and 9 had visible causes, so I trust the verdict, but a repeat run of each would show how much is noise.

**Why I reverted**
The step says to revert a change that hurts the scores, and wrong answers are worse than unread citations. `EVALS.md` records the exact line that was tried, so it can be reapplied. Combined with a better `fetch_url` and a preference for official sources, it might turn into a gain.

**Check for you:** compare the before and after numbers yourself and say whether you agree with the verdict. Then explain in your own words why forcing the agent to fetch pages did not make its answers better.

---

## Step 13: The README and the demo

**What was done**
The README had been built up step by step, so this step was a review, not a rewrite. I read it against the code and against `EVALS.md` and fixed what had gone stale:
- **Outdated statements.** Known limitations still said the evals "will measure" things and that Step 12 "is where a fix is tried". Step 10 still said "not yet run". All corrected.
- **Duplicated and scattered text.** The limitations were one long list with overlapping points. They are now grouped under "Agent behavior" and "Evals".
- **The results.** The baseline and the Step 12 change were in separate paragraphs. They are now one table, with the main finding and the reason the change was reverted written underneath.
- **Added:** a summary at the top that says what the project shows, including the result that the first fix made things worse; the exact package versions it was tested with; and a "What I would build next" section.
- The file is about 270 lines, under the 300-line limit in the guide.

**The rule I kept to:** no invented numbers. Every score in the README comes from `EVALS.md` or the saved result files. Where something wasn't measured (run-to-run noise), the README says so.

**Why the README leads with a negative result**
A reader, such as a hiring manager, learns more from "I measured a real problem, tried a fix, saw it hurt, and reverted it" than from a project that claims everything works. It is also the honest summary of what the evals showed.

**What is yours to do (the demo)**
Record a 2 to 3 minute screen recording that shows: one question running (the live step-by-step output), the trace file in `traces/`, the approve / edit / reject prompt and the saved `report.md`, and the eval summary. I can't make that, because it needs your screen. When you have it, I'll add a link under a "Demo" heading in the README.

**Check for you:** read the README as if you had never seen the project. Rewrite anything you can't explain, and be ready to answer "what would you change next?" in a minute (the "What I would build next" list is a starting point).
