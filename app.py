from __future__ import annotations

import hmac
import logging
import re
from pathlib import Path

from flask import Flask, jsonify, redirect, render_template, request, session, url_for
from werkzeug.middleware.proxy_fix import ProxyFix

from config import APP_TITLE, AUTH_PASSWORD, AUTH_USERNAME, MD_DIR, SEARCH_LIMIT, SECRET_KEY, TRACE_RAG, TRACE_RAG_FULL, WIKI_DIR, WIKI_TOPIC_BONUS
from llm import answer_with_gemini_details, attach_source_ids, build_context, cited_sources, select_wiki_topics
from rag import KnowledgeBase


app = Flask(__name__)
app.secret_key = SECRET_KEY
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)
kb = KnowledgeBase(MD_DIR)
if TRACE_RAG:
    app.logger.setLevel(logging.INFO)


WIKI_TOPIC_RE = re.compile(r"^-\s+\[(?P<title>[^\]]+)\]\((?P<filename>[^)]+)\)\s*$")
WIKI_DOCUMENT_RE = re.compile(r"^-\s+(?P<date>.+?)\s+-\s+`(?P<path>md/[^`]+\.md)`\s+-\s+(?P<title>.+?)\s*$")
FULLTEXT_SNIPPET_BEFORE_CHARS = 70
FULLTEXT_SNIPPET_AFTER_CHARS = 220


def is_authenticated() -> bool:
    return bool(session.get("authenticated"))


def wants_json_response() -> bool:
    return request.path.startswith("/api/")


def answer_needs_more_context(answer: str) -> bool:
    lowered = answer.casefold()
    return any(
        phrase in lowered
        for phrase in (
            "brakuje zapisów",
            "brakuje źródeł",
            "brakuje dokumentów",
            "brakuje informacji",
            "brakujące źródła",
            "nie zawierają informacji",
            "nie zawierają wystarczających",
            "fragmenty nie wystarczają",
            "niezbędne są dokumenty",
        )
    )


def followup_queries(question: str, answer: str) -> list[str]:
    haystack = f"{question}\n{answer}".casefold()
    queries: list[str] = []

    def add(query: str) -> None:
        normalized = " ".join(query.split())
        if normalized and normalized not in queries:
            queries.append(normalized)

    if "statut" in haystack:
        add("Statut IH PAN Dyrektor Rada Naukowa powołanie wybór")
    if "ustawa o polskiej akademii nauk" in haystack or "ustawa o pan" in haystack:
        add("Ustawa o Polskiej Akademii Nauk instytut dyrektor rada naukowa powołuje")
    if any(term in haystack for term in ("wład", "wlad", "przeją", "przejac", "powoływ", "powolyw", "wyłanian", "wylanian")):
        add("Statut IH PAN władze Instytutu Dyrektor Rada Naukowa")
        add("powołanie Dyrektora Instytutu Rada Naukowa ustawa o PAN")

    for line in answer.splitlines():
        candidate = re.sub(r"^\s*[-*0-9.)]+\s*", "", line).strip()
        if not candidate:
            continue
        if any(term in candidate.casefold() for term in ("statut", "ustawa", "regulamin", "zarządzenie", "uchwała")):
            add(candidate[:180])

    return queries[:5]


def merge_chunks(*chunk_groups: list[dict]) -> list[dict]:
    merged: list[dict] = []
    seen: set[tuple] = set()
    for chunks in chunk_groups:
        for chunk in chunks:
            key = (chunk.get("path"), chunk.get("start_line"), chunk.get("end_line"))
            if key in seen:
                continue
            seen.add(key)
            merged.append(chunk)
    return merged


def wiki_topic_title(path: Path, fallback: str) -> str:
    if not path.exists():
        return fallback.replace("-", " ")
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("# "):
            return line.removeprefix("# ").strip()
    return fallback.replace("-", " ")


def wiki_document_paths(path: Path) -> list[str]:
    if not path.exists():
        return []
    paths: list[str] = []
    seen: set[str] = set()
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        match = WIKI_DOCUMENT_RE.match(line.strip())
        if not match:
            continue
        document_path = match.group("path")
        if document_path not in seen:
            paths.append(document_path)
            seen.add(document_path)
    return paths


def wiki_topics() -> list[dict]:
    index_path = WIKI_DIR / "index.md"
    if not index_path.exists():
        return []

    documents_by_path = {document.path: document for document in kb.documents}
    topics: list[dict] = []
    for line in index_path.read_text(encoding="utf-8", errors="replace").splitlines():
        match = WIKI_TOPIC_RE.match(line.strip())
        if not match:
            continue

        topic_file = WIKI_DIR / Path(match.group("filename")).name
        topic_documents = [
            documents_by_path[path]
            for path in wiki_document_paths(topic_file)
            if path in documents_by_path
        ]
        topic_documents.sort(key=lambda document: (document.date, document.title), reverse=True)
        topics.append(
            {
                "id": topic_file.stem,
                "title": wiki_topic_title(topic_file, match.group("title")),
                "documents": topic_documents,
            }
        )
    return topics


