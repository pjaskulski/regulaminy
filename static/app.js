const form = document.querySelector("#chat-form");
const textarea = document.querySelector("#message");
const messages = document.querySelector("#messages");
const modal = document.querySelector("#document-modal");
const modalTitle = document.querySelector("#document-title");
const modalPath = document.querySelector("#document-path");
const modalContent = document.querySelector("#document-content");
const modalClose = document.querySelector("#document-close");
const appBase = (window.APP_BASE || "").replace(/\/$/, "");

function appUrl(path) {
  return `${appBase}${path}`;
}

function addMessage(role, text) {
  const article = document.createElement("article");
  article.className = `message ${role}`;
  const content = document.createElement("div");
  content.className = "message-content";
  setMessageContent(content, text, role === "assistant");
  article.appendChild(content);
  messages.appendChild(article);
  messages.scrollTop = messages.scrollHeight;
  return article;
}

function addCopyButton(message) {
  if (message.querySelector(".copy-answer")) return;
  const copyButton = document.createElement("button");
  copyButton.className = "copy-answer";
  copyButton.type = "button";
  copyButton.title = "Kopiuj odpowiedź";
  copyButton.textContent = "Kopiuj";
  message.prepend(copyButton);
}

function setMessageContent(element, text, renderMarkdown) {
  element.dataset.plainText = text;
  if (renderMarkdown) {
    element.innerHTML = renderSimpleMarkdown(text);
    return;
  }
  element.textContent = text;
}

function renderSimpleMarkdown(markdown) {
  const lines = String(markdown).split(/\r?\n/);
  const html = [];
  let listType = null;
  let table = null;

  function closeList() {
    if (!listType) return;
    html.push(`</${listType}>`);
    listType = null;
  }

  function closeTable() {
    if (!table) return;
    html.push("</tbody></table>");
    table = null;
  }

  for (let index = 0; index < lines.length; index += 1) {
    const rawLine = lines[index];
    const line = rawLine.trimEnd();
    if (!line.trim()) {
      if (table && isTableRow(lines[nextNonEmptyIndex(lines, index + 1)] || "")) {
        continue;
      }
      closeList();
      closeTable();
      continue;
    }

    const nextIndex = nextNonEmptyIndex(lines, index + 1);
    const nextLine = lines[nextIndex] || "";
    if (!table && isTableHeader(line, nextLine)) {
      closeList();
      const headers = parseTableRow(line);
      const alignments = parseTableAlignment(nextLine);
      html.push(renderTableHeader(headers, alignments));
      table = { alignments };
      index = nextIndex;
      continue;
    }

    if (table && isTableRow(line)) {
      closeList();
      html.push(renderTableRow(parseTableRow(line), table.alignments));
      continue;
    }

    closeTable();

    const heading = /^(#{1,6})\s+(.+)$/.exec(line);
    if (heading) {
      closeList();
      const level = Math.min(heading[1].length + 2, 6);
      html.push(`<h${level}>${renderInlineMarkdown(heading[2])}</h${level}>`);
      continue;
    }

    const unordered = /^[-*]\s+(.+)$/.exec(line);
    if (unordered) {
      if (listType !== "ul") {
        closeList();
        html.push("<ul>");
        listType = "ul";
      }
      html.push(`<li>${renderInlineMarkdown(unordered[1])}</li>`);
      continue;
    }

    const ordered = /^\d+[.)]\s+(.+)$/.exec(line);
    if (ordered) {
      if (listType !== "ol") {
        closeList();
        html.push("<ol>");
        listType = "ol";
      }
      html.push(`<li>${renderInlineMarkdown(ordered[1])}</li>`);
      continue;
    }

    closeList();
    html.push(`<p>${renderInlineMarkdown(line)}</p>`);
  }

  closeList();
  closeTable();
  return html.join("");
}

