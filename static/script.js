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

let lang = "ar";
let currentSessionId = null;

const el = (id) => document.getElementById(id);
const messagesEl = el("messages");
const emptyState = el("emptyState");
const form = el("composerForm");
const input = el("messageInput");
const sendBtn = el("sendBtn");
const sessionsList = el("sessionsList");

function applyLang() {
  const s = STRINGS[lang];
  el("headerTitle").textContent = s.headerTitle;
  el("headerSub").textContent = s.headerSub;
  el("emptyTitle").textContent = s.emptyTitle;
  el("emptySub").textContent = s.emptySub;
  input.placeholder = s.placeholder;
  el("newChatBtn").querySelector("span").textContent = s.newChat;
  el("sessionsLabel").textContent = s.sessionsLabel;
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

function renderMarkdownLite(text) {
  const blocks = text.trim().split(/\n\s*\n/);
  return blocks
    .map((block) => {
      const lines = block.split("\n").map((l) => l.trim()).filter(Boolean);
      if (!lines.length) return "";

      const isBullet = lines.every((l) => /^[-*]\s+/.test(l));
      const isNumbered = lines.every((l) => /^\d+[.)]\s+/.test(l));

      if (isBullet) {
        const items = lines.map((l) => `<li>${renderInline(l.replace(/^[-*]\s+/, ""))}</li>`).join("");
        return `<ul>${items}</ul>`;
      }
      if (isNumbered) {
        const items = lines.map((l) => `<li>${renderInline(l.replace(/^\d+[.)]\s+/, ""))}</li>`).join("");
        return `<ol>${items}</ol>`;
      }
      return `<p>${lines.map(renderInline).join("<br>")}</p>`;
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

async function sendMessage(text) {
  addMessage("user", text);
  const thinkingEl = addMessage("assistant thinking", STRINGS[lang].thinking);

  sendBtn.disabled = true;
  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: text, session_id: currentSessionId }),
    });
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

el("newChatBtn").addEventListener("click", clearChatView);

async function deleteSession(id, itemEl) {
  if (!confirm(STRINGS[lang].deleteConfirm)) return;
  try {
    const res = await fetch(`/api/sessions/${id}`, { method: "DELETE" });
    if (!res.ok) throw new Error("delete failed");
    itemEl.remove();
    if (id === currentSessionId) clearChatView();
  } catch (err) {
    /* if delete fails, just leave the item in place */
  }
}

async function refreshSessions() {
  try {
    const res = await fetch("/api/sessions");
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
  const res = await fetch(`/api/sessions/${id}/messages`);
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

// --- init ---
applyLang();
refreshSessions();
const savedId = localStorage.getItem("te_rag_session_id");
if (savedId) loadSession(savedId);
