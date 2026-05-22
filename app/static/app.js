const state = {
  selectedFiles: [],
  indexReady: false,
  collections: [],
  documents: [],
  selectedDocumentIds: new Set(),
  selectedCollectionIds: new Set(),
  expandedCollectionIds: new Set(),
  detailsOpen: false,
};

const allowedExtensions = new Set(["pdf", "txt", "md"]);

const els = {
  statusDot: document.querySelector("#statusDot"),
  statusLabel: document.querySelector("#statusLabel"),
  statusMeta: document.querySelector("#statusMeta"),
  globalAlert: document.querySelector("#globalAlert"),
  ingestForm: document.querySelector("#ingestForm"),
  dropZone: document.querySelector("#dropZone"),
  fileInput: document.querySelector("#fileInput"),
  fileTitle: document.querySelector("#fileTitle"),
  fileHint: document.querySelector("#fileHint"),
  uploadCollectionSelect: document.querySelector("#uploadCollectionSelect"),
  recreateInput: document.querySelector("#recreateInput"),
  ingestButton: document.querySelector("#ingestButton"),
  ingestResult: document.querySelector("#ingestResult"),
  collectionForm: document.querySelector("#collectionForm"),
  collectionNameInput: document.querySelector("#collectionNameInput"),
  collectionButton: document.querySelector("#collectionButton"),
  collectionList: document.querySelector("#collectionList"),
  askStateLabel: document.querySelector("#askStateLabel"),
  queryForm: document.querySelector("#queryForm"),
  questionInput: document.querySelector("#questionInput"),
  queryButton: document.querySelector("#queryButton"),
  scopeLedger: document.querySelector("#scopeLedger"),
  activeScope: document.querySelector("#activeScope"),
  clearScopeButton: document.querySelector("#clearScopeButton"),
  answerSection: document.querySelector("#answerSection"),
  answerText: document.querySelector("#answerText"),
  responseBadges: document.querySelector("#responseBadges"),
  detailsPanel: document.querySelector("#detailsPanel"),
  detailsToggle: document.querySelector("#detailsToggle"),
  detailsBody: document.querySelector("#detailsBody"),
  sourcesSection: document.querySelector("#sourcesSection"),
  sourcesList: document.querySelector("#sourcesList"),
  traceSection: document.querySelector("#traceSection"),
  traceRequestId: document.querySelector("#traceRequestId"),
  traceSummary: document.querySelector("#traceSummary"),
  traceWarnings: document.querySelector("#traceWarnings"),
  traceChunks: document.querySelector("#traceChunks"),
  chips: document.querySelectorAll(".chip"),
};

function showAlert(message) {
  els.globalAlert.textContent = message;
  els.globalAlert.classList.remove("hidden");
}

function clearAlert() {
  els.globalAlert.textContent = "";
  els.globalAlert.classList.add("hidden");
}

function setLoading(button, isLoading, label) {
  button.disabled = isLoading;
  button.classList.toggle("is-loading", isLoading);
  const buttonLabel = button.querySelector(".button-label");
  if (buttonLabel && label) {
    buttonLabel.textContent = label;
  }
}

function setIndexReady(isReady, metaText = "") {
  state.indexReady = isReady;
  els.questionInput.disabled = !isReady;
  els.queryButton.disabled = !isReady;
  els.askStateLabel.textContent = isReady ? "Ready to query" : "Waiting for an index";
  els.questionInput.placeholder = isReady
    ? "Ask a grounded question about the ingested document..."
    : "Ingest a document first, then ask a question...";

  els.statusDot.classList.toggle("ready", isReady);
  els.statusDot.classList.toggle("error", false);
  els.statusLabel.textContent = isReady ? "Index ready" : "No indexed documents yet";
  els.statusMeta.textContent = metaText || (isReady ? "You can ask questions now." : "Upload and ingest a document to begin.");
}

function setStatusError(message) {
  els.statusDot.classList.remove("ready");
  els.statusDot.classList.add("error");
  els.statusLabel.textContent = "Status unavailable";
  els.statusMeta.textContent = message;
}

function fileExtension(fileName) {
  return fileName.split(".").pop().toLowerCase();
}

