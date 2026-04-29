from __future__ import annotations

import hmac
from pathlib import Path

from flask import Flask, jsonify, redirect, render_template, request, session, url_for
from werkzeug.middleware.proxy_fix import ProxyFix

from config import APP_TITLE, AUTH_PASSWORD, AUTH_USERNAME, MD_DIR, SEARCH_LIMIT, SECRET_KEY
from llm import answer_with_gemini, attach_source_ids, cited_sources
from rag import KnowledgeBase


app = Flask(__name__)
app.secret_key = SECRET_KEY
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)
kb = KnowledgeBase(MD_DIR)


def is_authenticated() -> bool:
    return bool(session.get("authenticated"))


def wants_json_response() -> bool:
    return request.path.startswith("/api/")


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
    answer = answer_with_gemini(question, chunks)
    sources = cited_sources(answer, chunks)
    if not sources and ("Nie skonfigurowano klucza" in answer or "Nie udało się połączyć z Gemini" in answer):
        sources = chunks[:5]
    return jsonify({"answer": answer, "sources": sources, "stats": kb.stats()})


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
