from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from config import MD_DIR, WIKI_DIR
from rag import KnowledgeBase


TOPICS = {
    "regulamin-pracy": ["praca", "urlop", "czas pracy", "pracownik", "zdalna"],
    "zfss": ["zfss", "fundusz świadczeń", "socjaln"],
    "zamowienia-publiczne": ["zamówień publicznych", "zamowien publicznych", "przetarg"],
    "archiwum-i-kancelaria": ["archiwum", "kancelaryjna", "wykaz akt"],
    "finanse-i-rachunkowosc": ["rachunkowości", "rachunkowosci", "kasowej", "faktura", "księg"],
    "badania-i-konkursy": ["fundusz badań", "konkurs", "projekt badawczy", "oceny pracowników"],
    "bezpieczenstwo-i-dane": ["bezpieczeństwa", "danych osobowych", "pożar", "korupcji", "mobbing"],
}


def main() -> None:
    kb = KnowledgeBase(MD_DIR)
    WIKI_DIR.mkdir(exist_ok=True)

    index_lines = [
        "# Wiki regulaminów IH PAN",
        "",
        "To jest robocza warstwa orientacyjna. Źródłem prawdy pozostają pliki w `md/`.",
        "",
        f"Liczba dokumentów: {kb.stats()['documents']}",
        f"Liczba fragmentów: {kb.stats()['chunks']}",
        "",
        "## Tematy",
    ]

    grouped: dict[str, list[dict]] = defaultdict(list)
    for topic, queries in TOPICS.items():
        seen = set()
        for query in queries:
            for result in kb.search(query, limit=12):
                key = result["path"]
                if key not in seen:
                    grouped[topic].append(result)
                    seen.add(key)

    for topic, results in grouped.items():
        filename = f"{topic}.md"
        index_lines.append(f"- [{topic}]({filename})")
        lines = [
            f"# {topic.replace('-', ' ').title()}",
            "",
            "Ta strona jest automatycznie wygenerowaną mapą źródeł. Nie zastępuje dokumentów źródłowych.",
            "",
            "## Najbardziej powiązane dokumenty",
            "",
        ]
        for item in sorted(results, key=lambda row: row["date"], reverse=True):
            marker = " (zmiana/aneks/uchylenie)" if item["is_change"] else ""
            lines.append(f"- {item['date']} - `{item['path']}` - {item['title']}{marker}")
        (WIKI_DIR / filename).write_text("\n".join(lines) + "\n", encoding="utf-8")

    (WIKI_DIR / "index.md").write_text("\n".join(index_lines) + "\n", encoding="utf-8")
    print(f"Zbudowano wiki w {WIKI_DIR}")


if __name__ == "__main__":
    main()
