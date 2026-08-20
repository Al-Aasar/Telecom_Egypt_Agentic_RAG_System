const STRINGS = {
  ar: {
    headerTitle: "اسأل عن خدمات TE",
    headerSub: "إجابات مبنية على محتوى الموقع الرسمي فقط — بحث هجين (Dense + Sparse)",
    emptyTitle: "ابدأ بسؤال",
    emptySub: 'مثال: "ما هي باقات الإنترنت المنزلي المتاحة؟"',
    placeholder: "اكتب سؤالك هنا...",
    newChat: "+ محادثة جديدة",
    sessionsLabel: "المحادثات المحفوظة",
    thinking: "جارٍ البحث والتحليل...",
    error: "حدث خطأ أثناء الاتصال بالخادم. حاول مرة أخرى.",
    deleteConfirm: "تحذف المحادثة دي نهائيًا؟",
    deleteTitle: "حذف المحادثة",
  },
  en: {
    headerTitle: "Ask about TE services",
    headerSub: "Answers grounded only in the official site — hybrid search (Dense + Sparse)",
    emptyTitle: "Start with a question",
    emptySub: '"What home internet packages are available?"',
    placeholder: "Type your question...",
    newChat: "+ New chat",
    sessionsLabel: "Saved conversations",
    thinking: "Searching and thinking...",
    error: "Something went wrong reaching the server. Please try again.",
    deleteConfirm: "Delete this conversation permanently?",
    deleteTitle: "Delete conversation",
  },
};

// Backend base URL. The frontend (GitHub Pages) and backend (Hugging Face
// Space) are on different origins, so every fetch below must hit the full
// URL, not a relative path like "/api/chat" — a relative path would
// resolve against the GitHub Pages origin and 404.
const API_BASE_URL = "https://al-aasar-telecom-egypt-agentic-rag-system.hf.space";

let lang = "ar";
let currentSessionId = null;

// Each browser gets its own random id, generated once and kept in
// localStorage, so the backend can scope chat history per-user instead of
// showing everyone's saved conversations to everyone. This is device/
// browser-level isolation, not a real login — clearing site data or
// switching browsers starts a fresh, empty history.
function getOrCreateUserId() {
  const KEY = "te_rag_user_id";
  let id = localStorage.getItem(KEY);
  if (!id) {
    id = (crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(36).slice(2)}`);
    localStorage.setItem(KEY, id);
  }
  return id;
}
const userId = getOrCreateUserId();
const authHeaders = (extra = {}) => ({ "X-User-Id": userId, ...extra });

const el = (id) => document.getElementById(id);
const messagesEl = el("messages");
const emptyState = el("emptyState");
const form = el("composerForm");
const input = el("messageInput");
const sendBtn = el("sendBtn");
const sessionsList = el("sessionsList");
const sidebar = el("sidebar");
const menuToggle = el("menuToggle");
const sidebarOverlay = el("sidebarOverlay");

function openSidebar() {
  sidebar.classList.add("open");
  sidebarOverlay.classList.add("visible");
  menuToggle.setAttribute("aria-expanded", "true");
}
function closeSidebar() {
  sidebar.classList.remove("open");
  sidebarOverlay.classList.remove("visible");
  menuToggle.setAttribute("aria-expanded", "false");
}
menuToggle.addEventListener("click", () => {
  sidebar.classList.contains("open") ? closeSidebar() : openSidebar();
});
sidebarOverlay.addEventListener("click", closeSidebar);

function applyLang() {
  const s = STRINGS[lang];
  // setText is defensive: a missing element (e.g. HTML/JS drifting out
  // of sync) logs a warning instead of throwing and killing the rest of
  // this function plus everything queued after it in the init block
  // (refreshSessions(), loadSession()).
  const setText = (id, val) => {
    const node = el(id);
    if (node) {
      node.textContent = val;
    } else {
      console.warn(`applyLang: missing element #${id}`);
    }
  };

  setText("headerTitle", s.headerTitle);
  setText("headerSub", s.headerSub);
  setText("emptyTitle", s.emptyTitle);
  setText("emptySub", s.emptySub);
  input.placeholder = s.placeholder;
  const newChatSpan = el("newChatBtn")?.querySelector("span");
  if (newChatSpan) newChatSpan.textContent = s.newChat;
  setText("sessionsLabel", s.sessionsLabel);
  document.body.classList.toggle("ltr", lang === "en");
  document.documentElement.dir = lang === "ar" ? "rtl" : "ltr";
  document.documentElement.lang = lang;
}

