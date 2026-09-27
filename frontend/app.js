/* Ask Your Books — UI logic. Thin client: renders responses, persists the
   session id per browser, never computes numbers (the backend does that). */
"use strict";

const byId = (id) => document.getElementById(id);
const chatArea = byId("chat-area");
const form = byId("ask-form");
const input = byId("question");
const sendButton = byId("send-button");
const statusBar = byId("status-bar");
const userSelect = byId("user-select");

const sessionKey = "ask-your-books.session_id";
let sessionId = localStorage.getItem(sessionKey) || crypto.randomUUID();

function escapeHtml(text) {
  return String(text).replace(/[&<>"']/g, (ch) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[ch]);
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

function appendMessage(role, html, traceText) {
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
  if (traceText) {
    const chip = document.createElement("span");
    chip.className = "trace-line";
    chip.textContent = traceText;
    chatArea.append(chip);
  }
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

const BADGE = { answered: "answered", refused: "refused", clarifying: "clarifying", error: "error" };

function handleResponse(resp) {
  const badge = `<span class="badge ${BADGE[resp.status] ?? "error"}">${escapeHtml(resp.status)}</span>`;
  const text = escapeHtml(resp.text || "");
  const refusal = resp.refusal ? `<p class="muted">${escapeHtml(resp.refusal)}</p>` : "";
  let traceText = "";
  const lastTool = (resp.trace || []).filter((t) => t.status === "ok").pop();
  if (lastTool) traceText = `read-only · ${lastTool.tool}`;
  appendMessage("assistant", `${badge}<p>${text}</p>${refusal}${renderRows(resp.rows)}`, traceText);
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