function selectFiles(files) {
  const selected = Array.from(files || []);
  if (selected.length === 0) {
    return;
  }

  const unsupported = selected.filter((file) => !allowedExtensions.has(fileExtension(file.name)));
  if (unsupported.length > 0) {
    state.selectedFiles = [];
    els.fileInput.value = "";
    els.fileTitle.textContent = "Choose PDF, TXT, or MD files";
    els.fileHint.textContent = "This demo matches the document types currently supported by ingestion.";
    showAlert(`Unsupported file type: ${unsupported.map((file) => file.name).join(", ")}`);
    return;
  }

  clearAlert();
  state.selectedFiles = selected;
  if (selected.length === 1) {
    els.fileTitle.textContent = selected[0].name;
    els.fileHint.textContent = `${formatBytes(selected[0].size)} selected`;
  } else {
    const totalBytes = selected.reduce((sum, file) => sum + file.size, 0);
    els.fileTitle.textContent = `${selected.length} files selected`;
    els.fileHint.textContent = `${formatBytes(totalBytes)} total · ${selected.map((file) => file.name).join(", ")}`;
  }
}

function formatBytes(bytes) {
  if (!Number.isFinite(bytes) || bytes === 0) {
    return "0 bytes";
  }
  const units = ["bytes", "KB", "MB", "GB"];
  const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  const value = bytes / 1024 ** index;
  return `${value.toFixed(value >= 10 || index === 0 ? 0 : 1)} ${units[index]}`;
}

async function parseResponse(response) {
  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    return response.json();
  }
  return { detail: await response.text() };
}

function errorMessage(prefix, payload) {
  if (payload?.detail) {
    if (Array.isArray(payload.detail)) {
      return `${prefix}: ${payload.detail.map((item) => item.msg || JSON.stringify(item)).join(", ")}`;
    }
    return `${prefix}: ${payload.detail}`;
  }
  if (payload?.message) {
    return `${prefix}: ${payload.message}`;
  }
  return prefix;
}

async function apiJson(url, options = {}) {
  const response = await fetch(url, options);
  const payload = await parseResponse(response);
  if (!response.ok) {
    throw new Error(errorMessage("Request failed", payload));
  }
  return payload;
}

async function refreshMetadata() {
  try {
    const [collectionsPayload, documentsPayload] = await Promise.all([
      apiJson("/collections"),
      apiJson("/documents"),
    ]);
    state.collections = collectionsPayload.collections || [];
    state.documents = documentsPayload.documents || [];
    pruneScopeSelections();
    renderCollections();
    renderUploadCollectionOptions();
    renderScopeLedger();
  } catch (error) {
    showAlert(error.message || "Could not load document metadata.");
  }
}

function pruneScopeSelections() {
  const documentIds = new Set(state.documents.map((document) => document.document_id));
  const collectionIds = new Set(state.collections.map((collection) => collection.collection_id));

  state.selectedDocumentIds.forEach((documentId) => {
    if (!documentIds.has(documentId)) {
      state.selectedDocumentIds.delete(documentId);
    }
  });
  state.selectedCollectionIds.forEach((collectionId) => {
    if (!collectionIds.has(collectionId)) {
      state.selectedCollectionIds.delete(collectionId);
    }
  });
}

async function refreshStatus() {
  try {
    const response = await fetch("/status/");
    const payload = await parseResponse(response);

    if (!response.ok) {
      throw new Error(errorMessage("Status check failed", payload));
    }

    if (payload.index_ready) {
      setIndexReady(true, `${payload.collection_name} has about ${payload.point_count} indexed chunks.`);
    } else if (payload.qdrant_error) {
      setIndexReady(false);
      setStatusError(payload.qdrant_error);
    } else {
      setIndexReady(false, `${payload.collection_name} is empty. Retrieval mode: ${payload.retrieval_mode}.`);
    }
  } catch (error) {
    setStatusError(error.message || "Could not reach the status endpoint.");
  }
}

