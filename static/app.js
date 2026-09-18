const WELCOME_CARDS = [
  {
    title: "支持哪些文件格式？",
    desc: "查看 RAG Agent 能索引的文档类型",
    question: "RAG Agent 支持哪些知识文件格式？",
  },
  {
    title: "知识库讲了什么？",
    desc: "概括 knowledge 目录中的文档内容",
    question: "请总结一下知识库文档的核心内容。",
  },
  {
    title: "大雄如何战胜强敌？",
    desc: "检验故事细节的检索能力",
    question: "大雄是如何击败黑暗赛亚人的？",
  },
  {
    title: "推荐的测试问题",
    desc: "示例文档给出的验证方法",
    question: "示例文档推荐用什么问题来测试 RAG Agent？",
  },
];

const EXT_BADGES = {
  ".md": ["MD", "ext-md"],
  ".txt": ["TXT", "ext-txt"],
  ".pdf": ["PDF", "ext-pdf"],
  ".docx": ["DOC", "ext-docx"],
};

const state = {
  providers: [],
  sessionId: createSessionId(),
  busy: false,
};

// Node 环境（单测）下无 DOM：跳过元素绑定，只保留纯函数供导入
const hasDocument = typeof document !== "undefined";

const els = hasDocument
  ? {
  providerSelect: document.querySelector("#providerSelect"),
  modelSelect: document.querySelector("#modelSelect"),
  providerState: document.querySelector("#providerState"),
  providerLabel: document.querySelector("#providerLabel"),
  fileCount: document.querySelector("#fileCount"),
  chunkCount: document.querySelector("#chunkCount"),
  knowledgePath: document.querySelector("#knowledgePath"),
  knowledgeList: document.querySelector("#knowledgeList"),
  refreshKnowledge: document.querySelector("#refreshKnowledge"),
  reindexButton: document.querySelector("#reindexButton"),
  uploadButton: document.querySelector("#uploadButton"),
  fileInput: document.querySelector("#fileInput"),
  clearButton: document.querySelector("#clearButton"),
  themeToggle: document.querySelector("#themeToggle"),
  sessionSelect: document.querySelector("#sessionSelect"),
  engineState: document.querySelector("#engineState"),
  chatLog: document.querySelector("#chatLog"),
  sourceList: document.querySelector("#sourceList"),
  sourcesCount: document.querySelector("#sourcesCount"),
  chatForm: document.querySelector("#chatForm"),
  questionInput: document.querySelector("#questionInput"),
  sendButton: document.querySelector("#sendButton"),
  dropOverlay: document.querySelector("#dropOverlay"),
} : {};

async function init() {
  bindEvents();
  initTheme();
  renderWelcome();

  try {
    await Promise.all([loadProviders(), loadKnowledge()]);
    await loadSessions();
  } catch (error) {
    addMessage("status", `静态预览模式：启动 web.py 后会自动读取模型、知识库和对话接口。`);
    renderOfflineState();
  }
}

function bindEvents() {
  els.providerSelect.addEventListener("change", () => {
    renderModels();
    renderProviderState();
  });

  els.refreshKnowledge.addEventListener("click", loadKnowledge);
  els.reindexButton.addEventListener("click", reindexKnowledge);
  els.clearButton.addEventListener("click", newSession);
  els.chatForm.addEventListener("submit", submitQuestion);
  els.themeToggle.addEventListener("click", toggleTheme);
  els.sessionSelect.addEventListener("change", () => {
    switchSession(els.sessionSelect.value);
  });

  els.uploadButton.addEventListener("click", () => els.fileInput.click());
  els.fileInput.addEventListener("change", () => {
    if (els.fileInput.files?.[0]) {
      uploadFile(els.fileInput.files[0]);
    }
    els.fileInput.value = "";
  });

  bindDragDrop();

  els.chatLog.addEventListener("click", (event) => {
    const citation = event.target.closest(".citation");
    if (citation) {
      highlightSource(citation.dataset.source, citation.dataset.chunk);
    }
  });

  els.sourceList.addEventListener("click", (event) => {
    const card = event.target.closest(".source-card");
    if (card) {
      card.classList.toggle("expanded");
    }
  });

  els.questionInput.addEventListener("keydown", (event) => {
    if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
      els.chatForm.requestSubmit();
    }
  });

  els.questionInput.addEventListener("input", () => {
    els.questionInput.style.height = "auto";
    els.questionInput.style.height = `${Math.min(190, els.questionInput.scrollHeight)}px`;
  });
}

