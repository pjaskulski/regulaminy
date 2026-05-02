const form = document.querySelector("#chat-form");
const textarea = document.querySelector("#message");
const messages = document.querySelector("#messages");
const modal = document.querySelector("#document-modal");
const modalTitle = document.querySelector("#document-title");
const modalPath = document.querySelector("#document-path");
const modalContent = document.querySelector("#document-content");
const modalClose = document.querySelector("#document-close");
const documentSearch = document.querySelector("#document-search");
const documentSearchCount = document.querySelector("#document-search-count");
const documentSearchPrev = document.querySelector("#document-search-prev");
const documentSearchNext = document.querySelector("#document-search-next");
const examplesModal = document.querySelector("#examples-modal");
const examplesOpen = document.querySelector("#examples-open");
const examplesClose = document.querySelector("#examples-close");
const infoModal = document.querySelector("#info-modal");
const infoOpen = document.querySelector("#info-open");
const infoClose = document.querySelector("#info-close");
const documentsSearchForm = document.querySelector("#documents-search-form");
const documentsSearchQuery = document.querySelector("#documents-search-query");
const documentsSearchClear = document.querySelector("#documents-search-clear");
const documentsSearchStatus = document.querySelector("#documents-search-status");
const documentsSearchResults = document.querySelector("#documents-search-results");
const appBase = (window.APP_BASE || "").replace(/\/$/, "");
let documentSearchHits = [];
let documentSearchIndex = -1;

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

function highlightText(value, query) {
  const text = String(value);
  const needle = query.trim();
  if (!needle) return escapeHtml(text);

  const loweredText = text.toLocaleLowerCase("pl");
  const loweredNeedle = needle.toLocaleLowerCase("pl");
  let cursor = 0;
  let index = loweredText.indexOf(loweredNeedle, cursor);
  if (index === -1) return escapeHtml(text);

  const parts = [];
  while (index !== -1) {
    if (index > cursor) {
      parts.push(escapeHtml(text.slice(cursor, index)));
    }
    parts.push(`<mark class="documents-search-hit">${escapeHtml(text.slice(index, index + needle.length))}</mark>`);
    cursor = index + needle.length;
    index = loweredText.indexOf(loweredNeedle, cursor);
  }
  if (cursor < text.length) {
    parts.push(escapeHtml(text.slice(cursor)));
  }
  return parts.join("");
}

function resetDocumentSearch() {
  documentSearchHits = [];
  documentSearchIndex = -1;
  if (documentSearch) {
    documentSearch.value = "";
  }
  updateDocumentSearchControls();
}

function clearDocumentSearchHighlights() {
  const marks = Array.from(modalContent.querySelectorAll("mark.document-search-hit"));
  marks.forEach((mark) => {
    mark.replaceWith(document.createTextNode(mark.textContent || ""));
  });
  modalContent.normalize();
}

function updateDocumentSearchControls() {
  if (documentSearchCount) {
    if (!documentSearchHits.length) {
      documentSearchCount.textContent = documentSearch && documentSearch.value.trim() ? "0 wyników" : "";
    } else {
      documentSearchCount.textContent = `${documentSearchIndex + 1}/${documentSearchHits.length}`;
    }
  }
  const disabled = documentSearchHits.length === 0;
  if (documentSearchPrev) documentSearchPrev.disabled = disabled;
  if (documentSearchNext) documentSearchNext.disabled = disabled;
}

function activateDocumentSearchHit(index) {
  if (!documentSearchHits.length) {
    documentSearchIndex = -1;
    updateDocumentSearchControls();
    return;
  }
  documentSearchHits.forEach((hit) => hit.classList.remove("active"));
  documentSearchIndex = (index + documentSearchHits.length) % documentSearchHits.length;
  const hit = documentSearchHits[documentSearchIndex];
  hit.classList.add("active");
  hit.scrollIntoView({ block: "center" });
  updateDocumentSearchControls();
}