async function handleIngest(event) {
  event.preventDefault();
  clearAlert();
  els.ingestResult.classList.add("hidden");

  if (state.selectedFiles.length === 0) {
    showAlert("Choose one or more PDF, TXT, or MD files before ingesting.");
    return;
  }

  const formData = new FormData();
  state.selectedFiles.forEach((file) => {
    formData.append("files", file);
  });
  formData.append("recreate", els.recreateInput.checked ? "true" : "false");
  if (els.uploadCollectionSelect.value) {
    formData.append("collection_id", els.uploadCollectionSelect.value);
  }

  setLoading(els.ingestButton, true, "Ingesting...");
  els.queryButton.disabled = true;
  els.questionInput.disabled = true;

  try {
    const response = await fetch("/ingest/", {
      method: "POST",
      body: formData,
    });
    const payload = await parseResponse(response);

    if (!response.ok) {
      throw new Error(errorMessage("Ingestion failed", payload));
    }

    renderIngestResult(payload);
    els.ingestResult.classList.remove("hidden");
    setIndexReady(true, "Freshly ingested document is ready for questions.");
    await refreshStatus();
    await refreshMetadata();
  } catch (error) {
    showAlert(error.message || "Ingestion failed. Check the backend logs for details.");
    await refreshStatus();
  } finally {
    setLoading(els.ingestButton, false, "Ingest documents");
    els.queryButton.disabled = !state.indexReady;
    els.questionInput.disabled = !state.indexReady;
  }
}

async function handleQuery(event) {
  event.preventDefault();
  clearAlert();

  const query = els.questionInput.value.trim();
  if (!query) {
    showAlert("Enter a question before querying.");
    return;
  }

  setLoading(els.queryButton, true, "Thinking...");
  els.answerSection.classList.add("hidden");
  const document_ids = Array.from(state.selectedDocumentIds);
  const collection_ids = Array.from(state.selectedCollectionIds);

  try {
    const response = await fetch("/query/", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ question: query, document_ids, collection_ids }),
    });
    const payload = await parseResponse(response);

    if (!response.ok) {
      throw new Error(errorMessage("Query failed", payload));
    }

    renderAnswer(payload);
  } catch (error) {
    showAlert(error.message || "Query failed. Check the backend logs for details.");
  } finally {
    setLoading(els.queryButton, false, "Ask question");
    els.queryButton.disabled = !state.indexReady;
  }
}

function renderAnswer(payload) {
  els.answerText.innerHTML = renderMarkdown(payload.answer || "No answer returned.");
  els.responseBadges.innerHTML = "";
  state.detailsOpen = false;
  els.detailsBody.classList.add("hidden");
  els.detailsToggle.textContent = "Show details";

  addBadge(payload.mode ? `Mode: ${payload.mode}` : "Mode: unknown");
  addBadge(payload.cached ? "Cached" : "Fresh");
  if (payload.trace?.scope?.scoped) {
    addBadge("Scoped");
  }
  if (payload.score !== undefined && payload.score !== null) {
    addBadge(`Cache score: ${formatValue(payload.score)}`);
  }

  renderSources(collectSourceItems(payload));
  renderTrace(payload.trace);
  const hasDetails = !els.sourcesSection.classList.contains("hidden") || !els.traceSection.classList.contains("hidden");
  els.detailsPanel.classList.toggle("hidden", !hasDetails);
  els.answerSection.classList.remove("hidden");
}

