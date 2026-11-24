"use strict";

// ---------- small helpers ----------
function el(tag, cls, text) {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text != null) node.textContent = text;
  return node;
}
const $ = (selector) => document.querySelector(selector);
const fmt = (n) => Number(n).toLocaleString("en-US");
const short = (n) => (n >= 1000 ? (n / 1000).toFixed(n >= 100000 ? 0 : 1).replace(/\.0$/, "") + "k" : String(n));
const reduceMotion = matchMedia("(prefers-reduced-motion: reduce)").matches;

function host(url) {
  try { return new URL(url).hostname.replace(/^www\./, ""); } catch (e) { return url; }
}
function link(url, label) {
  const a = el("a", "", label || url);
  a.href = url; a.target = "_blank"; a.rel = "noopener noreferrer";
  return a;
}
function agentName(agent) {
  if (agent === "orchestrator") return "Orchestrator";
  if (agent === "human") return "You";
  return "Researcher " + agent.split("-")[1];
}
const AGENT_VAR = { orchestrator: "--a-orch", "researcher-1": "--a-r1", "researcher-2": "--a-r2", "researcher-3": "--a-r3" };

// ---------- tiny, safe markdown (builds DOM nodes, never HTML strings) ----------
function inline(text) {
  const frag = document.createDocumentFragment();
  const pattern = /(\*\*[^*]+\*\*|`[^`]+`|\[[^\]]+\]\(https?:\/\/[^)\s]+\)|https?:\/\/[^\s)<>\]]+)/g;
  let last = 0, match;
  while ((match = pattern.exec(text))) {
    if (match.index > last) frag.append(text.slice(last, match.index));
    const token = match[0];
    if (token.startsWith("**")) frag.append(el("strong", "", token.slice(2, -2)));
    else if (token[0] === "`") frag.append(el("code", "", token.slice(1, -1)));
    else if (token[0] === "[") {
      const parts = /^\[([^\]]+)\]\((.+)\)$/.exec(token);
      frag.append(link(parts[2], parts[1]));
    } else {
      const url = token.replace(/[.,;:]+$/, "");
      frag.append(link(url), token.slice(url.length));
    }
    last = match.index + token.length;
  }
  if (last < text.length) frag.append(text.slice(last));
  return frag;
}

