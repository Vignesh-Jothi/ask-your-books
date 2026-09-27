/* Ask Your Books — UI logic. Thin client: renders responses, persists the
   session id per browser, never computes numbers (the backend does that).
   The right-hand "Actions" panel mirrors the response trace: every tool call,
   its guarded SQL, status and latency — the observability view. */
"use strict";

const byId = (id) => document.getElementById(id);
const chatArea = byId("chat-area");
const form = byId("ask-form");
const input = byId("question");
const sendButton = byId("send-button");
const statusBar = byId("status-bar");
const userSelect = byId("user-select");
const obsFeed = byId("obs-feed");

const sessionKey = "ask-your-books.session_id";
let sessionId = localStorage.getItem(sessionKey) || crypto.randomUUID();

const BADGE = { answered: "answered", refused: "refused", clarifying: "clarifying", error: "error" };

function escapeHtml(text) {
  return String(text).replace(/[&<>"']/g, (ch) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[ch]);
}

function renderMarkdown(text) {
  const escaped = escapeHtml(text);
  if (!window.marked) return escaped.replace(/\n/g, "<br>");
  const html = window.marked.parse(escaped, { breaks: true });
  // belt-and-braces: never let the answer open links/scripts
  return html
    .replace(/\son\w+\s*=\s*"[^"]*"/gi, "")
    .replace(/href="javascript:[^"]*"/gi, 'href="#"');
}

function formatInr(paise) {
  // Indian digit grouping: 12,34,567 — the same rule the backend uses.
  const num = Math.abs(Math.trunc(paise / 100));
  const digits = String(num);
  if (digits.length <= 3) return digits;
  const head = digits.slice(0, -3);
  const tail = digits.slice(-3);
  const groupedHead = head.replace(/\B(?=(\d{2})+$)/g, ",");
  return `${groupedHead},${tail}`;
}

function appendMessage(role, html) {
  const wrapper = document.createElement("div");
  wrapper.className = `message ${role}`;
  const label = document.createElement("span");
  label.className = "role-label";
  label.textContent = role === "user" ? "You" : "Assistant";
  const body = document.createElement("div");
  body.className = "message-content";
  body.innerHTML = html;
  wrapper.append(label, body);
  chatArea.append(wrapper);
  chatArea.scrollTo(0, chatArea.scrollHeight);
}

function renderRows(rows) {
  if (!rows || !rows.length) return "";
  const cols = Object.keys(rows[0]);
  const head = cols.map((c) => `<th>${escapeHtml(c)}</th>`).join("");
  const body = rows.map((row) => "<tr>" + cols.map((c) => {
    const value = row[c];
    const looksMonetary = /paise|amount|balance|total|outstanding/i.test(c) && typeof value === "number";
    const text = looksMonetary ? `₹${formatInr(value)}` : escapeHtml(value);
    return `<td class="${looksMonetary ? "num" : ""}">${text}</td>`;
  }).join("") + "</tr>").join("");
  return `<table class="answer-table"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`;
}

/* ---- observability: one card per turn, one row per tool call ---- */
const obsCount = byId("obs-count");
let obsToolCalls = 0;

const obsPlaceholder = document.createElement("div");
obsPlaceholder.className = "obs-placeholder";
obsPlaceholder.textContent =
  "No actions yet — the agent's tool calls, guarded SQL and guard decisions will appear here.";

function statusChip(status) {
  return `<span class="status-step ${escapeHtml(status)}">${escapeHtml(status)}</span>`;
}

function argChips(args) {
  return Object.entries(args || {})
    .map(([key, value]) => `<span class="arg-chip"><b>${escapeHtml(key)}</b>${escapeHtml(value)}</span>`)
    .join("");
}

function traceStepRow(step) {
  const sqlBlock = `<div class="obs-label">guarded sql</div>
      <pre class="obs-sql">${escapeHtml(step.sql || "(no sql — agent-native tool)")}</pre>`;
  const errorBlock = step.error
    ? `<div class="obs-label">guard / error</div><pre class="obs-sql error">${escapeHtml(step.error)}</pre>`
    : "";
  return `
    <div class="step-row ${escapeHtml(step.status)}">
      <div class="step-head">
        <span class="step-dot"></span>
        <span class="step-name">${escapeHtml(step.tool)}</span>
        ${statusChip(step.status)}
        <span class="step-stats">${step.rows} rows · ${step.latency_ms} ms</span>
        <button type="button" class="step-toggle" aria-expanded="false">sql</button>
      </div>
      <div class="step-body">
        ${argChips(step.args) || '<span class="muted">no arguments</span>'}
        ${sqlBlock}
        ${errorBlock}
      </div>
    </div>`;
}

function appendObsCard(resp) {
  obsPlaceholder.remove();
  const steps = (resp.trace || []).map(traceStepRow);
  obsToolCalls += steps.length;
  obsCount.textContent = `${obsToolCalls} tool call${obsToolCalls === 1 ? "" : "s"}`;
  const card = document.createElement("details");
  card.className = "obs-card";
  card.classList.add(resp.status);
  card.open = true;
  const traceId = (resp.trace_id || "").slice(0, 12);
  const toolWords = steps.length
    ? `${steps.length} tool call${steps.length === 1 ? "" : "s"}`
    : "no tools";
  card.innerHTML = `
    <summary>
      <span class="caret">▶</span>
      <span class="obs-tool">turn</span>
      <span class="badge ${BADGE[resp.status] ?? "error"}">${escapeHtml(resp.status)}</span>
      <span class="obs-meta">${toolWords} · ${resp.tokens} tok</span>
    </summary>
    <div class="obs-detail">
      ${steps.join("") || `<div class="obs-empty">Text-only reply — the model answered without calling a tool.</div>`}
    </div>
    <div class="obs-footer">
      <span>trace ${escapeHtml(traceId)}</span>
      <span>org ${escapeHtml(resp.org_id || "")}</span>
      <span>period ${escapeHtml(resp.period || "—")}</span>
      <span>rows ${(resp.rows || []).length}</span>
    </div>`;
  obsFeed.append(card);
  obsFeed.scrollTo(0, obsFeed.scrollHeight);
}

obsFeed.append(obsPlaceholder);

/* "sql" button on a step row toggles the guarded SQL / arguments */
obsFeed.addEventListener("click", (event) => {
  const toggle = event.target.closest(".step-toggle");
  if (!toggle) return;
  const row = toggle.closest(".step-row");
  const isOpen = row.classList.toggle("show");
  toggle.setAttribute("aria-expanded", String(isOpen));
});

function handleResponse(resp) {
  const badge = `<span class="badge ${BADGE[resp.status] ?? "error"}">${escapeHtml(resp.status)}</span>`;
  const text = resp.text ? `<p>${renderMarkdown(resp.text)}</p>` : "";
  const refusal = resp.refusal ? `<p class="muted">${escapeHtml(resp.refusal)}</p>` : "";
  appendMessage("assistant", `${badge}${text}${refusal}${renderRows(resp.rows)}`);
  appendObsCard(resp);
}

function setStatus(text, isError = false) {
  statusBar.textContent = text;
  statusBar.className = isError ? "status-bar error" : "status-bar";
}

async function ask(question) {
  if (!question.trim()) return;
  input.value = "";
  appendMessage("user", escapeHtml(question.trim()));
  sendButton.disabled = true;
  setStatus("Thinking… guardrails on…");
  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-User-Id": userSelect.value,
      },
      body: JSON.stringify({ message: question.trim(), session_id: sessionId }),
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const payload = await response.json();
    handleResponse(payload);
    setStatus(payload.status === "clarifying" ? "Assistant needs a detail — pick a suggestion or rephrase." : "Ready");
  } catch (error) {
    appendMessage("assistant", `<p>Something went wrong talking to the API.</p><p class="muted">${escapeHtml(String(error))}</p>`);
    setStatus("API unreachable — is the server running?", true);
  } finally {
    sendButton.disabled = false;
    input.focus();
  }
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  ask(input.value);
});

document.querySelectorAll(".chip").forEach((chip) => {
  chip.addEventListener("click", () => ask(chip.dataset.q));
});

input.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    form.requestSubmit();
  }
});