function renderMarkdown(markdown) {
  const lines = String(markdown).replace(/\r\n?/g, "\n").split("\n");
  const blocks = [];
  let paragraph = [];
  let listType = null;
  let listItems = [];
  let inCodeBlock = false;
  let codeLines = [];

  function flushParagraph() {
    if (paragraph.length > 0) {
      blocks.push(`<p>${renderInlineMarkdown(paragraph.join(" ").trim())}</p>`);
      paragraph = [];
    }
  }

  function flushList() {
    if (listItems.length > 0 && listType) {
      const items = listItems.map((item) => `<li>${renderInlineMarkdown(item)}</li>`).join("");
      blocks.push(`<${listType}>${items}</${listType}>`);
      listItems = [];
      listType = null;
    }
  }

  lines.forEach((rawLine) => {
    const line = rawLine.trimEnd();
    const trimmed = line.trim();

    if (trimmed.startsWith("```")) {
      if (inCodeBlock) {
        blocks.push(`<pre><code>${escapeHtml(codeLines.join("\n"))}</code></pre>`);
        codeLines = [];
        inCodeBlock = false;
      } else {
        flushParagraph();
        flushList();
        inCodeBlock = true;
      }
      return;
    }

    if (inCodeBlock) {
      codeLines.push(rawLine);
      return;
    }

    if (!trimmed) {
      flushParagraph();
      flushList();
      return;
    }

    const heading = trimmed.match(/^(#{1,3})\s+(.+)$/);
    if (heading) {
      flushParagraph();
      flushList();
      const level = heading[1].length + 2;
      blocks.push(`<h${level}>${renderInlineMarkdown(heading[2])}</h${level}>`);
      return;
    }

    const unorderedItem = trimmed.match(/^[-*]\s+(.+)$/);
    if (unorderedItem) {
      flushParagraph();
      if (listType && listType !== "ul") {
        flushList();
      }
      listType = "ul";
      listItems.push(unorderedItem[1].trim());
      return;
    }

    const orderedItem = trimmed.match(/^\d+[.)]\s+(.+)$/);
    if (orderedItem) {
      flushParagraph();
      if (listType && listType !== "ol") {
        flushList();
      }
      listType = "ol";
      listItems.push(orderedItem[1].trim());
      return;
    }

    flushList();
    paragraph.push(trimmed);
  });

  if (inCodeBlock) {
    blocks.push(`<pre><code>${escapeHtml(codeLines.join("\n"))}</code></pre>`);
  }
  flushParagraph();
  flushList();

  return blocks.join("");
}

function renderInlineMarkdown(text) {
  const codeSpans = [];
  let rendered = escapeHtml(text).replace(/`([^`]+)`/g, (_match, code) => {
    const token = `@@CODE_SPAN_${codeSpans.length}@@`;
    codeSpans.push(`<code>${code}</code>`);
    return token;
  });

  rendered = rendered
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/__(.+?)__/g, "<strong>$1</strong>")
    .replace(/(^|[^\*])\*([^*\n]+)\*/g, "$1<em>$2</em>")
    .replace(/(^|[^_])_([^_\n]+)_/g, "$1<em>$2</em>");

  codeSpans.forEach((code, index) => {
    rendered = rendered.replace(`@@CODE_SPAN_${index}@@`, code);
  });

  return rendered;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function addBadge(text) {
  const badge = document.createElement("span");
  badge.className = "badge";
  badge.textContent = text;
  els.responseBadges.appendChild(badge);
}

function renderIngestResult(payload) {
  els.ingestResult.textContent = "";

  const title = document.createElement("strong");
  title.textContent = "Ingestion complete.";

  const summary = document.createElement("span");
  summary.textContent = `${payload.docs_ingested ?? 0} document page(s) loaded, ${payload.nodes ?? 0} chunks indexed.`;

  els.ingestResult.append(title, summary);

  if (payload.trace?.request_id) {
    const request = document.createElement("small");
    request.textContent = `Request ${payload.trace.request_id}`;
    els.ingestResult.appendChild(request);
  }
}

function renderUploadCollectionOptions() {
  const currentValue = els.uploadCollectionSelect.value;
  els.uploadCollectionSelect.innerHTML = '<option value="">Ungrouped</option>';
  state.collections.forEach((collection) => {
    const option = document.createElement("option");
    option.value = collection.collection_id;
    option.textContent = collection.collection_name;
    els.uploadCollectionSelect.appendChild(option);
  });
  if (state.collections.some((collection) => collection.collection_id === currentValue)) {
    els.uploadCollectionSelect.value = currentValue;
  }
}

function renderCollections() {
  els.collectionList.innerHTML = "";
  if (state.collections.length === 0) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    empty.textContent = "No collections yet. Uploaded documents can stay ungrouped until you create one.";
    els.collectionList.appendChild(empty);
    return;
  }

  state.collections.forEach((collection) => {
    const row = document.createElement("div");
    row.className = "collection-row";

    const label = document.createElement("div");
    const name = document.createElement("strong");
    name.textContent = collection.collection_name;
    const count = document.createElement("p");
    count.textContent = `${collection.document_count || 0} document${collection.document_count === 1 ? "" : "s"}`;
    label.append(name, count);

    const rename = document.createElement("button");
    rename.className = "mini-button";
    rename.type = "button";
    rename.textContent = "Rename";
    rename.addEventListener("click", () => renameCollection(collection));

    const remove = document.createElement("button");
    remove.className = "mini-button";
    remove.type = "button";
    remove.textContent = "Delete";
    remove.addEventListener("click", () => deleteCollection(collection));

    row.append(label, rename, remove);
    els.collectionList.appendChild(row);
  });
}

function documentsForCollection(collectionId) {
  return state.documents.filter((doc) => doc.collection_id === collectionId);
}

function ungroupedDocuments() {
  return state.documents.filter((doc) => !doc.collection_id);
}

function renderScopeLedger() {
  els.scopeLedger.innerHTML = "";
  renderActiveScope();

  if (state.documents.length === 0 && state.collections.length === 0) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    empty.textContent = "Upload documents to build a selectable retrieval scope.";
    els.scopeLedger.appendChild(empty);
    return;
  }

  state.collections.forEach((collection) => {
    els.scopeLedger.appendChild(scopeGroup(collection, documentsForCollection(collection.collection_id)));
  });

  const looseDocs = ungroupedDocuments();
  if (looseDocs.length > 0) {
    const group = document.createElement("div");
    group.className = "scope-group";
    const title = document.createElement("div");
    title.className = "scope-group-title";
    const spacer = document.createElement("p");
    const label = document.createElement("strong");
    label.textContent = "Ungrouped";
    const count = document.createElement("p");
    count.textContent = `${looseDocs.length} document${looseDocs.length === 1 ? "" : "s"}`;
    title.append(spacer, label, count);
    group.appendChild(title);
    const docs = document.createElement("div");
    docs.className = "scope-group-docs";
    looseDocs.forEach((doc) => docs.appendChild(scopeDocumentRow(doc)));
    group.appendChild(docs);
    els.scopeLedger.appendChild(group);
  }
}

function scopeGroup(collection, documents) {
  const group = document.createElement("div");
  group.className = "scope-group";

  const title = document.createElement("div");
  title.className = "scope-group-title";

  const checkLabel = document.createElement("label");
  checkLabel.className = "scope-check";
  const checkbox = document.createElement("input");
  checkbox.type = "checkbox";
  checkbox.checked = state.selectedCollectionIds.has(collection.collection_id);
  checkbox.addEventListener("change", () => {
    toggleSet(state.selectedCollectionIds, collection.collection_id, checkbox.checked);
    renderActiveScope();
  });
  checkLabel.appendChild(checkbox);

  const name = document.createElement("strong");
  name.textContent = collection.collection_name;

  const expand = document.createElement("button");
  expand.className = "mini-button";
  expand.type = "button";
  const isExpanded = state.expandedCollectionIds.has(collection.collection_id);
  expand.textContent = isExpanded ? "Hide" : `${documents.length} docs`;
  expand.addEventListener("click", () => {
    toggleSet(state.expandedCollectionIds, collection.collection_id, !isExpanded);
    renderScopeLedger();
  });

  title.append(checkLabel, name, expand);
  group.appendChild(title);

  if (isExpanded) {
    const docs = document.createElement("div");
    docs.className = "scope-group-docs";
    if (documents.length === 0) {
      const empty = document.createElement("div");
      empty.className = "empty-state";
      empty.textContent = "This collection has no documents.";
      docs.appendChild(empty);
    } else {
      documents.forEach((doc) => docs.appendChild(scopeDocumentRow(doc)));
    }
    group.appendChild(docs);
  }

  return group;
}

function scopeDocumentRow(doc) {
  const row = document.createElement("div");
  row.className = "scope-doc-row";

  const checkLabel = document.createElement("label");
  checkLabel.className = "scope-check";
  const checkbox = document.createElement("input");
  checkbox.type = "checkbox";
  checkbox.checked = state.selectedDocumentIds.has(doc.document_id);
  checkbox.addEventListener("change", () => {
    toggleSet(state.selectedDocumentIds, doc.document_id, checkbox.checked);
    renderActiveScope();
  });
  checkLabel.appendChild(checkbox);

  const label = document.createElement("div");
  const name = document.createElement("strong");
  name.textContent = doc.document_name;
  const meta = document.createElement("p");
  meta.textContent = `${doc.chunk_count || 0} chunks`;
  label.append(name, meta);

  const select = document.createElement("select");
  select.className = "doc-collection-select";
  select.value = doc.collection_id || "";
  select.innerHTML = '<option value="">Ungrouped</option>';
  state.collections.forEach((collection) => {
    const option = document.createElement("option");
    option.value = collection.collection_id;
    option.textContent = collection.collection_name;
    select.appendChild(option);
  });
  select.value = doc.collection_id || "";
  select.addEventListener("change", () => moveDocument(doc, select.value));

  row.append(checkLabel, label, select);
  return row;
}

function renderActiveScope() {
  const documentNames = Array.from(state.selectedDocumentIds)
    .map((documentId) => state.documents.find((doc) => doc.document_id === documentId)?.document_name)
    .filter(Boolean);
  const collectionNames = Array.from(state.selectedCollectionIds)
    .map((collectionId) => state.collections.find((collection) => collection.collection_id === collectionId)?.collection_name)
    .filter(Boolean);

  const items = [...collectionNames.map((name) => `Collection: ${name}`), ...documentNames.map((name) => `Document: ${name}`)];
  els.activeScope.textContent = items.length ? items.join(" · ") : "All indexed documents";
}

function toggleSet(set, value, enabled) {
  if (enabled) {
    set.add(value);
  } else {
    set.delete(value);
  }
}

async function handleCreateCollection(event) {
  event.preventDefault();
  const collectionName = els.collectionNameInput.value.trim();
  if (!collectionName) {
    showAlert("Enter a collection name.");
    return;
  }
  clearAlert();
  setLoading(els.collectionButton, true, "Creating...");
  try {
    await apiJson("/collections", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ collection_name: collectionName }),
    });
    els.collectionNameInput.value = "";
    await refreshMetadata();
  } catch (error) {
    showAlert(error.message || "Could not create collection.");
  } finally {
    setLoading(els.collectionButton, false, "Create");
  }
}

async function renameCollection(collection) {
  const nextName = window.prompt("Rename collection", collection.collection_name);
  if (!nextName || !nextName.trim()) {
    return;
  }
  try {
    await apiJson(`/collections/${collection.collection_id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ collection_name: nextName.trim() }),
    });
    await refreshMetadata();
  } catch (error) {
    showAlert(error.message || "Could not rename collection.");
  }
}