function bindDragDrop() {
  let dragDepth = 0;

  window.addEventListener("dragenter", (event) => {
    if (!event.dataTransfer?.types?.includes("Files")) return;
    dragDepth += 1;
    els.dropOverlay.hidden = false;
  });
  window.addEventListener("dragleave", () => {
    dragDepth = Math.max(0, dragDepth - 1);
    if (dragDepth === 0) els.dropOverlay.hidden = true;
  });
  window.addEventListener("dragover", (event) => event.preventDefault());
  window.addEventListener("drop", (event) => {
    event.preventDefault();
    dragDepth = 0;
    els.dropOverlay.hidden = true;
    const file = event.dataTransfer?.files?.[0];
    if (file) uploadFile(file);
  });
}

function initTheme() {
  const saved = localStorage.getItem("rag-theme");
  const preferDark = window.matchMedia?.("(prefers-color-scheme: dark)").matches;
  document.documentElement.dataset.theme = saved || (preferDark ? "dark" : "light");
}

function toggleTheme() {
  const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
  document.documentElement.dataset.theme = next;
  localStorage.setItem("rag-theme", next);
}

async function loadProviders() {
  const data = await fetchJson("/api/providers");
  state.providers = data.providers || [];

  els.providerSelect.innerHTML = state.providers
    .map((provider) => {
      const selected = provider.name === data.default_provider ? "selected" : "";
      return `<option value="${escapeHtml(provider.name)}" ${selected}>${escapeHtml(provider.display_name)}</option>`;
    })
    .join("");

  renderModels();
  renderProviderState();
}

function renderModels() {
  const provider = currentProvider();
  const models = provider?.models || [];

  if (!models.length) {
    els.modelSelect.innerHTML = `<option value="">暂无可用模型</option>`;
    return;
  }

  els.modelSelect.innerHTML = models
    .map((model) => {
      const selected = model === provider.default_model ? "selected" : "";
      return `<option value="${escapeHtml(model)}" ${selected}>${escapeHtml(model)}</option>`;
    })
    .join("");
}

function renderProviderState() {
  const provider = currentProvider();
  const configured = Boolean(provider?.configured);

  els.providerState.classList.toggle("ready", configured);
  els.providerState.title = configured ? "API Key 已配置" : "API Key 未配置";
  els.providerLabel.textContent = provider
    ? configured
      ? `${provider.display_name} 已就绪`
      : `${provider.display_name} 需要配置 API Key`
    : "暂无模型配置";
}

async function loadKnowledge() {
  setPanelLoading(true);

  try {
    const [knowledge, status] = await Promise.all([fetchJson("/api/knowledge"), fetchJson("/api/status")]);
    const files = knowledge.files || [];

    els.fileCount.textContent = status.file_count ?? files.length;
    els.chunkCount.textContent = status.chunk_count ?? "-";
    els.knowledgePath.textContent = compactPath(status.knowledge_dir || "knowledge/");
    els.engineState.textContent = status.engine_loaded ? "索引已加载" : "索引待加载";
    els.engineState.classList.toggle("ready", Boolean(status.engine_loaded));

    renderKnowledgeFiles(files);
  } finally {
    setPanelLoading(false);
  }
}

function renderKnowledgeFiles(files) {
  if (!files.length) {
    els.knowledgeList.innerHTML = `<div class="empty">knowledge 目录中还没有可检索文档，可上传或拖入文件。</div>`;
    return;
  }

  els.knowledgeList.innerHTML = files
    .map((file) => {
      const modified = file.modified ? formatDate(file.modified) : "未知时间";
      const [label, badgeClass] = EXT_BADGES[file.extension] || ["FILE", "ext-txt"];
      return `<article class="file-row">
        <span class="file-badge ${badgeClass}">${escapeHtml(label)}</span>
        <div>
          <strong title="${escapeHtml(file.name)}">${escapeHtml(file.name)}</strong>
          <span>${formatBytes(file.size)} · ${modified}</span>
        </div>
        <button class="file-del" type="button" data-name="${escapeHtml(file.name)}" title="删除该文件及其索引" aria-label="删除 ${escapeHtml(file.name)}">
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <path d="M3 6h18M8 6V4h8v2M6 6l1 14h10l1-14" />
          </svg>
        </button>
      </article>`;
    })
    .join("");

  els.knowledgeList.querySelectorAll(".file-del").forEach((button) => {
    button.addEventListener("click", (event) => {
      event.stopPropagation();
      deleteFile(button.dataset.name);
    });
  });
}