function renderDocumentMarkdown(markdown, startLine, endLine) {
  const lines = String(markdown).split(/\r?\n/);
  const html = [];
  let listType = null;
  let table = null;

  function closeList() {
    if (!listType) return;
    html.push(`</${listType}>`);
    listType = null;
  }

  function closeTable() {
    if (!table) return;
    html.push("</tbody></table>");
    table = null;
  }

  function lineClass(lineNumber) {
    return startLine && endLine && lineNumber >= startLine && lineNumber <= endLine ? ' class="source-hit"' : "";
  }

  for (let index = 0; index < lines.length; index += 1) {
    const rawLine = lines[index];
    const lineNumber = index + 1;
    const line = rawLine.trimEnd();
    const className = lineClass(lineNumber);
    if (!line.trim()) {
      if (table && isTableRow(lines[nextNonEmptyIndex(lines, index + 1)] || "")) {
        continue;
      }
      closeList();
      closeTable();
      continue;
    }

    const nextIndex = nextNonEmptyIndex(lines, index + 1);
    const nextLine = lines[nextIndex] || "";
    if (!table && isTableHeader(line, nextLine)) {
      closeList();
      const headers = parseTableRow(line);
      const alignments = parseTableAlignment(nextLine);
      html.push(renderTableHeader(headers, alignments, className, lineNumber));
      table = { alignments };
      index = nextIndex;
      continue;
    }

    if (table && isTableRow(line)) {
      closeList();
      html.push(renderTableRow(parseTableRow(line), table.alignments, className, lineNumber));
      continue;
    }

    closeTable();

    const heading = /^(#{1,6})\s+(.+)$/.exec(line);
    if (heading) {
      closeList();
      const level = Math.min(heading[1].length + 2, 6);
      html.push(`<h${level}${className} data-line="${lineNumber}">${renderInlineMarkdown(heading[2])}</h${level}>`);
      continue;
    }

    const unordered = /^[-*]\s+(.+)$/.exec(line);
    if (unordered) {
      if (listType !== "ul") {
        closeList();
        html.push("<ul>");
        listType = "ul";
      }
      html.push(`<li${className} data-line="${lineNumber}">${renderInlineMarkdown(unordered[1])}</li>`);
      continue;
    }

    const ordered = /^\d+[.)]\s+(.+)$/.exec(line);
    if (ordered) {
      if (listType !== "ol") {
        closeList();
        html.push("<ol>");
        listType = "ol";
      }
      html.push(`<li${className} data-line="${lineNumber}">${renderInlineMarkdown(ordered[1])}</li>`);
      continue;
    }

    closeList();
    html.push(`<p${className} data-line="${lineNumber}">${renderInlineMarkdown(line)}</p>`);
  }

  closeList();
  closeTable();
  return html.join("");
}

function isTableRow(line) {
  return /^\s*\|.+\|\s*$/.test(line);
}

function nextNonEmptyIndex(lines, startIndex) {
  for (let index = startIndex; index < lines.length; index += 1) {
    if (String(lines[index]).trim()) {
      return index;
    }
  }
  return -1;
}

function isTableHeader(line, nextLine) {
  return isTableRow(line) && isTableRow(nextLine) && parseTableAlignment(nextLine).length > 0;
}

function parseTableRow(line) {
  return line.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map((cell) => cell.trim());
}

function parseTableAlignment(line) {
  const cells = parseTableRow(line);
  if (!cells.length || !cells.every((cell) => /^:?-{3,}:?$/.test(cell))) {
    return [];
  }
  return cells.map((cell) => {
    const left = cell.startsWith(":");
    const right = cell.endsWith(":");
    if (left && right) return "center";
    if (right) return "right";
    return "left";
  });
}

function renderTableHeader(cells, alignments, className = "", lineNumber = null) {
  const lineAttr = lineNumber ? ` data-line="${lineNumber}"` : "";
  const headers = cells.map((cell, index) => `<th style="text-align: ${alignments[index] || "left"}">${renderInlineMarkdown(cell)}</th>`).join("");
  return `<table${className}${lineAttr}><thead><tr>${headers}</tr></thead><tbody>`;
}

function renderTableRow(cells, alignments, className = "", lineNumber = null) {
  const lineAttr = lineNumber ? ` data-line="${lineNumber}"` : "";
  const columns = cells.map((cell, index) => `<td style="text-align: ${alignments[index] || "left"}">${renderInlineMarkdown(cell)}</td>`).join("");
  return `<tr${className}${lineAttr}>${columns}</tr>`;
}

function renderInlineMarkdown(text) {
  return escapeHtml(text)
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/\*([^*]+)\*/g, "<em>$1</em>");
}