async function deleteCollection(collection) {
  if (!window.confirm(`Delete "${collection.collection_name}"? Documents will remain ungrouped.`)) {
    return;
  }
  try {
    await apiJson(`/collections/${collection.collection_id}`, { method: "DELETE" });
    state.selectedCollectionIds.delete(collection.collection_id);
    await refreshMetadata();
  } catch (error) {
    showAlert(error.message || "Could not delete collection.");
  }
}

async function moveDocument(doc, nextCollectionId) {
  try {
    if (nextCollectionId) {
      await apiJson(`/collections/${nextCollectionId}/documents`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ document_ids: [doc.document_id] }),
      });
    } else if (doc.collection_id) {
      await apiJson(`/collections/${doc.collection_id}/documents/${doc.document_id}`, {
        method: "DELETE",
      });
    }
    await refreshMetadata();
  } catch (error) {
    showAlert(error.message || "Could not update document collection.");
    await refreshMetadata();
  }
}

function collectSourceItems(payload) {
  const items = [];

  if (Array.isArray(payload.sources)) {
    payload.sources.forEach((source) => items.push(normalizeSource(source, "source")));
  }

  if (Array.isArray(payload.trace?.final_chunks)) {
    payload.trace.final_chunks.forEach((node) => items.push(normalizeSource(node, "final")));
  }

  if (Array.isArray(payload.reranked_nodes)) {
    payload.reranked_nodes.forEach((node) => items.push(normalizeSource(node, "reranked")));
  }

  if (items.length === 0 && Array.isArray(payload.retrieved_nodes)) {
    payload.retrieved_nodes.forEach((node) => items.push(normalizeSource(node, "retrieved")));
  }

  return items;
}