function markdown(source) {
  const root = el("div", "md");
  let list = null, paragraph = [];
  const flush = () => {
    if (!paragraph.length) return;
    const p = el("p"); p.append(inline(paragraph.join(" "))); root.append(p); paragraph = [];
  };
  for (const raw of source.split("\n")) {
    const line = raw.trimEnd();
    let m;
    if (!line.trim()) { flush(); list = null; continue; }
    if (/^---+$/.test(line.trim())) { flush(); list = null; root.append(el("hr")); continue; }
    if ((m = /^#{1,4}\s+(.*)$/.exec(line))) {
      flush(); list = null; const h = el("h4"); h.append(inline(m[1])); root.append(h); continue;
    }
    if ((m = /^\s*([*-]|\d+\.)\s+(.*)$/.exec(line))) {
      flush();
      const ordered = /\d/.test(m[1]);
      if (!list || list.dataset.ordered !== String(ordered)) {
        list = el(ordered ? "ol" : "ul"); list.dataset.ordered = String(ordered); root.append(list);
      }
      const li = el("li"); li.append(inline(m[2])); list.append(li); continue;
    }
    list = null; paragraph.push(line.trim());
  }
  flush();
  return root;
}

// ---------- timeline steps ----------
const ACTIONS = {
  web_search: (s) => ["Searched the web", s.args.query],
  fetch_url: (s) => ["Opened a page", s.args.url],
  write_file: (s) => ["Wrote notes", s.args.file_path],
  read_file: (s) => ["Read notes", s.args.file_path],
  ls: (s) => ["Listed the notes folder", s.args.path || ""],
  task: (s) => ["Delegated a subtopic", s.args.description],
  save_report: () => ["Proposed the report to save", ""],
};
const DECISIONS = { approve: "Approved the draft", edit: "Edited the draft, then approved it", reject: "Rejected the draft" };

function details(summary) {
  const d = el("details"); d.append(el("summary", "", summary)); return d;
}
function textDetails(summary, text) {
  const d = details(summary); d.append(el("div", "body", text)); return d;
}

function toolDetails(card, step) {
  const result = step.result;
  if (step.name === "web_search" && result && result.type === "search" && result.items.length) {
    const d = details(result.items.length + " results");
    const ul = el("ul", "results");
    result.items.forEach((item) => {
      const li = el("li");
      li.append(link(item.url, item.title || host(item.url)), el("small", "", host(item.url)));
      ul.append(li);
    });
    d.append(ul); card.append(d);
  } else if (step.name === "write_file" && step.args.content) {
    card.append(textDetails("Show the notes", step.args.content));
  } else if (step.name === "save_report" && step.args.content) {
    card.append(textDetails("Show the draft", step.args.content));
  } else if (result && result.type === "text" && result.text) {
    const label = step.name === "fetch_url" ? "Page text (" + fmt(result.text.length) + " characters)"
      : step.name === "task" ? "The researcher's reply" : "Show the result";
    card.append(textDetails(label, result.text));
  }
}

function stepNode(step) {
  const li = el("li", "step");
  li.dataset.agent = step.agent;
  li.hidden = true;
  const card = el("div", "step-card");
  const head = el("div", "step-head");
  head.append(el("span", "who", agentName(step.agent)));
  li.append(card); card.append(head);

  if (step.kind === "tool") {
    const [what, target] = (ACTIONS[step.name] || ((s) => [s.name, JSON.stringify(s.args)]))(step);
    head.append(el("span", "what", what));
    if (step.tokens) head.append(el("span", "tok", fmt(step.tokens) + " tokens"));
    if (target) head.append(el("div", "target", target));
    toolDetails(card, step);
  } else if (step.kind === "says") {
    const isAnswer = step.agent === "orchestrator";
    head.append(el("span", "what", isAnswer ? "Wrote the final answer" : "Reported back"));
    if (step.tokens) head.append(el("span", "tok", fmt(step.tokens) + " tokens"));
    if (isAnswer) card.append(textDetails("Show the message", step.text));
    else head.append(el("div", "target", step.text));
  } else if (step.kind === "approval") {
    head.append(el("span", "what", DECISIONS[step.decision[0]] || "Reviewed the draft"));
    if (step.outcome && step.outcome.text) card.append(el("p", "approval-text", step.outcome.text));
  }
  return li;
}

// ---------- the run view ----------
const player = { timer: null, nodes: [], shown: 0, outcome: null, progress: null };

function stat(value, label) {
  const box = el("div", "stat"); box.append(el("b", "", value), el("span", "", label)); return box;
}

function outcomeNodes(run) {
  const wrap = el("div", "outcome");

  const answer = el("div", "panel");
  answer.append(el("h3", "", "Final answer"), el("p", "sub", "Written by the orchestrator from its researchers' notes."));
  answer.append(markdown(run.answer || "(no answer recorded)"));
  wrap.append(answer);

  const checked = el("div", "panel");
  checked.append(el("h3", "", "Citation check"));
  checked.append(el("p", "sub", "Each URL cited in the answer, compared with the pages the agent actually opened during the run."));
  const total = run.citations.length, opened = run.citations.filter((c) => c.fetched).length;
  const verdict = el("p", "verdict");
  if (!total) verdict.textContent = "This answer cites no URLs, so there is nothing to check.";
  else verdict.textContent = opened + " of " + total + " cited URL" + (total === 1 ? " was" : "s were") + " opened during the run.";
  checked.append(verdict);
  if (total) {
    const ul = el("ul", "cites");
    run.citations.forEach((c) => {
      const li = el("li");
      const url = el("span", "url"); url.append(link(c.url));
      li.append(url, el("span", "badge " + (c.fetched ? "ok" : "bad"), c.fetched ? "Opened" : "Never opened"));
      ul.append(li);
    });
    checked.append(ul);
  }
  wrap.append(checked);

  if (run.eval) {
    const score = el("div", "panel");
    const ok = run.eval.correctness >= 1;
    score.append(el("h3", "", "Eval result"));
    score.append(el("p", "sub", "This question is in the 12-question eval suite. The score is a text match against known key facts."));
    const line = el("p", "verdict");
    line.append("Correctness ", el("span", "badge " + (ok ? "ok" : run.eval.correctness > 0 ? "warn" : "bad"), run.eval.correctness.toFixed(2)),
      "  Looked for: " + run.eval.key_facts.join(", "));
    score.append(line);
    wrap.append(score);
  }
  return wrap;
}

function renderRun(run) {
  stopPlayback();
  const section = $("#run");
  section.replaceChildren();
  section.hidden = false;

  const head = el("div", "run-head");
  head.append(el("span", "tag" + (run.tag === "When it goes wrong" ? " bad" : ""), run.tag));
  head.append(el("h2", "", run.title));
  head.append(el("p", "ask", "“" + run.question + "”"));
  head.append(el("p", "note", run.note));
  const stats = el("div", "stats");
  stats.append(stat(run.stats.model_calls, "model calls"), stat(run.stats.tool_calls, "tool calls"),
    stat(run.stats.fetch_calls, "pages opened"), stat(fmt(run.stats.total_tokens), "tokens"));
  if (run.stats.researchers) stats.append(stat(run.stats.researchers, run.stats.researchers === 1 ? "researcher" : "researchers"));
  stats.append(stat(run.recorded, "recorded, " + run.model));
  head.append(stats);

  const controls = el("div", "controls");
  const replay = el("button", "btn primary", "Replay");
  replay.type = "button";
  const skip = el("button", "btn", "Skip to the end");
  skip.type = "button";
  const progress = el("span", "progress");
  controls.append(replay, skip, progress);
  const legend = el("div", "legend");
  [...new Set(run.steps.map((s) => s.agent))].forEach((agent) => {
    const item = el("span", "", agentName(agent));
    const dot = el("i"); dot.style.setProperty("--c", "var(" + (AGENT_VAR[agent] || "--a-human") + ")");
    item.prepend(dot); legend.append(item);
  });
  controls.append(legend);
  head.append(controls);
  section.append(head);

  const list = el("ol", "steps");
  const nodes = run.steps.map(stepNode);
  nodes.forEach((n) => list.append(n));
  section.append(list);
  const outcome = outcomeNodes(run);
  outcome.hidden = true;
  section.append(outcome);

  Object.assign(player, { nodes, outcome, progress, shown: 0 });
  replay.addEventListener("click", startPlayback);
  skip.addEventListener("click", finishPlayback);
  startPlayback();
}

function reveal(index) {
  const node = player.nodes[index];
  node.hidden = false;
  if (!reduceMotion) node.classList.add("enter");
  player.nodes.forEach((n) => n.classList.remove("now"));
  node.classList.add("now");
  player.progress.textContent = "Step " + (index + 1) + " of " + player.nodes.length;
  if (!reduceMotion) {
    const box = node.getBoundingClientRect();
    if (box.bottom > innerHeight - 24) node.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }
}

function tick() {
  if (player.shown >= player.nodes.length) return finishPlayback();
  reveal(player.shown++);
  player.timer = setTimeout(tick, 520);
}

function startPlayback() {
  stopPlayback();
  player.shown = 0;
  player.nodes.forEach((n) => { n.hidden = true; n.classList.remove("enter", "now"); });
  player.outcome.hidden = true;
  if (reduceMotion) return finishPlayback();
  tick();
}

function stopPlayback() {
  clearTimeout(player.timer);
  player.timer = null;
}

function finishPlayback() {
  stopPlayback();
  player.nodes.forEach((n) => { n.hidden = false; n.classList.remove("now"); });
  player.shown = player.nodes.length;
  player.outcome.hidden = false;
  player.progress.textContent = "All " + player.nodes.length + " steps";
}

// ---------- the example cards ----------
function renderCards(examples) {
  const grid = $("#examples");
  grid.replaceChildren();
  examples.forEach((example) => {
    const card = el("button", "card");
    card.type = "button"; card.dataset.id = example.id; card.setAttribute("aria-pressed", "false");
    card.setAttribute("role", "listitem");
    card.append(el("span", "tag" + (example.tag === "When it goes wrong" ? " bad" : ""), example.tag));
    card.append(el("h3", "", example.title));
    card.append(el("p", "q", "“" + example.question + "”"));
    const s = example.stats;
    card.append(el("p", "meta", s.model_calls + " model calls · " + short(s.total_tokens) + " tokens" +
      (s.researchers ? " · " + s.researchers + (s.researchers === 1 ? " researcher" : " researchers") : "")));
    card.addEventListener("click", () => { location.hash = example.id; });
    grid.append(card);
  });
}

function markSelected(id) {
  document.querySelectorAll(".card").forEach((c) => c.setAttribute("aria-pressed", String(c.dataset.id === id)));
}

async function openExample(id) {
  markSelected(id);
  const section = $("#run");
  try {
    const response = await fetch("/api/examples/" + encodeURIComponent(id));
    if (!response.ok) throw new Error("HTTP " + response.status);
    renderRun(await response.json());
    section.scrollIntoView({ behavior: reduceMotion ? "auto" : "smooth", block: "start" });
  } catch (error) {
    section.hidden = false;
    section.replaceChildren(el("p", "note", "Could not load that run (" + error.message + "). Is the server running?"));
  }
}

// ---------- the "why this exists" section ----------
function renderWhy(summary) {
  const b = summary.baseline, e = summary.experiment;
  const section = $("#why");
  section.replaceChildren();
  const extraTokens = Math.round((e.tokens_per_question / b.tokens_per_question - 1) * 100);

  section.append(el("p", "eyebrow", "Why this exists"));
  section.append(el("h2", "", "It answered correctly, and cited pages it never read."));
  section.append(el("p", "lead",
    "The agent usually got the answer right, because search snippets often contained it. But it listed sources it had never opened. " +
    "A 12-question eval suite put numbers on that: correctness " + b.correctness.toFixed(2) + ", citation accuracy " + b.citation_accuracy.toFixed(2) +
    ". One fix was tried, and the table below decided its fate."));

  const rows = [
    ["Correctness", b.correctness, e.correctness, true, (v) => v.toFixed(2), e.correctness_corrected ? e.correctness_corrected.toFixed(2) + " once one scoring false positive is corrected" : ""],
    ["Citation accuracy", b.citation_accuracy, e.citation_accuracy, true, (v) => v.toFixed(2), ""],
    ["Cited pages never opened", b.unfetched_citations, e.unfetched_citations, false, fmt, ""],
    ["Questions with no page opened", b.no_fetch_questions, e.no_fetch_questions, false, fmt, ""],
    ["Tokens per question", b.tokens_per_question, e.tokens_per_question, false, fmt, "+" + extraTokens + "%"],
  ];
  const wrap = el("div", "table-wrap");
  const table = el("table");
  const headRow = el("tr");
  ["Measure", "Baseline", "With the fix (reverted)", ""].forEach((t) => headRow.append(el("th", "", t)));
  const thead = el("thead"); thead.append(headRow); table.append(thead);
  const tbody = el("tbody");
  rows.forEach(([label, before, after, higherIsBetter, format, note]) => {
    const tr = el("tr");
    const better = higherIsBetter ? after > before : after < before;
    tr.append(el("td", "", label), el("td", "num", format(before)), el("td", "num", format(after)));
    const last = el("td");
    last.append(el("span", "badge " + (better ? "ok" : "bad"), better ? "Better" : "Worse"));
    if (note) last.append(el("span", "delta verdict", note));
    tr.append(last); tbody.append(tr);
  });
  table.append(tbody); wrap.append(table); section.append(wrap);

  section.append(el("p", "after",
    "The fix made the agent open more pages, and citation accuracy rose. But it opened the wrong ones: a stale copy of a ranking, an old release page. " +
    "Answers got worse and cost about " + extraTokens + "% more tokens, so the change was reverted. The third run above shows exactly how it went wrong."));

  const how = el("div", "how");
  [
    ["The agent", "An orchestrator splits a question into subtopics. Researcher sub-agents search, read pages and save notes to a shared folder. A person approves the draft before it is saved."],
    ["The evidence", "Every run is a saved trace: each model call, tool call and result. The evals score correctness, citation accuracy and cost across " + b.questions + " questions."],
    ["The stack", "Google Gemini (" + summary.model + "), Deep Agents on LangGraph, Tavily for search. This page is a FastAPI server replaying recorded runs."],
  ].forEach(([title, text]) => { const d = el("div"); d.append(el("h4", "", title), el("p", "", text)); how.append(d); });
  section.append(how);
  section.hidden = false;
}

// ---------- theme ----------
function toggleTheme() {
  const root = document.documentElement;
  const dark = root.dataset.theme === "dark" || (!root.dataset.theme && matchMedia("(prefers-color-scheme: dark)").matches);
  const next = dark ? "light" : "dark";
  root.dataset.theme = next;
  try { localStorage.setItem("theme", next); } catch (e) { /* storage may be blocked */ }
}

// ---------- start ----------
async function main() {
  $("#theme").addEventListener("click", toggleTheme);
  try {
    const [examples, summary] = await Promise.all([
      fetch("/api/examples").then((r) => r.json()),
      fetch("/api/summary").then((r) => r.json()),
    ]);
    renderCards(examples);
    renderWhy(summary);
    const open = () => { const id = location.hash.slice(1); if (examples.some((x) => x.id === id)) openExample(id); };
    addEventListener("hashchange", open);
    open();
  } catch (error) {
    $("#examples").replaceChildren(el("p", "note", "Could not reach the server (" + error.message + ")."));
  }
}
main();