function highlightDocumentSearch(query) {
  clearDocumentSearchHighlights();
  documentSearchHits = [];
  documentSearchIndex = -1;
  const needle = query.trim();
  if (!needle) {
    updateDocumentSearchControls();
    return;
  }

  const textNodes = [];
  const walker = document.createTreeWalker(modalContent, NodeFilter.SHOW_TEXT, {
    acceptNode(node) {
      return node.nodeValue.trim() ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT;
    },
  });
  while (walker.nextNode()) {
    textNodes.push(walker.currentNode);
  }

  const loweredNeedle = needle.toLocaleLowerCase("pl");
  textNodes.forEach((node) => {
    const text = node.nodeValue;
    const loweredText = text.toLocaleLowerCase("pl");
    let cursor = 0;
    let index = loweredText.indexOf(loweredNeedle, cursor);
    if (index === -1) return;

    const fragment = document.createDocumentFragment();
    while (index !== -1) {
      if (index > cursor) {
        fragment.appendChild(document.createTextNode(text.slice(cursor, index)));
      }
      const mark = document.createElement("mark");
      mark.className = "document-search-hit";
      mark.textContent = text.slice(index, index + needle.length);
      fragment.appendChild(mark);
      documentSearchHits.push(mark);
      cursor = index + needle.length;
      index = loweredText.indexOf(loweredNeedle, cursor);
    }
    if (cursor < text.length) {
      fragment.appendChild(document.createTextNode(text.slice(cursor)));
    }
    node.replaceWith(fragment);
  });

  activateDocumentSearchHit(0);
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

function setDocumentsSearchStatus(text) {
  if (documentsSearchStatus) {
    documentsSearchStatus.textContent = text;
  }
}

function clearDocumentsSearch() {
  if (documentsSearchQuery) {
    documentsSearchQuery.value = "";
    documentsSearchQuery.focus();
  }
  if (documentsSearchResults) {
    documentsSearchResults.innerHTML = "";
  }
  setDocumentsSearchStatus("Wpisz szukaną frazę i uruchom wyszukiwanie.");
}

function renderDocumentsSearchResults(items, query) {
  if (!documentsSearchResults) return;
  documentsSearchResults.innerHTML = "";
  items.forEach((item) => {
    const button = document.createElement("button");
    button.className = "document-list-item documents-search-result";
    button.type = "button";
    button.dataset.documentPath = item.path;
    button.dataset.startLine = item.start_line;
    button.dataset.endLine = item.end_line;
    button.innerHTML = `
      <span class="document-list-title">${escapeHtml(item.path.replace(/^md\//, ""))}</span>
      <span class="document-list-meta">
        ${escapeHtml(item.title)} · ${escapeHtml(item.date)} · ${escapeHtml(item.kind)}${item.is_change ? " · zmiana/aneks/uchylenie" : ""} · trafienia: ${item.match_count}
      </span>
      <span class="documents-search-snippet">${highlightText(item.snippet, query)}</span>
      <span class="document-list-path">${escapeHtml(item.path)} · linia ${item.start_line}</span>
    `;
    documentsSearchResults.appendChild(button);
  });
}

if (documentsSearchForm && documentsSearchQuery && documentsSearchClear) {
  documentsSearchForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const query = documentsSearchQuery.value.trim();
    if (!query) {
      clearDocumentsSearch();
      return;
    }

    setDocumentsSearchStatus("Szukam w treści dokumentów...");
    if (documentsSearchResults) documentsSearchResults.innerHTML = "";
    try {
      const response = await fetch(appUrl("/api/document-search"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query }),
      });
      const data = await response.json();
      const results = data.results || [];
      renderDocumentsSearchResults(results, query);
      setDocumentsSearchStatus(results.length ? `Znaleziono dokumenty: ${results.length}.` : "Brak wyników.");
    } catch (error) {
      setDocumentsSearchStatus(`Błąd wyszukiwania: ${error}`);
    }
  });

  documentsSearchClear.addEventListener("click", clearDocumentsSearch);
}

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
  resetDocumentSearch();
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

function openExamplesModal() {
  examplesModal.hidden = false;
  document.body.classList.add("modal-open");
}

function closeExamplesModal() {
  examplesModal.hidden = true;
  document.body.classList.remove("modal-open");
}

function openInfoModal() {
  infoModal.hidden = false;
  document.body.classList.add("modal-open");
}

function closeInfoModal() {
  infoModal.hidden = true;
  document.body.classList.remove("modal-open");
}

if (examplesModal && examplesOpen && examplesClose && textarea) {
  examplesOpen.addEventListener("click", openExamplesModal);
  examplesClose.addEventListener("click", closeExamplesModal);
  examplesModal.addEventListener("click", (event) => {
    if (event.target.matches("[data-close-examples]")) {
      closeExamplesModal();
      return;
    }

    const button = event.target.closest(".example-question");
    if (!button) return;
    textarea.value = button.textContent.trim();
    textarea.focus();
    closeExamplesModal();
  });
}

if (infoModal && infoOpen && infoClose) {
  infoOpen.addEventListener("click", openInfoModal);
  infoClose.addEventListener("click", closeInfoModal);
  infoModal.addEventListener("click", (event) => {
    if (event.target.matches("[data-close-info]")) {
      closeInfoModal();
    }
  });
}

modalClose.addEventListener("click", closeModal);
modal.addEventListener("click", (event) => {
  if (event.target.matches("[data-close-modal]")) closeModal();
});

if (documentSearch) {
  documentSearch.addEventListener("input", () => {
    highlightDocumentSearch(documentSearch.value);
  });
  documentSearch.addEventListener("keydown", (event) => {
    if (event.key !== "Enter" || !documentSearchHits.length) return;
    event.preventDefault();
    activateDocumentSearchHit(documentSearchIndex + (event.shiftKey ? -1 : 1));
  });
}

if (documentSearchPrev) {
  documentSearchPrev.addEventListener("click", () => activateDocumentSearchHit(documentSearchIndex - 1));
}

if (documentSearchNext) {
  documentSearchNext.addEventListener("click", () => activateDocumentSearchHit(documentSearchIndex + 1));
}
document.addEventListener("keydown", (event) => {
  if (event.key !== "Escape") return;
  if (infoModal && !infoModal.hidden) closeInfoModal();
  if (examplesModal && !examplesModal.hidden) closeExamplesModal();
  if (!modal.hidden) closeModal();
});