function renderTrace(trace) {
  if (!trace) {
    els.traceSection.classList.add("hidden");
    return;
  }

  els.traceRequestId.textContent = trace.request_id ? `Request ${trace.request_id}` : "";
  els.traceSummary.innerHTML = "";
  els.traceWarnings.innerHTML = "";
  els.traceChunks.innerHTML = "";

  const embeddingCalls = trace.external_calls?.embedding_calls || {};
  const llmCalls = trace.external_calls?.llm_calls || {};
  const rerankerCalls = trace.external_calls?.reranker_calls || {};

  const summaryItems = [
    ["LLM", `${trace.providers?.llm || "unknown"} / ${trace.models?.llm || "unknown"}`],
    ["Embeddings", `${trace.providers?.embedding || "unknown"} / ${trace.models?.embedding || "unknown"}`],
    ["Mode", trace.retrieval?.mode || trace.retrieval_mode || "unknown"],
    ["Top K", trace.retrieval?.top_k ?? "unknown"],
    ["Retrieved", trace.retrieved_count ?? "n/a"],
    ["Final Context", trace.final_context_count ?? "n/a"],
    ["Cache", trace.cache?.hit ? `hit (${formatValue(trace.cache.score)})` : trace.cache?.enabled ? "miss" : "off"],
    ["Latency", trace.timings?.total ? `${formatValue(trace.timings.total)}s` : "n/a"],
    ["Embedding Calls", Object.values(embeddingCalls).reduce((sum, value) => sum + Number(value || 0), 0)],
    ["LLM Calls", Object.values(llmCalls).reduce((sum, value) => sum + Number(value || 0), 0)],
    ["Remote Rerank Calls", rerankerCalls.remote ?? 0],
  ];

  summaryItems.forEach(([label, value]) => {
    els.traceSummary.appendChild(traceItem(label, value));
  });

  Object.entries(trace.timings || {}).forEach(([label, value]) => {
    els.traceSummary.appendChild(traceItem(`${label} latency`, `${formatValue(value)}s`));
  });

  if (Array.isArray(trace.warnings) && trace.warnings.length > 0) {
    trace.warnings.forEach((warning) => {
      const item = document.createElement("div");
      item.textContent = warning;
      els.traceWarnings.appendChild(item);
    });
    els.traceWarnings.classList.remove("hidden");
  } else {
    els.traceWarnings.classList.add("hidden");
  }

  const chunks = Array.isArray(trace.final_chunks) && trace.final_chunks.length
    ? trace.final_chunks
    : trace.retrieved_chunks || [];

  if (chunks.length > 0) {
    const title = document.createElement("h4");
    title.textContent = "Chunks used";
    els.traceChunks.appendChild(title);

    chunks.forEach((chunk) => {
      const row = document.createElement("div");
      row.className = "trace-chunk";
      const name = chunk.source || chunk.file_name || chunk.file_path || chunk.chunk_id || "chunk";
      const chunkTitle = document.createElement("strong");
      chunkTitle.textContent = String(name);
      const chunkMeta = document.createElement("span");
      chunkMeta.textContent = [
        chunk.chunk_id ? `id ${chunk.chunk_id}` : "",
        chunk.score !== undefined ? `score ${formatValue(chunk.score)}` : "",
        chunk.rerank_score !== undefined ? `rerank ${formatValue(chunk.rerank_score)}` : "",
        chunk.page_label || chunk.page_number || chunk.page ? `page ${chunk.page_label || chunk.page_number || chunk.page}` : "",
      ].filter(Boolean).join(" · ");
      row.append(chunkTitle, chunkMeta);
      els.traceChunks.appendChild(row);
    });
    els.traceChunks.classList.remove("hidden");
  } else {
    els.traceChunks.classList.add("hidden");
  }

  els.traceSection.classList.remove("hidden");
}