el("langToggle").addEventListener("click", () => {
  lang = lang === "ar" ? "en" : "ar";
  applyLang();
});

// ---------- self-contained markdown-lite renderer ----------
// No external library/CDN — some networks block those. Escapes HTML
// first (so raw content is never trusted), then applies a small set
// of regex transforms for the formatting an LLM actually produces:
// **bold**, *italic*, `code`, [text](url), and - / 1. lists.
function escapeHtml(str) {
  return str
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function renderInline(text) {
  let out = escapeHtml(text);
  out = out.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
  out = out.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  out = out.replace(/(^|[^*])\*([^*\n]+)\*(?!\*)/g, "$1<em>$2</em>");
  out = out.replace(/`([^`]+)`/g, "<code>$1</code>");
  return out;
}

// A markdown table row: leading/trailing pipes optional, cells separated by |.
// Matches "| a | b |" and "a | b" but not a normal sentence with a stray "|".
function isTableRow(line) {
  return /^\|?.+\|.+\|?$/.test(line) && line.includes("|");
}

// The separator row under a table header, e.g. "|---|:---:|---|" or "---|---".
function isTableSeparator(line) {
  return /^\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?$/.test(line);
}

function splitTableRow(line) {
  let cells = line.trim();
  if (cells.startsWith("|")) cells = cells.slice(1);
  if (cells.endsWith("|")) cells = cells.slice(0, -1);
  return cells.split("|").map((c) => c.trim());
}

function renderTable(lines) {
  // lines[0] = header row, lines[1] = separator row, rest = body rows
  const headerCells = splitTableRow(lines[0]);
  const bodyRows = lines.slice(2).map(splitTableRow);

  const thead = `<thead><tr>${headerCells
    .map((c) => `<th>${renderInline(c)}</th>`)
    .join("")}</tr></thead>`;

  const tbody = `<tbody>${bodyRows
    .map((row) => `<tr>${row.map((c) => `<td>${renderInline(c)}</td>`).join("")}</tr>`)
    .join("")}</tbody>`;

  return `<div class="table-wrap"><table>${thead}${tbody}</table></div>`;
}

function renderMarkdownLite(text) {
  const blocks = text.trim().split(/\n\s*\n/);
  return blocks
    .map((block) => {
      const rawLines = block.split("\n").map((l) => l.trim()).filter(Boolean);
      if (!rawLines.length) return "";

      // A block can mix a heading line with a table/list below it (the LLM
      // often emits "### Title" directly above a table with no blank line
      // between them), so walk the block line-by-line instead of assuming
      // the whole block is one type.
      const html = [];
      let i = 0;
      while (i < rawLines.length) {
        const line = rawLines[i];

        const headingMatch = line.match(/^(#{1,6})\s+(.*)$/);
        if (headingMatch) {
          const level = Math.min(headingMatch[1].length, 6);
          html.push(`<h${level}>${renderInline(headingMatch[2])}</h${level}>`);
          i += 1;
          continue;
        }

        if (
          isTableRow(line) &&
          i + 1 < rawLines.length &&
          isTableSeparator(rawLines[i + 1])
        ) {
          const tableLines = [line, rawLines[i + 1]];
          let j = i + 2;
          while (j < rawLines.length && isTableRow(rawLines[j]) && !isTableSeparator(rawLines[j])) {
            tableLines.push(rawLines[j]);
            j += 1;
          }
          html.push(renderTable(tableLines));
          i = j;
          continue;
        }

        // Collect a run of consecutive bullet or numbered lines into one list.
        if (/^[-*]\s+/.test(line)) {
          const items = [];
          while (i < rawLines.length && /^[-*]\s+/.test(rawLines[i])) {
            items.push(`<li>${renderInline(rawLines[i].replace(/^[-*]\s+/, ""))}</li>`);
            i += 1;
          }
          html.push(`<ul>${items.join("")}</ul>`);
          continue;
        }
        if (/^\d+[.)]\s+/.test(line)) {
          const items = [];
          while (i < rawLines.length && /^\d+[.)]\s+/.test(rawLines[i])) {
            items.push(`<li>${renderInline(rawLines[i].replace(/^\d+[.)]\s+/, ""))}</li>`);
            i += 1;
          }
          html.push(`<ol>${items.join("")}</ol>`);
          continue;
        }

        // Plain paragraph line(s): collect consecutive plain lines together.
        const paraLines = [];
        while (
          i < rawLines.length &&
          !/^(#{1,6})\s+/.test(rawLines[i]) &&
          !/^[-*]\s+/.test(rawLines[i]) &&
          !/^\d+[.)]\s+/.test(rawLines[i]) &&
          !(isTableRow(rawLines[i]) && i + 1 < rawLines.length && isTableSeparator(rawLines[i + 1]))
        ) {
          paraLines.push(rawLines[i]);
          i += 1;
        }
        if (paraLines.length) {
          html.push(`<p>${paraLines.map(renderInline).join("<br>")}</p>`);
        }
      }

      return html.join("");
    })
    .join("");
}

function addMessage(role, text) {
  emptyState.style.display = "none";
  const div = document.createElement("div");
  div.className = `msg ${role}`;

  if (role.startsWith("assistant")) {
    div.innerHTML = renderMarkdownLite(text);
  } else {
    // User's own input never needs HTML rendering — keep it as plain text.
    div.textContent = text;
  }

  messagesEl.appendChild(div);
  messagesEl.scrollTop = messagesEl.scrollHeight;
  return div;
}

function setAssistantContent(div, text) {
  div.innerHTML = renderMarkdownLite(text);
}

function addSources(sources) {
  if (!sources || !sources.length) return;
  const wrap = document.createElement("div");
  wrap.className = "sources";
  sources.forEach((s) => {
    const a = document.createElement("a");
    a.className = "source-chip";
    a.href = s.url;
    a.target = "_blank";
    a.rel = "noopener";
    a.title = s.title || s.url;
    a.textContent = (s.title || s.url).slice(0, 40);
    wrap.appendChild(a);
  });
  messagesEl.appendChild(wrap);
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

async function postChat(text, sessionId) {
  return fetch(`${API_BASE_URL}/api/chat`, {
    method: "POST",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({ message: text, session_id: sessionId }),
  });
}

async function sendMessage(text) {
  addMessage("user", text);
  const thinkingEl = addMessage("assistant thinking", STRINGS[lang].thinking);

  sendBtn.disabled = true;
  try {
    let res = await postChat(text, currentSessionId);

    // A 404 here means currentSessionId doesn't belong to this browser's
    // user id — most commonly a session_id saved in localStorage from
    // before per-user isolation existed (see chat_memory.py's 'legacy'
    // owner), or a session that was deleted from another tab. Either way,
    // the fix is the same: drop the stale id and start a fresh session
    // with the same message, instead of leaving the user stuck.
    if (res.status === 404 && currentSessionId) {
      currentSessionId = null;
      localStorage.removeItem("te_rag_session_id");
      res = await postChat(text, null);
    }

    if (!res.ok) throw new Error("bad response");
    const data = await res.json();

    currentSessionId = data.session_id;
    localStorage.setItem("te_rag_session_id", currentSessionId);

    thinkingEl.classList.remove("thinking");
    setAssistantContent(thinkingEl, data.answer);
    addSources(data.sources);
    refreshSessions();
  } catch (err) {
    thinkingEl.classList.remove("thinking");
    thinkingEl.textContent = STRINGS[lang].error;
  } finally {
    sendBtn.disabled = false;
  }
}

form.addEventListener("submit", (e) => {
  e.preventDefault();
  const text = input.value.trim();
  if (!text) return;
  input.value = "";
  input.style.height = "auto";
  sendMessage(text);
});

input.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    form.requestSubmit();
  }
});

input.addEventListener("input", () => {
  input.style.height = "auto";
  input.style.height = Math.min(input.scrollHeight, 140) + "px";
});

function clearChatView() {
  currentSessionId = null;
  localStorage.removeItem("te_rag_session_id");
  messagesEl.innerHTML = "";
  messagesEl.appendChild(emptyState);
  emptyState.style.display = "block";
  highlightActiveSession();
}

el("newChatBtn").addEventListener("click", () => {
  clearChatView();
  closeSidebar();
});

async function deleteSession(id, itemEl) {
  if (!confirm(STRINGS[lang].deleteConfirm)) return;
  try {
    const res = await fetch(`${API_BASE_URL}/api/sessions/${id}`, {
      method: "DELETE",
      headers: authHeaders(),
    });
    if (!res.ok) throw new Error("delete failed");
    itemEl.remove();
    if (id === currentSessionId) clearChatView();
  } catch (err) {
    /* if delete fails, just leave the item in place */
  }
}

async function refreshSessions() {
  try {
    const res = await fetch(`${API_BASE_URL}/api/sessions`, { headers: authHeaders() });
    const sessions = await res.json();
    sessionsList.innerHTML = "";
    sessions.forEach((s) => {
      const item = document.createElement("div");
      item.className = "session-item";
      item.dataset.id = s.id;

      const label = document.createElement("span");
      label.className = "session-label";
      label.textContent = s.title || s.id;
      label.addEventListener("click", () => loadSession(s.id));

      const del = document.createElement("button");
      del.className = "session-delete";
      del.type = "button";
      del.title = STRINGS[lang].deleteTitle;
      del.innerHTML = "&times;";
      del.addEventListener("click", (e) => {
        e.stopPropagation();
        deleteSession(s.id, item);
      });

      item.appendChild(label);
      item.appendChild(del);
      sessionsList.appendChild(item);
    });
    highlightActiveSession();
  } catch (err) {
    /* sessions list is a convenience, fail silently */
  }
}

function highlightActiveSession() {
  [...sessionsList.children].forEach((c) => {
    c.classList.toggle("active", c.dataset.id === currentSessionId);
  });
}

async function loadSession(id) {
  currentSessionId = id;
  localStorage.setItem("te_rag_session_id", id);
  closeSidebar();
  const res = await fetch(`${API_BASE_URL}/api/sessions/${id}/messages`, { headers: authHeaders() });
  const msgs = await res.json();

  messagesEl.innerHTML = "";
  if (!msgs.length) {
    messagesEl.appendChild(emptyState);
    emptyState.style.display = "block";
  } else {
    msgs.forEach((m) => {
      addMessage(m.role, m.content);
      if (m.role === "assistant" && m.retrieved_sources) {
        addSources(m.retrieved_sources);
      }
    });
  }
  highlightActiveSession();
}


try { applyLang(); } catch (err) { console.error("applyLang failed:", err); }
try { refreshSessions(); } catch (err) { console.error("refreshSessions failed:", err); }
try {
  const savedId = localStorage.getItem("te_rag_session_id");
  if (savedId) loadSession(savedId);
} catch (err) {
  console.error("loadSession failed:", err);
}