async function uploadFile(file) {
  const ext = `.${file.name.split(".").pop()?.toLowerCase()}`;
  if (![".md", ".txt", ".pdf", ".docx"].includes(ext)) {
    addMessage("error", `不支持的文件类型：${ext}，仅支持 .md / .txt / .pdf / .docx`);
    return;
  }
  if (file.size > 20 * 1024 * 1024) {
    addMessage("error", "文件过大，上限 20MB。");
    return;
  }

  setBusy(true);
  addMessage("status", `正在上传并索引 ${file.name} ...`);

  try {
    const response = await fetch("/api/upload", {
      method: "POST",
      headers: { "X-Filename": encodeURIComponent(file.name) },
      body: file,
    });
    const data = await response.json();
    if (!response.ok || !data.ok) {
      throw new Error(data.error || `上传失败：${response.status}`);
    }
    addMessage("status", `已入库 ${data.file}（${data.status.chunk_count} 个片段）。`);
    await loadKnowledge();
  } catch (error) {
    addMessage("error", `上传失败：${error.message}`);
  } finally {
    setBusy(false);
  }
}

async function deleteFile(name) {
  if (!window.confirm(`确定删除「${name}」及其索引片段？此操作不可恢复。`)) {
    return;
  }

  setBusy(true);
  try {
    const data = await fetchJson("/api/knowledge/delete", {
      method: "POST",
      body: JSON.stringify({ name }),
    });
    if (!data.ok) {
      throw new Error(data.error || "删除失败");
    }
    addMessage("status", `已删除 ${name}（清理 ${data.removed_chunks} 个片段）。`);
    await loadKnowledge();
  } catch (error) {
    addMessage("error", `删除失败：${error.message}`);
  } finally {
    setBusy(false);
  }
}

async function loadSessions() {
  try {
    const data = await fetchJson("/api/sessions");
    const sessions = data.sessions || [];
    const known = new Set(sessions.map((s) => s.session_id));

    const options = [`<option value="">当前对话（新）</option>`];
    for (const session of sessions) {
      const isCurrent = session.session_id === state.sessionId;
      const label = isCurrent ? `▸ ${session.preview || "当前会话"}` : session.preview || "未命名会话";
      options.push(
        `<option value="${escapeHtml(session.session_id)}" ${isCurrent ? "selected" : ""}>${escapeHtml(label)}</option>`
      );
    }

    els.sessionSelect.innerHTML = options.join("");
    if (!known.has(state.sessionId) && state.sessionId) {
      // 当前内存中的会话尚未落库（还没有完成过一次问答），保持"当前对话"
      els.sessionSelect.value = "";
    }
  } catch {
    els.sessionSelect.innerHTML = `<option value="">历史会话不可用</option>`;
  }
}

async function switchSession(sessionId) {
  if (!sessionId || sessionId === state.sessionId) {
    return;
  }

  try {
    const data = await fetchJson(`/api/sessions/${encodeURIComponent(sessionId)}/messages`);
    state.sessionId = sessionId;
    els.chatLog.innerHTML = "";
    chatInner();
    renderSources([]);

    const messages = data.messages || [];
    if (!messages.length) {
      renderWelcome("该会话没有历史消息。");
      return;
    }

    for (const message of messages) {
      const node = addMessage(message.role === "user" ? "user" : "assistant", "");
      if (message.role === "user") {
        node.textContent = message.content;
      } else {
        node.innerHTML = renderMarkdown(message.content);
      }
    }
    scrollChatToBottom();
  } catch (error) {
    addMessage("error", `加载会话失败：${error.message}`);
    els.sessionSelect.value = "";
  }
}

async function newSession() {
  try {
    await fetchJson("/api/session/clear", {
      method: "POST",
      body: JSON.stringify({ session_id: state.sessionId }),
    });
  } catch {
    // 清理本地界面不依赖后端成功。
  }

  state.sessionId = createSessionId();
  els.chatLog.innerHTML = "";
  chatInner();
  renderSources([]);
  renderWelcome("新的对话已开始。");
  await loadSessions();
  els.sessionSelect.value = "";
}