function traceItem(label, value) {
  const item = document.createElement("div");
  item.className = "trace-item";
  const key = document.createElement("span");
  key.textContent = label;
  const val = document.createElement("strong");
  val.textContent = value === undefined || value === null ? "n/a" : String(value);
  item.append(key, val);
  return item;
}

function normalizeSource(source, retrieverType) {
  if (!source || typeof source !== "object") {
    return { retriever_type: retrieverType, value: source };
  }

  const node = source.node && typeof source.node === "object" ? source.node : null;
  const metadata = node?.metadata && typeof node.metadata === "object" ? node.metadata : {};
  const normalized = {
    ...metadata,
    ...source,
    retriever_type: source.retriever_type || retrieverType,
  };

  if (node) {
    normalized.chunk_id = normalized.chunk_id || node.id_ || node.node_id || source.node_id;
    normalized.text = normalized.text || node.text;
  }

  return normalized;
}

function renderSources(sources) {
  els.sourcesList.innerHTML = "";

  if (!Array.isArray(sources) || sources.length === 0) {
    els.sourcesSection.classList.add("hidden");
    return;
  }

  sources.forEach((source, index) => {
    const card = document.createElement("article");
    card.className = "source-card";

    const title = document.createElement("div");
    title.className = "source-title";
    const sourceName = document.createElement("strong");
    sourceName.textContent = bestSourceName(source, index);
    const sourceNumber = document.createElement("span");
    sourceNumber.textContent = `Source ${index + 1}`;
    title.append(sourceName, sourceNumber);

    const grid = document.createElement("div");
    grid.className = "meta-grid";

    importantEntries(source).forEach(([key, value]) => {
      grid.appendChild(metaItem(key, value));
    });

    card.append(title);
    const chunkText = source.text || source.chunk || source.content;
    if (chunkText) {
      const snippet = document.createElement("p");
      snippet.className = "source-snippet";
      snippet.textContent = String(chunkText);
      card.appendChild(snippet);
    }
    card.appendChild(grid);
    els.sourcesList.appendChild(card);
  });

  els.sourcesSection.classList.remove("hidden");
}

