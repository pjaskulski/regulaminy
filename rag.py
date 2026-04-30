from __future__ import annotations

import json
import math
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


WORD_RE = re.compile(r"[0-9A-Za-zÀ-ž_/-]+", re.UNICODE)
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
SECTION_RE = re.compile(r"^(?:§|\$)\s*(?P<number>\d+[a-zA-Z]?)\.?\s*(?P<title>.*)$")
DATE_RE = re.compile(r"(?P<date>(?:19|20)\d{2}[-_]\d{2}[-_]\d{2})")
CHANGE_RE = re.compile(
    r"\b(zmienia|zmieniaj[aą]ce|uchyla|uchyla si[eę]|aneks|otrzymuje nast[eę]puj[aą]ce brzmienie)\b",
    re.IGNORECASE,
)

STOPWORDS = {
    "a",
    "albo",
    "ale",
    "bez",
    "byc",
    "być",
    "czy",
    "dla",
    "do",
    "i",
    "ich",
    "jest",
    "lub",
    "na",
    "nie",
    "nr",
    "o",
    "od",
    "oraz",
    "po",
    "pod",
    "przez",
    "r",
    "roku",
    "sie",
    "się",
    "to",
    "w",
    "we",
    "z",
    "za",
    "ze",
}


PHRASE_PAIR_LEADING_SKIPWORDS = {"jak", "czy"}
PHRASE_PAIR_INSTITUTION_WORDS = {"instytucie", "instytutu", "historii", "pan"}


QUERY_EXPANSIONS = {
    "staż": ["wysługa", "wysługę", "wysluga", "wysluge", "wieloletnia", "wieloletnią", "okres", "zatrudnienia"],
    "staz": ["wysługa", "wysługę", "wysluga", "wysluge", "wieloletnia", "wieloletnią", "okres", "zatrudnienia"],
    "przejąć": ["dyrektor", "rada", "naukowa", "statut", "powołuje", "powołanie", "wybory"],
    "przejac": ["dyrektor", "rada", "naukowa", "statut", "powoluje", "powolanie", "wybory"],
    "władzę": ["dyrektor", "rada", "naukowa", "statut", "powołuje", "powołanie", "wybory"],
    "wladze": ["dyrektor", "rada", "naukowa", "statut", "powoluje", "powolanie", "wybory"],
    "władza": ["dyrektor", "rada", "naukowa", "statut", "powołuje", "powołanie", "wybory"],
    "wladza": ["dyrektor", "rada", "naukowa", "statut", "powoluje", "powolanie", "wybory"],
    "zmienić": ["zmiana", "odwołać", "odwołanie", "odwołuje", "odwotuje", "powołać", "powołanie", "powołuje", "powoluje", "powotuje", "konkurs", "kadencja"],
    "zmienic": ["zmiana", "odwolac", "odwolanie", "odwoluje", "odwotuje", "powolac", "powolanie", "powoluje", "powotuje", "konkurs", "kadencja"],
    "dyrektora": ["dyrektor", "dyrektorem", "dyrektorowi", "prezes", "akademii", "rada", "kuratorów", "kuratorow"],
    "dyrektor": ["dyrektora", "dyrektorem", "dyrektorowi", "prezes", "akademii", "rada", "kuratorów", "kuratorow"],
    "instytutu": ["instytut", "instytucie"],
    "instytut": ["instytutu", "instytucie"],
    "wynagrodzenia": ["wynagradzania", "wynagrodzenie", "wynagrodzeniu", "wynagrodzeń"],
    "wynagrodzenie": ["wynagradzania", "wynagrodzenia", "wynagrodzeniu", "wynagrodzeń"],
    "wysokość": ["wysokości", "wysokosc", "wysokosci"],
    "wysokosc": ["wysokość", "wysokości", "wysokosci"],
    "wpływa": ["zależy", "przysługuje", "uwzględnia"],
    "wplywa": ["zależy", "przysługuje", "uwzględnia"],
}


@dataclass
class Document:
    path: str
    title: str
    date: str
    kind: str
    is_change: bool


@dataclass
class Chunk:
    id: str
    path: str
    title: str
    date: str
    heading: str
    start_line: int
    end_line: int
    text: str
    is_change: bool


def normalize(text: str) -> str:
    return text.casefold()


def tokenize(text: str) -> list[str]:
    words = [normalize(match.group(0)) for match in WORD_RE.finditer(text)]
    return [word for word in words if len(word) > 2 and word not in STOPWORDS]


def expand_query_tokens(tokens: list[str]) -> list[str]:
    expanded: list[str] = []
    seen: set[str] = set()
    for token in tokens:
        for item in [token, *QUERY_EXPANSIONS.get(token, [])]:
            normalized = normalize(item)
            if normalized not in seen and len(normalized) > 2 and normalized not in STOPWORDS:
                expanded.append(normalized)
                seen.add(normalized)
    return expanded


def infer_date(path: Path, text: str) -> str:
    for source in (path.name, text[:1200]):
        match = DATE_RE.search(source)
        if match:
            return match.group("date").replace("_", "-")
    return "BRAK_DATY"