async function reindexKnowledge() {
  setBusy(true);
  addMessage("status", "正在重建索引，首次加载模型可能需要一点时间。");

  try {
    const data = await fetchJson("/api/reindex", {
      method: "POST",
      body: JSON.stringify({ force: true }),
    });

    if (!data.ok) {
      throw new Error(data.error || "重建失败");
    }

    addMessage("status", `索引已更新：${data.indexed_chunks} 个片段。`);
    await loadKnowledge();
  } catch (error) {
    addMessage("error", `重建索引失败：${error.message}`);
  } finally {
    setBusy(false);
  }
}

async function submitQuestion(event) {
  event.preventDefault();
  const question = els.questionInput.value.trim();

  if (!question || state.busy) {
    return;
  }

  removeWelcome();
  addMessage("user", question);
  els.questionInput.value = "";
  els.questionInput.style.height = "";
  setBusy(true);

  const answerNode = addMessage("assistant", "");
  answerNode.innerHTML = `<span class="dots"><i></i><i></i><i></i></span>`;

  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        question,
        provider: els.providerSelect.value,
        model: els.modelSelect.value,
        session_id: state.sessionId,
      }),
    });

    if (!response.ok || !response.body) {
      throw new Error(`请求失败：${response.status}`);
    }

    let hasToken = false;
    let answerText = "";

    await readNdjson(response.body, (eventData) => {
      if (eventData.event === "status" && !hasToken) {
        answerNode.textContent = eventData.message;
      }

      if (eventData.event === "sources") {
        renderSources(eventData.sources || []);
        answerNode.textContent = "";
      }

      if (eventData.event === "token") {
        if (!hasToken) {
          hasToken = true;
          answerNode.classList.add("streaming");
          answerNode.textContent = "";
        }
        answerText += eventData.token;
        answerNode.innerHTML = renderStreamingMarkdown(answerText);
        scrollChatToBottom();
      }

      if (eventData.event === "done") {
        answerNode.classList.remove("streaming");
        state.sessionId = eventData.session_id || state.sessionId;
        if (hasToken) {
          answerNode.innerHTML = renderMarkdown(answerText);
        } else if (eventData.answer && eventData.answer.trim()) {
          answerNode.textContent = eventData.answer;
        }
        loadKnowledge().catch(() => {});
        loadSessions().catch(() => {});
      }

      if (eventData.event === "error") {
        answerNode.classList.remove("streaming");
        answerNode.classList.add("error");
        answerNode.textContent = `出错了：${eventData.message}`;
      }
    });

    answerNode.classList.remove("streaming");
  } catch (error) {
    answerNode.classList.remove("streaming");
    answerNode.classList.add("error");
    answerNode.textContent = `出错了：${error.message}`;
  } finally {
    setBusy(false);
  }
}

async function readNdjson(stream, onEvent) {
  const reader = stream.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";

    for (const line of lines) {
      if (line.trim()) {
        onEvent(JSON.parse(line));
      }
    }
  }

  if (buffer.trim()) {
    onEvent(JSON.parse(buffer));
  }
}

function renderSources(sources) {
  els.sourcesCount.textContent = sources.length ? `${sources.length} 个片段` : "等待回答";

  if (!sources.length) {
    els.sourceList.className = "source-list empty";
    els.sourceList.innerHTML = `
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
        <path d="M14 2v6h6M9 13h6M9 17h4" />
      </svg>
      <span>回答后会显示检索到的文档片段。</span>`;
    return;
  }

  els.sourceList.className = "source-list";
  els.sourceList.innerHTML = sources
    .map((source, index) => {
      return `<article class="source-card" data-source="${escapeHtml(source.source)}" data-chunk="${escapeHtml(source.chunk_index)}" title="点击展开/收起全文">
        <header>
          <span class="source-num">${index + 1}</span>
          <strong title="${escapeHtml(source.source)}">${escapeHtml(source.source)}</strong>
          <span class="source-chip">片段 ${escapeHtml(source.chunk_index)}</span>
        </header>
        <p>${escapeHtml(source.text)}</p>
        <span class="expand-hint">点击查看全文</span>
      </article>`;
    })
    .join("");
}