def preferred_document_paths(topics: list[dict], topic_ids: list[str]) -> set[str]:
    selected_ids = set(topic_ids)
    paths: set[str] = set()
    for topic in topics:
        if topic["id"] not in selected_ids:
            continue
        for document in topic["documents"]:
            paths.add(document.path)
    return paths


def line_number_for_offset(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def fulltext_snippet(text: str, start: int, end: int) -> str:
    snippet_start = max(0, start - FULLTEXT_SNIPPET_BEFORE_CHARS)
    snippet_end = min(len(text), end + FULLTEXT_SNIPPET_AFTER_CHARS)
    snippet = text[snippet_start:snippet_end]
    snippet = re.sub(r"\s+", " ", snippet).strip()
    if snippet_start > 0:
        snippet = "..." + snippet
    if snippet_end < len(text):
        snippet += "..."
    return snippet


def document_fulltext_search(query: str, limit: int = 100) -> list[dict]:
    needle = query.casefold()
    if not needle:
        return []

    results: list[dict] = []
    documents_by_path = {document.path: document for document in kb.documents}
    for document_path, document in documents_by_path.items():
        filename = Path(document_path).name
        path = MD_DIR / filename
        if not path.exists():
            continue

        text = path.read_text(encoding="utf-8", errors="replace")
        haystack = text.casefold()
        first_index = haystack.find(needle)
        if first_index == -1:
            continue

        count = haystack.count(needle)
        start_line = line_number_for_offset(text, first_index)
        results.append(
            {
                "path": document.path,
                "title": document.title,
                "date": document.date,
                "kind": document.kind,
                "is_change": document.is_change,
                "match_count": count,
                "start_line": start_line,
                "end_line": start_line,
                "snippet": fulltext_snippet(text, first_index, first_index + len(query)),
            }
        )

    results.sort(key=lambda item: (item["match_count"], item["date"], item["title"]), reverse=True)
    return results[:limit]


def adaptive_answer(question: str, chunks: list[dict], preferred_paths: set[str] | None = None) -> tuple[str, list[dict], list[str], dict]:
    result = answer_with_gemini_details(question, chunks)
    answer = result.text
    if not answer_needs_more_context(answer):
        return answer, chunks, [], result.metadata | {"retried": result.retried}

    queries = followup_queries(question, answer)
    if not queries:
        return answer, chunks, [], result.metadata | {"retried": result.retried}

    extra_chunks: list[dict] = []
    for query in queries:
        extra_chunks.extend(kb.search(query, limit=4, preferred_paths=preferred_paths, topic_bonus=WIKI_TOPIC_BONUS))

    if not extra_chunks:
        return answer, chunks, queries, result.metadata | {"retried": result.retried}

    combined_chunks = attach_source_ids(merge_chunks(extra_chunks, chunks))
    if len(combined_chunks) == len(chunks):
        return answer, chunks, queries, result.metadata | {"retried": result.retried}

    if TRACE_RAG:
        app.logger.info("[RAG] Uruchamiam dodatkowe wyszukiwanie: %s", queries)
    retry_result = answer_with_gemini_details(question, combined_chunks)
    metadata = retry_result.metadata | {
        "retried": retry_result.retried,
        "first_pass": result.metadata,
        "adaptive_search": True,
    }
    return retry_result.text, combined_chunks, queries, metadata


def log_chat_trace(question: str, chunks: list[dict], answer: str, sources: list[dict], llm_metadata: dict) -> None:
    if not TRACE_RAG:
        return

    app.logger.info("[RAG] Pytanie: %s", question)
    app.logger.info("[RAG] Znalezione fragmenty: %s, limit: %s", len(chunks), SEARCH_LIMIT)
    for idx, chunk in enumerate(chunks, start=1):
        snippet = " ".join(chunk["text"].split())[:500]
        app.logger.info(
            "[RAG] #%s %s score=%s path=%s lines=%s-%s date=%s change=%s heading=%s title=%s snippet=%r",
            idx,
            chunk.get("source_id"),
            chunk.get("score"),
            chunk.get("path"),
            chunk.get("start_line"),
            chunk.get("end_line"),
            chunk.get("date"),
            chunk.get("is_change"),
            chunk.get("heading"),
            chunk.get("title"),
            snippet,
        )

    context = build_context(chunks)
    app.logger.info("[RAG] Kontekst dla modelu: %s znaków", len(context))
    if TRACE_RAG_FULL:
        app.logger.info("[RAG] Pełny kontekst dla modelu:\n%s", context)

    app.logger.info("[RAG] Długość odpowiedzi: %s znaków", len(answer))
    app.logger.info("[RAG] Gemini metadata: %s", llm_metadata)
    app.logger.info("[RAG] Źródła rozpoznane w odpowiedzi: %s", [source.get("source_id") for source in sources])
    if TRACE_RAG_FULL:
        app.logger.info("[RAG] Odpowiedź modelu:\n%s", answer)


@app.before_request
def require_login():
    allowed_endpoints = {"login", "static"}
    if request.endpoint in allowed_endpoints or is_authenticated():
        return None
    if wants_json_response():
        return jsonify({"error": "Wymagane logowanie."}), 401
    next_url = f"{request.script_root}{request.full_path}"
    return redirect(url_for("login", next=next_url))


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        username_ok = hmac.compare_digest(username, AUTH_USERNAME)
        password_ok = bool(AUTH_PASSWORD) and hmac.compare_digest(password, AUTH_PASSWORD)
        if username_ok and password_ok:
            session.clear()
            session["authenticated"] = True
            target = request.args.get("next") or url_for("index")
            if not target.startswith("/") or target.startswith("//"):
                target = url_for("index")
            return redirect(target)
        if not AUTH_PASSWORD:
            error = "Logowanie nie jest skonfigurowane. Ustaw AUTH_PASSWORD w pliku .env."
        else:
            error = "Nieprawidłowy login lub hasło."
    return render_template("login.html", title=APP_TITLE, error=error)


@app.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.get("/")
def index():
    return render_template("index.html", title=APP_TITLE, stats=kb.stats())


@app.get("/documents")
def documents():
    view = request.args.get("view", "chronological")
    if view not in {"chronological", "topics", "search"}:
        view = "chronological"
    return render_template(
        "documents.html",
        title=APP_TITLE,
        documents=sorted(kb.documents, key=lambda document: (document.date, document.title), reverse=True),
        document_topics=wiki_topics(),
        current_view=view,
        stats=kb.stats(),
    )


@app.get("/api/status")
def status():
    return jsonify({"ok": True, **kb.stats()})


@app.post("/api/search")
def search():
    payload = request.get_json(force=True)
    query = (payload.get("query") or "").strip()
    limit = int(payload.get("limit") or SEARCH_LIMIT)
    return jsonify({"query": query, "results": kb.search(query, limit=limit)})


@app.post("/api/document-search")
def document_search():
    payload = request.get_json(force=True)
    query = (payload.get("query") or "").strip()
    limit = int(payload.get("limit") or 100)
    if not query:
        return jsonify({"query": query, "results": []})
    return jsonify({"query": query, "results": document_fulltext_search(query, limit=limit)})


@app.get("/api/document")
def document():
    requested_path = (request.args.get("path") or "").strip()
    if not requested_path:
        return jsonify({"error": "Brak ścieżki dokumentu."}), 400

    md_root = MD_DIR.resolve()
    filename = Path(requested_path).name
    document_path = (md_root / filename).resolve()
    if document_path.parent != md_root or document_path.suffix != ".md":
        return jsonify({"error": "Nieprawidłowa ścieżka dokumentu."}), 400
    if not document_path.exists():
        return jsonify({"error": "Nie znaleziono dokumentu."}), 404

    return jsonify(
        {
            "path": f"md/{document_path.name}",
            "title": document_path.stem.replace("_", " "),
            "content": document_path.read_text(encoding="utf-8", errors="replace"),
        }
    )


@app.post("/api/chat")
def chat():
    payload = request.get_json(force=True)
    question = (payload.get("message") or "").strip()
    if not question:
        return jsonify({"error": "Brak pytania."}), 400
    topics = wiki_topics()
    selected_topic_ids, topic_metadata = select_wiki_topics(question, topics)
    preferred_paths = preferred_document_paths(topics, selected_topic_ids)
    chunks = attach_source_ids(
        kb.search(question, limit=SEARCH_LIMIT, preferred_paths=preferred_paths, topic_bonus=WIKI_TOPIC_BONUS)
    )
    answer, chunks, extra_queries, llm_metadata = adaptive_answer(question, chunks, preferred_paths)
    llm_metadata["selected_wiki_topics"] = selected_topic_ids
    llm_metadata["topic_selection"] = topic_metadata
    sources = cited_sources(answer, chunks)
    if not sources and ("Nie skonfigurowano klucza" in answer or "Nie udało się połączyć z Gemini" in answer):
        sources = chunks[:5]
    if TRACE_RAG and extra_queries:
        app.logger.info("[RAG] Dodatkowe zapytania: %s", extra_queries)
    if TRACE_RAG and selected_topic_ids:
        app.logger.info("[RAG] Preferowane tematy wiki: %s", selected_topic_ids)
    log_chat_trace(question, chunks, answer, sources, llm_metadata)
    return jsonify({"answer": answer, "sources": sources, "stats": kb.stats()})


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