function renderSources(container, items) {
  const existing = container.querySelector(".message-sources");
  if (existing) existing.remove();
  if (!items.length) return;

  const details = document.createElement("details");
  details.className = "message-sources";
  const summary = document.createElement("summary");
  summary.textContent = `Źródła (${items.length})`;
  details.appendChild(summary);

  const list = document.createElement("div");
  list.className = "source-list";
  items.forEach((item, index) => {
    const div = document.createElement("div");
    div.className = "source";
    div.innerHTML = `
      <strong>[${escapeHtml(item.source_id || `S${index + 1}`)}] ${escapeHtml(item.title)}</strong>
      <span>${escapeHtml(item.date)} · ${escapeHtml(item.heading)} · linie ${item.start_line}-${item.end_line}</span>
      <button class="source-link" type="button" data-document-path="${escapeHtml(item.path)}" data-start-line="${item.start_line}" data-end-line="${item.end_line}">${escapeHtml(item.path)}</button>
    `;
    list.appendChild(div);
  });
  details.appendChild(list);
  container.appendChild(details);
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

if (form && textarea && messages) {
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const message = textarea.value.trim();
    if (!message) return;
    textarea.value = "";
    addMessage("user", message);
    const pending = addMessage("assistant", "Szukam w dokumentach...");

    try {
      const response = await fetch(appUrl("/api/chat"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message }),
      });
      const data = await response.json();
      setMessageContent(pending.querySelector(".message-content"), data.answer || data.error || "Brak odpowiedzi.", true);
      addCopyButton(pending);
      renderSources(pending, data.sources || []);
    } catch (error) {
      setMessageContent(pending.querySelector(".message-content"), `Błąd połączenia: ${error}`, false);
      addCopyButton(pending);
    }
  });

  textarea.addEventListener("keydown", (event) => {
    if (event.key !== "Enter" || event.shiftKey) return;
    event.preventDefault();
    if (textarea.value.trim()) {
      form.requestSubmit();
    }
  });

  messages.addEventListener("click", async (event) => {
    const copyButton = event.target.closest(".copy-answer");
    if (copyButton) {
      await copyAnswer(copyButton);
      return;
    }

    const button = event.target.closest("[data-document-path]");
    if (!button) return;
    await openDocument(button.dataset.documentPath, Number(button.dataset.startLine), Number(button.dataset.endLine));
  });
}

document.addEventListener("click", async (event) => {
  const button = event.target.closest(".document-list-item[data-document-path]");
  if (!button) return;
  await openDocument(button.dataset.documentPath, Number(button.dataset.startLine), Number(button.dataset.endLine));
});

async function copyAnswer(button) {
  const message = button.closest(".message");
  const content = message.querySelector(".message-content");
  const text = content.dataset.plainText || content.textContent;
  try {
    await navigator.clipboard.writeText(text);
    showCopyState(button, "Skopiowano");
  } catch {
    fallbackCopy(text);
    showCopyState(button, "Skopiowano");
  }
}

function fallbackCopy(text) {
  const field = document.createElement("textarea");
  field.value = text;
  field.setAttribute("readonly", "");
  field.style.position = "fixed";
  field.style.left = "-9999px";
  document.body.appendChild(field);
  field.select();
  document.execCommand("copy");
  field.remove();
}

function showCopyState(button, label) {
  const original = button.textContent;
  button.textContent = label;
  button.disabled = true;
  window.setTimeout(() => {
    button.textContent = original;
    button.disabled = false;
  }, 1200);
}

async function openDocument(path, startLine, endLine) {
  showModal("Ładowanie dokumentu...", path, "");
  try {
    const response = await fetch(appUrl(`/api/document?path=${encodeURIComponent(path)}`));
    const data = await response.json();
    if (!response.ok) {
      showModal("Nie udało się otworzyć dokumentu", path, data.error || "Błąd pobierania dokumentu.");
      return;
    }
    showModal(data.title, data.path, data.content, startLine, endLine);
  } catch (error) {
    showModal("Nie udało się otworzyć dokumentu", path, `Błąd połączenia: ${error}`);
  }
}

function showModal(title, path, markdown, startLine, endLine) {
  modalTitle.textContent = title;
  modalPath.textContent = startLine && endLine ? `${path} · linie ${startLine}-${endLine}` : path;
  modalContent.innerHTML = renderDocumentMarkdown(markdown || "", startLine, endLine);
  modal.hidden = false;
  document.body.classList.add("modal-open");
  const firstHit = modalContent.querySelector(".source-hit");
  if (firstHit) {
    window.setTimeout(() => firstHit.scrollIntoView({ block: "center" }), 0);
  }
}

function closeModal() {
  modal.hidden = true;
  document.body.classList.remove("modal-open");
}

modalClose.addEventListener("click", closeModal);
modal.addEventListener("click", (event) => {
  if (event.target.matches("[data-close-modal]")) closeModal();
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !modal.hidden) closeModal();
});