def infer_kind(title: str, filename: str) -> str:
    haystack = f"{title} {filename}".casefold()
    for kind in ("zarządzenie", "zarzadzenie", "regulamin", "instrukcja", "aneks", "decyzja", "uchwała"):
        if kind in haystack:
            return kind.replace("zarzadzenie", "zarządzenie").capitalize()
    return "Dokument"


def extract_title(path: Path, text: str) -> str:
    for line in text.splitlines()[:40]:
        match = HEADING_RE.match(line.strip())
        if match:
            return match.group(2).strip()
    return path.stem.replace("_", " ")


def iter_markdown_files(md_dir: Path) -> Iterable[Path]:
    yield from sorted(md_dir.glob("*.md"))


def split_document(path: Path, text: str) -> tuple[Document, list[Chunk]]:
    title = extract_title(path, text)
    date = infer_date(path, text)
    kind = infer_kind(title, path.name)
    is_change = bool(CHANGE_RE.search(f"{path.name}\n{text[:2500]}"))
    display_path = str(Path("md") / path.name)
    document = Document(display_path, title, date, kind, is_change)

    lines = text.splitlines()
    chunks: list[Chunk] = []
    current_heading = title
    current_start = 1
    current_lines: list[str] = []
    chunk_no = 1

    def flush(end_line: int) -> None:
        nonlocal chunk_no, current_lines
        body = "\n".join(current_lines).strip()
        if len(body) < 80:
            current_lines = []
            return
        chunks.append(
            Chunk(
                id=f"{path.name}:{chunk_no}",
                path=display_path,
                title=title,
                date=date,
                heading=current_heading,
                start_line=current_start,
                end_line=end_line,
                text=body,
                is_change=is_change,
            )
        )
        chunk_no += 1
        current_lines = []

    for idx, line in enumerate(lines, start=1):
        stripped = line.strip()
        heading = HEADING_RE.match(stripped)
        section = SECTION_RE.match(stripped)
        starts_new_section = (heading and heading.group(1) in {"##", "###", "####"}) or bool(section)
        too_large = sum(len(item) for item in current_lines) > 2600 and not line.strip()
        if (starts_new_section or too_large) and current_lines:
            flush(idx - 1)
            current_start = idx
        if heading:
            current_heading = heading.group(2).strip()
        elif section:
            suffix = section.group("title").strip()
            current_heading = f"§ {section.group('number')}{'. ' + suffix if suffix else ''}"
        current_lines.append(line)

    if current_lines:
        flush(len(lines))

    return document, chunks


class KnowledgeBase:
    def __init__(self, md_dir: Path):
        self.md_dir = md_dir
        self.documents: list[Document] = []
        self.chunks: list[Chunk] = []
        self._chunk_tokens: list[set[str]] = []
        self.reload()

    def reload(self) -> None:
        self.documents.clear()
        self.chunks.clear()
        for path in iter_markdown_files(self.md_dir):
            text = path.read_text(encoding="utf-8", errors="replace")
            document, chunks = split_document(path, text)
            self.documents.append(document)
            self.chunks.extend(chunks)
        self._chunk_tokens = [set(tokenize(chunk.text + " " + chunk.heading + " " + chunk.title)) for chunk in self.chunks]

    def stats(self) -> dict[str, int]:
        return {"documents": len(self.documents), "chunks": len(self.chunks)}

    def search(self, query: str, limit: int = 8) -> list[dict]:
        original_query_tokens = tokenize(query)
        query_tokens = expand_query_tokens(original_query_tokens)
        if not query_tokens:
            return []
        query_set = set(query_tokens)
        scored = []
        for chunk, tokens in zip(self.chunks, self._chunk_tokens):
            overlap = query_set & tokens
            if not overlap:
                continue
            phrase_bonus = 0.0
            lowered = normalize(chunk.text)
            lowered_haystack = normalize(f"{chunk.text} {chunk.heading} {chunk.title}")
            for term in query_tokens:
                if term in lowered:
                    phrase_bonus += 0.15
            for first, second in zip(original_query_tokens, original_query_tokens[1:]):
                if first in PHRASE_PAIR_LEADING_SKIPWORDS or second in PHRASE_PAIR_LEADING_SKIPWORDS:
                    continue
                if first in PHRASE_PAIR_INSTITUTION_WORDS and second in PHRASE_PAIR_INSTITUTION_WORDS:
                    continue
                if f"{first} {second}" in lowered_haystack:
                    phrase_bonus += 0.45
            recency_bonus = 0.2 if chunk.date >= "2024-01-01" else 0.0
            change_bonus = 0.25 if chunk.is_change else 0.0
            score = len(overlap) / math.sqrt(max(len(tokens), 1)) + phrase_bonus + recency_bonus + change_bonus
            scored.append((score, chunk))
        scored.sort(key=lambda item: (item[0], item[1].date), reverse=True)
        return [{"score": round(score, 4), **asdict(chunk)} for score, chunk in scored[:limit]]

    def as_json(self) -> str:
        return json.dumps([asdict(document) for document in self.documents], ensure_ascii=False, indent=2)
