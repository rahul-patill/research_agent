# Research Agent: Step-by-Step Build Guide

This guide breaks the project into small steps. Give Claude Code **one step at a time**. Before moving on, make sure you can explain what the step did and why.

## How to use this guide

For every step:

1. Read the **Goal** and **Why** sections so you know what you're building and why.
2. Paste the **Prompt for Claude Code** into Claude Code. Edit it if your setup differs.
3. Read every file it creates or changes. Ask Claude Code to explain anything you don't understand.
4. Run the **Check** commands or do the check described.
5. When the **Done when** list is all true, commit with the suggested message and move on.

If a step fails, don't skip ahead. Fix it or ask Claude Code to fix it, then rerun the check. Each step builds on the one before it.

Library names and APIs change. Before Steps 4 and 8, check the current Deep Agents and LangGraph docs. The prompts below describe what to build, so they still work if the code details change.

---

## Step 0: Set up the project

**Goal:** A clean project folder with Python, git, and API keys ready.

**Why:** Keeping the environment separate from the code avoids version conflicts. Git records each step so you can compare or undo changes. Keeping keys in a `.env` file (and out of git) prevents accidentally publishing them.

**Do this yourself (not in Claude Code):**

```bash
mkdir research-agent && cd research-agent
git init
python -m venv .venv
source .venv/bin/activate          # On Windows: .venv\Scripts\activate
pip install deepagents langgraph python-dotenv
```

Create a `.gitignore` file containing:

```
.venv/
.env
__pycache__/
```

Create a `.env` file with your API key (the variable name depends on your model provider, such as `ANTHROPIC_API_KEY`). Don't commit it.

Set a spending limit in your model provider's dashboard before you start.

**Check:** `git status` should not show `.env` or `.venv/`.

**Done when:**
- The virtual environment activates and the packages install without errors.
- `.env` exists and is listed in `.gitignore`.
- You've set a spending limit with your provider.

**Commit:** `git add .gitignore && git commit -m "Set up project environment"`

---

## Step 1: Write the spec and the project rules

**Goal:** Two files that tell Claude Code what to build and how to work: `SPEC.md` and `CLAUDE.md`.

**Why:** Claude Code produces better work when it has clear requirements. `SPEC.md` defines the scope, so it doesn't add features you didn't plan. `CLAUDE.md` holds the rules that apply to every step, so you don't repeat them in each prompt. These files also become the basis of your README later.

**Prompt for Claude Code:**

> Create two files in this folder.
>
> 1. `SPEC.md`: The project is a research agent. Given a question, it plans, searches the web, reads sources, and returns a short answer with citations (source URLs). The scope for the first version is: one agent, two tools (web search and fetch URL), a single answer with sources. Later additions, which are not part of this version: sub-agents, a shared filesystem, human approval before saving, and an evaluation suite. Include a section listing these as out of scope.
> 2. `CLAUDE.md`: Project rules. Work in small steps and change only what the current step asks for. Never commit or print secrets from `.env`. Explain each file you create in two or three sentences. Ask before adding any dependency not listed in SPEC.md. Keep functions short and name them clearly.
>
> Don't write any code yet.

**Check:** Read both files. Make sure the out-of-scope list is complete and the rules match how you want to work.

**Done when:**
- `SPEC.md` lists the goal, the tools, the output format, and the out-of-scope items.
- `CLAUDE.md` contains the working rules.
- You understand every line of both files.

**Commit:** `git add SPEC.md CLAUDE.md && git commit -m "Add spec and project rules"`

---

## Step 2: Build a tool-calling loop by hand

**Goal:** A small Python script, with no frameworks, where a model can call a function and use the result.

**Why:** This is the core idea behind every agent. Once you've seen the loop in plain code, the Deep Agents and LangGraph layers will make sense instead of feeling like magic. You'll know what the framework is doing for you.

The loop looks like this:

1. Send the question and a list of available tools to the model.
2. If the model asks to call a tool, run that function with the arguments it gave.
3. Add the result to the message history.
4. Send the history back to the model.
5. Repeat until the model gives a final answer, or until you hit a step limit.

**Prompt for Claude Code:**

> Create `raw_loop.py`. It should use the model provider's SDK directly, without any agent framework. Define one simple tool, `add_numbers(a, b)`, and describe it to the model in the tool-calling format the SDK expects. Run a loop that sends a question, executes any tool calls the model requests, feeds the results back, and stops when the model gives a final text answer or after 5 steps. Print each step as it happens. Add comments explaining each part of the loop. Use the question "What is 1234 plus 5678, then add 10?" to test it.