function highlightSource(source, chunk) {
  const card = [...els.sourceList.querySelectorAll(".source-card")].find(
    (item) => item.dataset.source === source && item.dataset.chunk === String(chunk)
  );
  if (!card) {
    return;
  }

  card.classList.remove("highlight");
  void card.offsetWidth;
  card.classList.add("highlight");
  card.scrollIntoView({ behavior: "smooth", block: "nearest" });
  window.setTimeout(() => card.classList.remove("highlight"), 2400);
}

// 匹配 [来源: file.md - 片段 3] / [来源: file.md - 第3段] 两种写法
const CITATION_RE = /\[来源[:：]\s*([^\][\n]+?)\s*[-–—]\s*(?:片段\s*|第\s*)?(\d+)(?:\s*段|\s*个?片段)?\s*\]/g;

function renderMarkdown(raw) {
  let text = escapeHtml(raw);

  const codeBlocks = [];
  text = text.replace(/```[a-zA-Z0-9_-]*\n?([\s\S]*?)```/g, (_, code) => {
    codeBlocks.push(`<pre><code>${code.replace(/\n$/, "")}</code></pre>`);
    return `\u0000${codeBlocks.length - 1}\u0000`;
  });

  const out = [];
  let paragraph = [];
  let list = null;

  const flushParagraph = () => {
    if (paragraph.length) {
      out.push(`<p>${paragraph.join("<br>")}</p>`);
      paragraph = [];
    }
  };
  const flushList = () => {
    if (list) {
      out.push(`</${list}>`);
      list = null;
    }
  };

  for (const line of text.split("\n")) {
    const trimmed = line.trim();
    if (!trimmed) {
      flushParagraph();
      flushList();
      continue;
    }

    if (/^\u0000\d+\u0000$/.test(trimmed)) {
      flushParagraph();
      flushList();
      out.push(trimmed);
      continue;
    }

    const heading = trimmed.match(/^(#{1,4})\s+(.+)$/);
    if (heading) {
      flushParagraph();
      flushList();
      const level = Math.min(heading[1].length + 1, 5);
      out.push(`<h${level}>${inlineMarkdown(heading[2])}</h${level}>`);
      continue;
    }

    const unordered = trimmed.match(/^[-*•]\s+(.+)$/);
    if (unordered) {
      flushParagraph();
      if (list !== "ul") {
        flushList();
        out.push("<ul>");
        list = "ul";
      }
      out.push(`<li>${inlineMarkdown(unordered[1])}</li>`);
      continue;
    }

    const ordered = trimmed.match(/^\d+(?:[.)]\s+|、\s*)(.+)$/);
    if (ordered) {
      flushParagraph();
      if (list !== "ol") {
        flushList();
        out.push("<ol>");
        list = "ol";
      }
      out.push(`<li>${inlineMarkdown(ordered[1])}</li>`);
      continue;
    }

    const quote = trimmed.match(/^&gt;\s?(.*)$/);
    if (quote) {
      flushParagraph();
      flushList();
      out.push(`<blockquote>${inlineMarkdown(quote[1])}</blockquote>`);
      continue;
    }

    if (/^(-{3,}|\*{3,})$/.test(trimmed)) {
      flushParagraph();
      flushList();
      out.push("<hr>");
      continue;
    }

    flushList();
    paragraph.push(inlineMarkdown(trimmed));
  }
  flushParagraph();
  flushList();

  return out.join("").replace(/\u0000(\d+)\u0000/g, (_, index) => codeBlocks[Number(index)]);
}

function inlineMarkdown(text) {
  return text
    .replace(CITATION_RE, (_, source, chunk) => {
      const name = source.trim();
      return `<button type="button" class="citation" title="${name} · 片段 ${chunk}" data-source="${name}" data-chunk="${chunk}">来源: ${shortenName(name)} · 片段 ${chunk}</button>`;
    })
    .replace(/`([^`\n]+)`/g, "<code>$1</code>")
    .replace(
      /\[([^\]\n]+)\]\(((?:https?:|mailto:)[^)\s]+)\)/g,
      '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>'
    )
    .replace(/\*\*([^*\n]+)\*\*/g, "<strong>$1</strong>")
    .replace(/(^|[^*])\*([^*\n]+)\*(?!\*)/g, "$1<em>$2</em>");
}

// 文件名过长时中间截断显示；输入已是转义后的文本，含实体（&...;）时不截断以免切坏实体
function shortenName(name, max = 30) {
  if (name.length <= max || name.includes("&")) {
    return name;
  }
  return `${name.slice(0, 16)}…${name.slice(-12)}`;
}

function renderStreamingMarkdown(raw) {
  const fenceCount = (raw.match(/```/g) || []).length;
  const holder = document.createElement("div");
  holder.innerHTML = renderMarkdown(fenceCount % 2 === 1 ? `${raw}\n\`\`\`` : raw);

  let target = holder;
  while (target.lastElementChild && !["PRE", "UL", "OL", "HR"].includes(target.lastElementChild.tagName)) {
    target = target.lastElementChild;
  }

  const caret = document.createElement("span");
  caret.className = "caret";
  target.appendChild(caret);
  return holder.innerHTML;
}

