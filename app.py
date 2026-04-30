from __future__ import annotations

import hmac
import logging
import re
from pathlib import Path

from flask import Flask, jsonify, redirect, render_template, request, session, url_for
from werkzeug.middleware.proxy_fix import ProxyFix

from config import APP_TITLE, AUTH_PASSWORD, AUTH_USERNAME, MD_DIR, SEARCH_LIMIT, SECRET_KEY, TRACE_RAG, TRACE_RAG_FULL
from llm import answer_with_gemini_details, attach_source_ids, build_context, cited_sources
from rag import KnowledgeBase


app = Flask(__name__)
app.secret_key = SECRET_KEY
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)
kb = KnowledgeBase(MD_DIR)
if TRACE_RAG:
    app.logger.setLevel(logging.INFO)


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


def adaptive_answer(question: str, chunks: list[dict]) -> tuple[str, list[dict], list[str], dict]:
    result = answer_with_gemini_details(question, chunks)
    answer = result.text
    if not answer_needs_more_context(answer):
        return answer, chunks, [], result.metadata | {"retried": result.retried}

    queries = followup_queries(question, answer)
    if not queries:
        return answer, chunks, [], result.metadata | {"retried": result.retried}

    extra_chunks: list[dict] = []
    for query in queries:
        extra_chunks.extend(kb.search(query, limit=4))

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
    return render_template(
        "documents.html",
        title=APP_TITLE,
        documents=sorted(kb.documents, key=lambda document: (document.date, document.title), reverse=True),
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
    chunks = attach_source_ids(kb.search(question, limit=SEARCH_LIMIT))
    answer, chunks, extra_queries, llm_metadata = adaptive_answer(question, chunks)
    sources = cited_sources(answer, chunks)
    if not sources and ("Nie skonfigurowano klucza" in answer or "Nie udało się połączyć z Gemini" in answer):
        sources = chunks[:5]
    if TRACE_RAG and extra_queries:
        app.logger.info("[RAG] Dodatkowe zapytania: %s", extra_queries)
    log_chat_trace(question, chunks, answer, sources, llm_metadata)
    return jsonify({"answer": answer, "sources": sources, "stats": kb.stats()})


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