**Check:**

```bash
python raw_loop.py
```

You should see the model call `add_numbers` at least twice (or once and then answer), then print a final answer with the correct total.

**Done when:**
- The script prints each tool call and each result.
- You can point to the line where the tool actually runs. (The model never runs it; your code does.)
- You can explain why the message history gets sent back on every step.

**Commit:** `git add raw_loop.py && git commit -m "Add hand-written tool-calling loop"`

---

## Step 3: Add real tools for web search and fetching pages

**Goal:** Replace the demo tool with two real ones: `web_search(query)` and `fetch_url(url)`.

**Why:** These two tools are what let the agent find and read sources. Keeping them small and well described matters, because the model decides when to use them based on their names and descriptions. A vague description leads to poor tool use.

**Prompt for Claude Code:**

> In `raw_loop.py`, replace `add_numbers` with two tools:
> - `web_search(query: str)`: Returns a list of results, each with a title, URL, and snippet. Use a search API that works with a free or low-cost key (ask me which one to use if you need one; don't guess).
> - `fetch_url(url: str)`: Downloads a page and returns its readable text, truncated to about 4,000 characters so it fits in the context window.
> Write a short tool description for each one that explains what it does and when to use it. Keep the loop as it was. Make the test question something that needs a web search, such as "What is the latest stable version of Python?"

**Check:** Run the script and confirm the model calls `web_search`, then `fetch_url` on a result, then answers with the URL it used.

**Done when:**
- Both tools return real data.
- The printed trace shows the search and fetch calls.
- You understand why the fetch result is truncated.

**Commit:** `git add -A && git commit -m "Add web search and fetch tools"`

---

## Step 4: Move the loop into the Deep Agents harness

**Goal:** Replace the hand-written loop with a Deep Agents agent, using the same two tools.

**Why:** The harness handles the parts you'd otherwise write yourself: planning, managing long conversations, and the tool loop. Comparing this version with the one from Step 3 shows you what the harness is adding. This is the moment the framework becomes understandable, because you've already seen the problem it solves.

**Prompt for Claude Code:**

> Create `agent.py`. Use Deep Agents to create an agent with the same two tools from `raw_loop.py` (`web_search` and `fetch_url`). Set a system prompt telling the agent to search for sources, read them, and answer with the URLs it used. Make the agent answer the question passed as a command-line argument. Look up the current Deep Agents documentation to confirm the setup function and the way to invoke the agent, and tell me which doc page you used. Keep `raw_loop.py` in place for comparison.

**Check:**

```bash
python agent.py "What is the latest stable version of Python?"
```

**Done when:**
- The agent answers the question and includes source URLs.
- You can explain in one or two sentences what the harness does that `raw_loop.py` didn't.
- You know which docs page the setup came from.

**Commit:** `git add agent.py && git commit -m "Run research agent on Deep Agents harness"`

---

## Step 5: Look at the trace

**Goal:** See every step the agent took, including each model call, tool call, and result.

**Why:** Traces are how you debug agents and how you'll show your work in a demo. Reading one tells you whether the agent searched properly, whether it used the sources it cited, and where it wasted steps. You can't improve what you can't see.

**Prompt for Claude Code:**

> Update `agent.py` to print the trace of each run: every model call, tool call with its arguments, and tool result, in order. Use the streaming output that Deep Agents or LangGraph provides rather than writing custom logging if one exists. Also save the trace to `traces/<timestamp>.json`. Add `traces/` to `.gitignore`.

**Check:** Run one question and read the trace. Confirm the cited URLs match URLs the agent actually fetched.

**Done when:**
- The trace is printed and saved.
- You can point to one tool call in the trace and explain what it did.

**Commit:** `git add -A && git commit -m "Add run tracing"`

---

## Step 6: Add a shared filesystem

**Goal:** The agent can save notes and sources to files, and read them back later.

**Why:** Long research runs fill the context window. If the agent writes findings to files and reads only what it needs, it can handle bigger questions without losing track. This is also how sub-agents will share information in Step 7. It's the "context offloading" idea from the architecture diagram.

**Prompt for Claude Code:**

> Update `agent.py` so the agent has access to a filesystem backend for notes and sources. Use the Deep Agents filesystem support, and keep the files in a `workspace/` folder that is cleared at the start of each run. Update the system prompt so the agent saves each source's URL and key facts to a file before writing its answer, then reads those files to write the answer. Check the current docs for how to configure the filesystem backend, and tell me which option you chose and why.

**Check:** Run a question and open `workspace/` after the run. You should see files with notes and URLs.

**Done when:**
- Notes appear in `workspace/` during a run.
- The final answer is built from those notes.
- You can explain why offloading helps with long research.

**Commit:** `git add -A && git commit -m "Add shared workspace filesystem"`

---

## Step 7: Add sub-agents

**Goal:** The main agent (orchestrator) splits a question into subtopics and delegates each one to a sub-agent with its own context.

**Why:** Sub-agents keep each subtopic's research separate, so the orchestrator's context stays small. Work that can be split also runs faster. The tradeoff is more model calls and therefore more cost, so the eval suite in Step 9 will tell you whether it's worth it.

**Prompt for Claude Code:**

> Update `agent.py` to add sub-agents. The orchestrator should split the question into two or three subtopics, delegate each one to a sub-agent, and combine the results from the workspace into the final answer. Give each sub-agent the same two tools and a system prompt that tells it to research only its assigned subtopic and write its notes to a file named after the subtopic. Limit the orchestrator to three sub-agents. Explain how you configured the sub-agents and link the docs you used.

**Check:** Run a broad question, such as "Compare the main approaches to evaluating LLM agents." Check that the trace shows separate sub-agent calls and that `workspace/` has one file per subtopic.

**Done when:**
- Each subtopic has its own sub-agent and its own file.
- The final answer combines all of them.
- You can explain why sub-agents keep the orchestrator's context smaller.

**Commit:** `git add -A && git commit -m "Add sub-agents for subtopic research"`

---

## Step 8: Add human approval before saving

**Goal:** The run pauses before the final report is saved, shows you the draft, and waits for you to approve, edit, or reject it.

**Why:** Human approval is a standard safety and quality step in production agent systems. LangGraph's interrupts let the run pause without losing progress, so you can review it and resume later. This step also shows how a graph can wait for input, which is a core LangGraph idea.

**Prompt for Claude Code:**

> Update `agent.py` so that before the final answer is saved to `report.md`, the run pauses and shows me the draft in the terminal. I should be able to type `approve`, `reject`, or provide edited text. Use LangGraph's interrupt feature (or the Deep Agents equivalent, if one exists) so the run can resume from where it paused. Check the current docs for how interrupts and resuming work, and tell me which doc page you used. Don't change the research steps.

**Check:** Run a question, approve the draft, and confirm `report.md` is written. Then run another question, reject it, and confirm nothing is saved.

**Done when:**
- The run pauses at the draft.
- Approve saves the report, and reject doesn't.
- You can explain what the checkpoint stores so the run can resume.

**Commit:** `git add -A && git commit -m "Add human approval step before saving"`

---

## Step 9: Write the test questions

**Goal:** A file with 10–15 test questions, each with an expected answer or key facts and the source it should cite.

**Why:** Evaluations need a fixed set of questions so you can compare runs fairly. Writing the questions yourself matters. If Claude Code writes them, you won't know what "correct" means, and you won't be able to judge the results. Choose questions where the answer changes or where you already know the facts.

**Do this yourself:** Write 10–15 questions in a file called `evals/questions.json`. Each entry should have:
- `question`: the question text
- `key_facts`: two or three facts a correct answer must include
- `expected_source`: a URL where that information can be verified

Mix difficulty. Include a few easy single-fact questions, a few that need two sources, and at least one that has no clear answer, where the right behavior is to say so.

**Prompt for Claude Code (after you've written the file):**

> Read `evals/questions.json`. Check that every entry has all three fields and that each expected source URL is reachable. Report anything missing or broken, but don't change the questions.

**Check:** Open the file and confirm you can explain why each question is in the set.

**Done when:**
- The file has 10–15 entries with all three fields.
- Every source URL works.
- You can say what a good answer to each question looks like.

**Commit:** `git add evals/questions.json && git commit -m "Add eval questions"`

---

## Step 10: Build the eval runner

**Goal:** A script that runs the agent on every test question and records the results.

**Why:** This script is how you measure whether the agent works. It turns "it seems to work" into numbers you can compare across changes. Scoring has three parts: correctness (are the key facts present?), citation accuracy (did the agent cite a page it actually read?), and cost (how many model calls and tokens did it use?).

**Prompt for Claude Code:**

> Create `evals/run_evals.py`. For each question in `evals/questions.json`, run the agent with human approval disabled, so the run is automatic. Score each answer three ways:
> 1. Correctness: check whether each key fact appears in the answer. Use a simple string or keyword match first. Don't use an LLM judge yet.
> 2. Citation accuracy: check that each URL in the answer was actually fetched during the run, using the trace.
> 3. Cost: record the number of model calls and tool calls.
> Print one line per question and a summary at the end, and save the results to `evals/results/<timestamp>.json`. Explain the scoring method in a docstring at the top of the file.

**Check:**

```bash
python evals/run_evals.py
```

**Done when:**
- The script runs all questions and prints a summary.
- You can explain each of the three scores in one sentence.
- A result file is saved.

**Commit:** `git add evals/run_evals.py && git commit -m "Add eval runner"`

---

## Step 11: Record the baseline

**Goal:** One complete eval run, with the numbers saved, that you'll compare future changes against.

**Why:** A number means nothing alone. The baseline is what makes your later improvements measurable. Write it down before you change anything.

**Do this:** Run the eval script once. Then create `EVALS.md` with:
- The date and the model you used
- The three summary scores
- The three worst questions and why they failed (read the traces)

**Prompt for Claude Code:**

> Read the latest file in `evals/results/`. Create `EVALS.md` with a summary table and a list of the three lowest-scoring questions, with one sentence on the likely cause of each failure for each. Don't change any code.

**Check:** Read your failure analysis and confirm you agree with it after looking at the traces yourself.

**Done when:**
- `EVALS.md` has the baseline scores and your failure notes.
- You can explain the most common failure in one sentence.

**Commit:** `git add EVALS.md && git commit -m "Record baseline eval results"`

---

## Step 12: Make one change and measure it

**Goal:** Change one thing, rerun the evals, and compare the results with the baseline.

**Why:** This is the core of engineering an agent: change one variable, measure, and keep the change only if it helps. Changing several things at once makes it impossible to know what worked. Pick the change based on the most common failure from Step 11.

**Prompt for Claude Code:**

> Based on the most common failure in `EVALS.md`, make one focused change to the system prompt or the tool descriptions in `agent.py`. Don't change anything else. Then rerun the evals and add a new section to `EVALS.md` comparing the scores with the baseline. Say whether the change helped, hurt, or made no difference, and why.

**Check:** Compare the before and after numbers yourself, and confirm the conclusion matches them.

**Done when:**
- You have a before-and-after comparison in `EVALS.md`.
- You can explain the change and why you think it did or didn't help.
- If the change hurt the scores, you reverted it and noted that in `EVALS.md`.

**Commit:** `git add -A && git commit -m "Improve [what you changed], with eval comparison"`

---

## Step 13: Write the README and record a demo

**Goal:** A README that someone can understand in five minutes, and a short demo recording.

**Why:** The README and demo are what a hiring manager actually sees. A good project with a weak README looks unfinished. Writing the README also tests whether you understand the system, because you have to explain it simply.

**Prompt for Claude Code:**

> Create `README.md` with these sections: what the project does; the architecture diagram (use a text or Mermaid diagram); how to set it up and run it; how evals work; the baseline and improved scores from `EVALS.md`; known limitations; and what I'd build next. Keep it under 300 lines. Don't invent results. Use only numbers from `EVALS.md`.

**Do this yourself:**
- Review the README and rewrite anything you can't explain.
- Record a 2–3 minute screen recording showing one question running, the trace, the approval step, and the eval summary.

**Done when:**
- The README matches what the code actually does.
- The demo shows the whole flow.
- You can answer "what would you change next?" in a minute.

**Commit:** `git add -A && git commit -m "Add README and project documentation"`

---

## Step 14: Clean up before sharing

**Goal:** Remove unused code, check for leaked secrets, and make the project easy to run.

**Why:** Dead code and leftover experiments make a project look rushed. Interviewers often ask you to walk through the code, so every file should have a clear purpose.

**Prompt for Claude Code:**

> Review the whole project. Remove unused files, including `raw_loop.py` if it's no longer needed (keep it if you find it useful for explaining the design). Check that no secrets are in the code or git history. Make sure `README.md` setup instructions work by following them from scratch in a new folder. Report anything that doesn't work.

**Check:** Clone the repo into a new folder and follow your README from start to finish.

**Done when:**
- A fresh clone runs following only the README.
- No secrets appear in the repo or its history.
- Every file has a clear purpose.

**Commit:** `git add -A && git commit -m "Clean up project for review"`

---

## After the build: interview prep

Be ready to explain:
1. The tool-calling loop, from your `raw_loop.py` version.
2. What the harness adds on top of that loop.
3. One failure you hit and how you found it in the trace.
4. The tradeoff of sub-agents: better context isolation versus more cost.
5. Why you used evals, and what the numbers showed.
6. What you'd build next.