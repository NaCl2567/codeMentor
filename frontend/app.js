const state = {
  mock: true,
  userId: "demo_user",
  apiBase: "http://127.0.0.1:8000",
};

const els = {
  chatList: document.querySelector("#chatList"),
  chatForm: document.querySelector("#chatForm"),
  messageInput: document.querySelector("#messageInput"),
  userIdInput: document.querySelector("#userIdInput"),
  mockToggle: document.querySelector("#mockToggle"),
  clearBtn: document.querySelector("#clearBtn"),
  statusPill: document.querySelector("#statusPill"),
  intentView: document.querySelector("#intentView"),
  exerciseView: document.querySelector("#exerciseView"),
  reviewView: document.querySelector("#reviewView"),
  pathView: document.querySelector("#pathView"),
  chatItemTpl: document.querySelector("#chatItemTpl"),
};

function nowTime() {
  return new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function escapeHtml(str) {
  return str
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function renderMarkdown(md) {
  if (!md) return "";

  const codeBlocks = [];
  let text = md.replace(/```(\w+)?\n([\s\S]*?)```/g, (_, lang = "", code = "") => {
    const idx = codeBlocks.length;
    codeBlocks.push(
      `<pre class="md-pre"><code class="md-code ${escapeHtml(lang)}">${escapeHtml(code.trimEnd())}</code></pre>`,
    );
    return `@@CODEBLOCK_${idx}@@`;
  });

  text = escapeHtml(text);

  text = text
    .replace(/^###\s+(.+)$/gm, "<h4>$1</h4>")
    .replace(/^##\s+(.+)$/gm, "<h3>$1</h3>")
    .replace(/^#\s+(.+)$/gm, "<h2>$1</h2>")
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/^\-\s+(.+)$/gm, "<li>$1</li>");

  text = text.replace(/(?:<li>[\s\S]*?<\/li>\n?)+/g, (block) => `<ul>${block}</ul>`);
  text = text.replace(/\n{2,}/g, "</p><p>");
  text = `<p>${text.replace(/\n/g, "<br/>")}</p>`;

  text = text.replace(/@@CODEBLOCK_(\d+)@@/g, (_, i) => codeBlocks[Number(i)] || "");
  return text;
}

function setStatus(text) {
  els.statusPill.textContent = text;
}

function addChat(role, text) {
  const node = els.chatItemTpl.content.firstElementChild.cloneNode(true);
  node.classList.add(role);
  node.querySelector(".role").textContent = role === "user" ? "你" : "导师主控";
  node.querySelector(".bubble").textContent = text;
  node.querySelector(".time").textContent = nowTime();
  els.chatList.appendChild(node);
  els.chatList.scrollTop = els.chatList.scrollHeight;
}

function classifyIntent(message) {
  const text = message.toLowerCase();
  if (text.includes("review") || text.includes("审查") || text.includes("代码") || text.includes("```")) {
    return "submit_code";
  }
  if (text.includes("路径") || text.includes("学习计划") || text.includes("roadmap")) {
    return "learning_path";
  }
  if (text.includes("练习") || text.includes("来一题") || text.includes("题")) {
    return "request_exercise";
  }
  return "chat";
}

function mockResponse(message) {
  const intent = classifyIntent(message);
  const data = { intent, params: {} };
  if (intent === "request_exercise") {
    data.params = { language: "Python", difficulty: "基础", topic: "列表与循环" };
  }
  if (intent === "submit_code") {
    data.params = { language: "Python", problem_description: "检查循环逻辑" };
  }
  if (intent === "learning_path") {
    data.params = { goal: "Python 工程化" };
  }

  let reply = "我们继续。你也可以让我出题、review 代码、或者规划路径。";
  let exercise = "";
  let review = "";
  let path = "";

  if (intent === "request_exercise") {
    reply = "已为你生成一题基础练习，先做做看，做完我给你 review。";
    exercise = [
      "题目：实现 `dedupe_keep_order(nums)`",
      "要求：去重并保持原顺序，返回新列表。",
      "示例：输入 [1,2,2,3,1] -> 输出 [1,2,3]",
      "起始代码：",
      "def dedupe_keep_order(nums):",
      "    # TODO",
      "    pass",
    ].join("\n");
  }

  if (intent === "submit_code") {
    reply = "我看完你的代码了，已整理成结构化审查建议。";
    review = [
      "评分：7.5 / 10",
      "严重问题：边界条件遗漏（空列表未处理）",
      "建议：",
      "- 增加空输入保护",
      "- 用 set 做 visited 降低查找复杂度",
      "- 补 3 个边界测试用例",
    ].join("\n");
  }

  if (intent === "learning_path") {
    reply = "我先给你一个 12 周路线图，如果你同意再细化每周任务。";
    path = [
      "Stage 1 (2周): Python 语法与函数式思维",
      "Stage 2 (3周): 数据结构与复杂度",
      "Stage 3 (3周): Web 后端实践（FastAPI）",
      "Stage 4 (2周): 测试与重构",
      "Stage 5 (2周): 作品集项目 + 复盘",
    ].join("\n");
  }

  return { reply, intent: data.intent, params: data.params, exercise, review, path };
}

async function backendResponse(message) {
  const res = await fetch(`${state.apiBase}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ user_id: state.userId, message }),
  });
  if (!res.ok) {
    throw new Error(`HTTP ${res.status}`);
  }
  const data = await res.json();
  return {
    reply: data.response || "(empty response)",
    intent: data.intent || "unknown",
    params: data.params || {},
    exercise: data.exercise_markdown || "",
    review: data.review_markdown || "",
    path: data.path_markdown || "",
  };
}

function renderPanels(result) {
  els.intentView.textContent = JSON.stringify({ intent: result.intent, params: result.params }, null, 2);
  clearDownstreamByIntent(result.intent);

  // Same intent should always overwrite its own panel;
  // fallback text avoids stale content when backend omits detail fields.
  if (result.intent === "request_exercise") {
    els.exerciseView.innerHTML = renderMarkdown(result.exercise || "本次未返回练习详情。");
    return;
  }
  if (result.intent === "submit_code") {
    els.reviewView.innerHTML = renderMarkdown(result.review || "本次未返回审查详情。");
    return;
  }
  if (result.intent === "learning_path") {
    els.pathView.innerHTML = renderMarkdown(result.path || "本次未返回路径详情。");
    return;
  }

  // chat/unknown: only update panels when payload includes explicit content
  if (result.exercise) els.exerciseView.innerHTML = renderMarkdown(result.exercise);
  if (result.review) els.reviewView.innerHTML = renderMarkdown(result.review);
  if (result.path) els.pathView.innerHTML = renderMarkdown(result.path);
}

function clearDownstreamByIntent(intent) {
  // Workflow: request_exercise -> submit_code -> learning_path
  // Changing an earlier stage invalidates downstream results.
  if (intent === "request_exercise") {
    els.reviewView.innerHTML = "";
    els.pathView.innerHTML = "";
    return;
  }
  if (intent === "submit_code") {
    els.pathView.innerHTML = "";
  }
}

els.chatForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const message = els.messageInput.value.trim();
  if (!message) return;

  state.userId = els.userIdInput.value.trim() || "demo_user";
  addChat("user", message);
  els.messageInput.value = "";

  try {
    setStatus("Thinking...");
    const result = state.mock ? mockResponse(message) : await backendResponse(message);
    addChat("assistant", result.reply);
    renderPanels(result);
    setStatus("Done");
  } catch (err) {
    addChat("assistant", `请求失败: ${err.message}`);
    setStatus("Error");
  }
});

els.mockToggle.addEventListener("change", (e) => {
  state.mock = e.target.checked;
  setStatus(state.mock ? "Mock Ready" : "API Ready");
});

els.clearBtn.addEventListener("click", () => {
  els.chatList.innerHTML = "";
  els.intentView.textContent = "";
  els.exerciseView.innerHTML = "";
  els.reviewView.innerHTML = "";
  els.pathView.innerHTML = "";
  setStatus(state.mock ? "Mock Ready" : "API Ready");
});

addChat("assistant", "欢迎来到 Code Tutor Studio。你可以让我出题、审查代码、或规划学习路径。");
setStatus("Mock Ready");