function chatInner() {
  let inner = els.chatLog.querySelector(".chat-inner");
  if (!inner) {
    inner = document.createElement("div");
    inner.className = "chat-inner";
    els.chatLog.appendChild(inner);
  }
  return inner;
}

function addMessage(role, text) {
  const node = document.createElement("div");
  node.className = `message ${role}`;
  node.textContent = text;
  chatInner().appendChild(node);
  scrollChatToBottom();
  return node;
}

function renderWelcome(subtitle = "基于 knowledge 目录中的本地文档回答问题，回答附带可追溯的引用来源。") {
  const welcome = document.createElement("div");
  welcome.className = "welcome";
  welcome.innerHTML = `
    <div class="welcome-mark" aria-hidden="true">
      <svg viewBox="0 0 24 24">
        <path d="M12 3l2.1 5.4L19.5 10.5l-5.4 2.1L12 18l-2.1-5.4L4.5 10.5l5.4-2.1z" />
      </svg>
    </div>
    <h3>有什么可以帮你？</h3>
    <p>${escapeHtml(subtitle)}</p>
    <div class="welcome-cards">
      ${WELCOME_CARDS.map(
        (card) => `
        <button type="button" data-question="${escapeHtml(card.question)}">
          <strong>${escapeHtml(card.title)}</strong>
          <span>${escapeHtml(card.desc)}</span>
        </button>`
      ).join("")}
    </div>`;

  welcome.querySelectorAll("[data-question]").forEach((button) => {
    button.addEventListener("click", () => {
      els.questionInput.value = button.dataset.question || "";
      els.chatForm.requestSubmit();
    });
  });

  chatInner().appendChild(welcome);
}

function removeWelcome() {
  els.chatLog.querySelector(".welcome")?.remove();
}

function renderOfflineState() {
  els.providerSelect.innerHTML = `<option value="">接口未连接</option>`;
  els.modelSelect.innerHTML = `<option value="">接口未连接</option>`;
  els.providerLabel.textContent = "启动 web.py 后可读取模型配置";
  els.providerState.classList.remove("ready");
  els.engineState.textContent = "接口未连接";
  els.engineState.classList.remove("ready");
  els.knowledgeList.innerHTML = `<div class="empty">暂时无法读取知识库状态。</div>`;
}

function setBusy(busy) {
  state.busy = busy;
  els.sendButton.disabled = busy;
  els.reindexButton.disabled = busy;
  els.refreshKnowledge.disabled = busy;
  els.questionInput.disabled = busy;
}

function setPanelLoading(loading) {
  els.refreshKnowledge.disabled = loading || state.busy;
  if (loading) {
    els.knowledgePath.textContent = "正在刷新";
  }
}

function currentProvider() {
  return state.providers.find((provider) => provider.name === els.providerSelect.value);
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  const data = await response.json();

  if (!response.ok) {
    throw new Error(data.error || `请求失败：${response.status}`);
  }

  return data;
}

function scrollChatToBottom() {
  els.chatLog.scrollTop = els.chatLog.scrollHeight;
}

function createSessionId() {
  if (globalThis.crypto?.randomUUID) {
    return crypto.randomUUID();
  }
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function compactPath(path) {
  const parts = String(path).split(/[\\/]+/).filter(Boolean);
  return parts.length > 2 ? `${parts.at(-2)}/${parts.at(-1)}` : String(path);
}

function formatBytes(bytes = 0) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function formatDate(timestamp) {
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(timestamp * 1000));
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

export { escapeHtml, shortenName, inlineMarkdown, renderMarkdown, renderStreamingMarkdown, CITATION_RE };

if (hasDocument) {
  init();
}
