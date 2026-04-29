from __future__ import annotations

import re
from typing import Any

from config import GEMINI_MODEL, GOOGLE_API_KEY, MAX_CONTEXT_CHARS


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


def answer_with_gemini(question: str, chunks: list[dict[str, Any]]) -> str:
    if not GOOGLE_API_KEY:
        return fallback_answer(question, chunks)

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
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                systemInstruction=SYSTEM_INSTRUCTION,
                temperature=0.2,
                maxOutputTokens=1800,
            ),
        )
    except Exception as exc:
        return fallback_answer(
            question,
            chunks,
            reason=f"Nie udało się połączyć z Gemini (`{type(exc).__name__}`). Pokazuję najlepsze znalezione źródła.",
        )
    return response.text or "Model nie zwrócił treści odpowiedzi."