function bestSourceName(source, index) {
  const candidates = [
    source.file_name,
    source.filename,
    source.file_path,
    source.path,
    source.document_id,
    source.doc_id,
    source.id,
  ];
  return candidates.find(Boolean) || `Retrieved chunk ${index + 1}`;
}

function importantEntries(source) {
  const preferred = [
    "file_name",
    "filename",
    "file_path",
    "path",
    "page_label",
    "page",
    "page_number",
    "chunk_id",
    "node_id",
    "document_id",
    "doc_id",
    "retriever",
    "retriever_type",
    "score",
    "similarity",
    "rerank_score",
    "sparse_score",
    "dense_score",
    "value",
  ];
  const entries = [];
  const seen = new Set();

  preferred.forEach((key) => {
    if (source[key] !== undefined && source[key] !== null && source[key] !== "") {
      entries.push([labelFor(key), source[key]]);
      seen.add(key);
    }
  });

  Object.entries(source).forEach(([key, value]) => {
    if (!seen.has(key) && key !== "node" && key !== "text" && key !== "chunk" && key !== "content" && value !== undefined && value !== null && value !== "") {
      entries.push([labelFor(key), value]);
    }
  });

  return entries.length ? entries : [["Metadata", "No source metadata returned"]];
}

function labelFor(key) {
  return key.replaceAll("_", " ");
}

function metaItem(key, value) {
  const item = document.createElement("div");
  item.className = "meta-item";
  const label = document.createElement("strong");
  label.textContent = key;
  const content = document.createElement("span");
  content.textContent = formatValue(value);
  item.append(label, content);
  return item;
}

function formatValue(value) {
  if (typeof value === "number") {
    return Number.isInteger(value) ? String(value) : value.toFixed(4);
  }
  if (typeof value === "object") {
    return JSON.stringify(value);
  }
  return String(value);
}

els.fileInput.addEventListener("change", (event) => {
  selectFiles(event.target.files);
});

["dragenter", "dragover"].forEach((eventName) => {
  els.dropZone.addEventListener(eventName, (event) => {
    event.preventDefault();
    els.dropZone.classList.add("drag-over");
  });
});

["dragleave", "drop"].forEach((eventName) => {
  els.dropZone.addEventListener(eventName, (event) => {
    event.preventDefault();
    els.dropZone.classList.remove("drag-over");
  });
});

els.dropZone.addEventListener("drop", (event) => {
  const files = event.dataTransfer.files;
  if (files?.length) {
    els.fileInput.files = event.dataTransfer.files;
    selectFiles(files);
  }
});

els.ingestForm.addEventListener("submit", handleIngest);
els.collectionForm.addEventListener("submit", handleCreateCollection);
els.queryForm.addEventListener("submit", handleQuery);
els.clearScopeButton.addEventListener("click", () => {
  state.selectedDocumentIds.clear();
  state.selectedCollectionIds.clear();
  renderScopeLedger();
});

els.detailsToggle.addEventListener("click", () => {
  state.detailsOpen = !state.detailsOpen;
  els.detailsBody.classList.toggle("hidden", !state.detailsOpen);
  els.detailsToggle.textContent = state.detailsOpen ? "Hide details" : "Show details";
});

els.chips.forEach((chip) => {
  chip.addEventListener("click", () => {
    els.questionInput.value = chip.textContent;
    if (state.indexReady) {
      els.questionInput.focus();
    }
  });
});

refreshStatus();
refreshMetadata();
