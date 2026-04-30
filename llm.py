from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from config import GEMINI_MAX_OUTPUT_TOKENS, GEMINI_MODEL, GOOGLE_API_KEY, MAX_CONTEXT_CHARS


SYSTEM_INSTRUCTION = """Jesteś asystentem IH PAN odpowiadającym na pytania o regulaminy, zarządzenia i instrukcje.
Odpowiadasz wyłącznie na podstawie przekazanych fragmentów dokumentów.
Jeśli fragmenty nie wystarczają do odpowiedzi, powiedz to wprost i wskaż, jakich źródeł brakuje.
Każde twierdzenie o treści dokumentów opatruj cytowaniem w formacie [S1], [S2] itd.
Jeśli korzystasz z kilku źródeł naraz, zapisz je jako [S1, S2], nie pomijając żadnego użytego identyfikatora.
Używaj wyłącznie identyfikatorów źródeł przekazanych w kontekście.
Jeśli źródło wygląda na dokument zmieniający, aneks albo uchylenie, wyraźnie to zaznacz.
Nie udzielasz porady prawnej; wyjaśniasz treść dokumentów wewnętrznych.
Odpowiadaj po polsku, rzeczowo i zwięźle."""


CITATION_RE = re.compile(r"\bS(?P<number>\d+)\b")


@dataclass
class GeminiAnswer:
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)
    retried: bool = False


def attach_source_ids(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{**chunk, "source_id": f"S{idx}"} for idx, chunk in enumerate(chunks, start=1)]


def cited_sources(answer: str, chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cited_ids = {f"S{match.group('number')}" for match in CITATION_RE.finditer(answer)}
    if not cited_ids:
        return []
    return [chunk for chunk in chunks if chunk.get("source_id") in cited_ids]


def build_context(chunks: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    total = 0
    for idx, chunk in enumerate(chunks, start=1):
        source_id = chunk.get("source_id") or f"S{idx}"
        header = (
            f"[{source_id}]\n"
            f"Tytuł: {chunk['title']}\n"
            f"Data: {chunk['date']}\n"
            f"Plik: {chunk['path']}\n"
            f"Sekcja: {chunk['heading']}\n"
            f"Linie: {chunk['start_line']}-{chunk['end_line']}\n"
            f"Dokument zmieniający/aneks/uchylenie: {'tak' if chunk['is_change'] else 'nie'}\n"
            "Treść:\n"
        )
        item = header + chunk["text"].strip()
        if total + len(item) > MAX_CONTEXT_CHARS:
            break
        parts.append(item)
        total += len(item)
    return "\n\n---\n\n".join(parts)


def fallback_answer(question: str, chunks: list[dict[str, Any]], reason: str | None = None) -> str:
    if not chunks:
        return "Nie znalazłem w dokumentach fragmentów, które pozwalają odpowiedzieć na to pytanie."
    message = reason or "Nie skonfigurowano klucza `GOOGLE_API_KEY`/`GEMINI_API_KEY`, więc pokazuję najlepsze znalezione źródła zamiast odpowiedzi modelu."
    lines = [message, "", "Najbardziej pasujące fragmenty:"]
    for idx, chunk in enumerate(chunks[:5], start=1):
        source_id = chunk.get("source_id") or f"S{idx}"
        snippet = " ".join(chunk["text"].split())[:450]
        lines.append(
            f"{idx}. [{source_id}] {chunk['title']} ({chunk['date']}), {chunk['heading']}, "
            f"{chunk['path']}:{chunk['start_line']} - {snippet}"
        )
    return "\n".join(lines)


def response_metadata(response: Any) -> dict[str, Any]:
    candidates = response.candidates or []
    finish_reasons = []
    finish_messages = []
    for candidate in candidates:
        reason = getattr(candidate, "finish_reason", None)
        finish_reasons.append(getattr(reason, "value", reason))
        finish_messages.append(getattr(candidate, "finish_message", None))

    usage = getattr(response, "usage_metadata", None)
    return {
        "model_version": getattr(response, "model_version", None),
        "finish_reasons": finish_reasons,
        "finish_messages": finish_messages,
        "prompt_token_count": getattr(usage, "prompt_token_count", None),
        "candidates_token_count": getattr(usage, "candidates_token_count", None),
        "total_token_count": getattr(usage, "total_token_count", None),
    }


def looks_incomplete(text: str, metadata: dict[str, Any]) -> bool:
    finish_reasons = {str(reason) for reason in metadata.get("finish_reasons") or []}
    if "MAX_TOKENS" in finish_reasons:
        return True
    stripped = text.rstrip()
    if not stripped:
        return True
    if stripped.endswith(("*", "-", "•", ":", ",", ";")):
        return True
    if re.search(r"(?:^|\n)\s*(?:[-*]|\d+[.)])\s*$", stripped):
        return True
    return False


def generate_answer(client: Any, types: Any, prompt: str) -> GeminiAnswer:
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            systemInstruction=SYSTEM_INSTRUCTION,
            temperature=0.2,
            maxOutputTokens=GEMINI_MAX_OUTPUT_TOKENS,
        ),
    )
    return GeminiAnswer(response.text or "Model nie zwrócił treści odpowiedzi.", response_metadata(response))


def answer_with_gemini_details(question: str, chunks: list[dict[str, Any]]) -> GeminiAnswer:
    if not GOOGLE_API_KEY:
        return GeminiAnswer(fallback_answer(question, chunks), {"fallback": "missing_api_key"})

    from google import genai
    from google.genai import types

    context = build_context(chunks)
    prompt = f"""Pytanie użytkownika:
{question}

Fragmenty dokumentów:
{context}

Przygotuj odpowiedź dla pracownika instytutu. Nie wychodź poza podane fragmenty."""

    client = genai.Client(api_key=GOOGLE_API_KEY)
    try:
        result = generate_answer(client, types, prompt)
        if looks_incomplete(result.text, result.metadata):
            retry_prompt = (
                f"{prompt}\n\n"
                "Poprzednia odpowiedź wyglądała na urwaną. Wygeneruj kompletną odpowiedź od początku. "
                "Nie kończ na rozpoczętej liście ani samotnym znaku wypunktowania."
            )
            retry_result = generate_answer(client, types, retry_prompt)
            retry_result.retried = True
            retry_result.metadata["first_attempt"] = result.metadata
            if looks_incomplete(retry_result.text, retry_result.metadata):
                retry_result.text = (
                    retry_result.text.rstrip()
                    + "\n\nUwaga: odpowiedź modelu wygląda na urwaną. Spróbuj ponowić pytanie albo sprawdź log `REGULAMINY_TRACE_RAG=1`."
                )
            return retry_result
    except Exception as exc:
        return GeminiAnswer(
            fallback_answer(
                question,
                chunks,
                reason=f"Nie udało się połączyć z Gemini (`{type(exc).__name__}`). Pokazuję najlepsze znalezione źródła.",
            ),
            {"fallback": "exception", "exception_type": type(exc).__name__},
        )
    return result


def answer_with_gemini(question: str, chunks: list[dict[str, Any]]) -> str:
    return answer_with_gemini_details(question, chunks).text
