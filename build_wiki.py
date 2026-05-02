from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict
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
    "wynagrodzenia-płace-świadczenia": ["wynagrodzenia", "płace", "świadczenia", "pensja", "wynagradzania"],
    "organizacja-statut-rada-naukowa": [
        "statut",
        "regulamin organizacyjny",
        "rada naukowa",
        "wybory uzupełniające",
        "komisja dyscyplinarna",
        "rzecznik dyscyplinarny",
        "siedziba instytutu",
    ],
    "biblioteka-i-zbiory": ["biblioteka", "czytelnia", "wypożyczalnia", "skontrum", "zbiory biblioteki"],
    "wydawnictwa-i-czasopisma": ["wydawnictwo", "wydawniczy", "czasopismo", "produkcja czasopism", "komisja wydawnicza"],
    "wyjazdy-konferencje": ["wyjazdy", "przyjazdy", "konferencje naukowe"],
    "majatek-sprzet-inwentaryzacja-energia": [
        "majątek",
        "sprzęt",
        "sprzet",
        "inwentaryzacja",
        "energia",
        "okulary korekcyjne",
        "środki ochrony indywidualnej",
        "antresola",
    ],
    "szkola-doktorska-anthropos": ["Anthropos", "szkoła doktorska", "kierownik szkoły doktorskiej", "koordynator Anthropos"],
    "etyka-i-dyscyplina": ["kodeks etyki", "etyka pracownika naukowego", "dyscyplinarny", "rzecznik dyscyplinarny"],
    "wlasnosc-intelektualna": ["własność intelektualna", "wlasnosc intelektualna", "utwór", "utwor", "prawa autorskie", "otwarty mandat"],
    "wynajem-sal": ["wynajem sal", "sale konferencyjne", "sala konferencyjna"],
    "nostryfikacja": ["nostryfikacja", "opłata nostryfikacyjna", "oplata nostryfikacyjna"],
    "mobbing": ["mobbing", "procedura antymobbingowa", "dyskryminacja", "zachowania dyskryminacyjne"],
}


TOPIC_FILE_KEYWORDS = {
    "regulamin-pracy": [
        "regulamin_pracy",
        "czas_pracy",
        "rownowazny_system_czasu_pracy",
        "równoważny_system_czasu_pracy",
        "badan_lekarskich",
        "organizacja_pracy",
        "dni_wolne",
    ],
    "zfss": ["zfss", "funduszu_swiadczen_socjalnych", "komisji_socjalnej", "komisja_socjalna"],
    "zamowienia-publiczne": ["zamowien_publicznych", "zamowienia_publiczne", "komisja_przetargowa", "komisji_przetar"],
    "archiwum-i-kancelaria": ["archiwum", "kancelaryjna", "wykaz_akt"],
    "finanse-i-rachunkowosc": [
        "rachunkowosci",
        "rachunkowości",
        "kasowej",
        "obiegu_kontroli_dokumentow",
        "instrukcji_obiegu_dokumentow_ksiegowych",
        "faktura",
    ],
    "badania-i-konkursy": [
        "fundusz_badan",
        "funduszu_badan",
        "fbw",
        "konkursow",
        "konkurs",
        "projekty_badawcze",
        "finan_proj_badawczych",
        "oceny_pracownikow",
        "regulamin_odwoan_od_oceny",
    ],
    "bezpieczenstwo-i-dane": [
        "bezpieczenstwa",
        "bezpieczeństwa",
        "danych_osobowych",
        "pozarowego",
        "ppoż",
        "ppoz",
        "korupcji",
        "mobbing",
        "zgloszen_naruszen",
        "zgloszen_wewnetrznych",
        "dokonywania_zgloszen_narusze",
        "procedura_postepowania_zagrozenia",
        "stalego_dyzuru",
        "stałego_dyzuru",
    ],
    "wynagrodzenia-płace-świadczenia": [
        "wynagradzania",
        "wynagrodzenia",
        "regulaminu_wynagradzania",
        "zarzadzenie_10_2021",
        "place",
        "płace",
        "dni_wolne",
    ],
    "organizacja-statut-rada-naukowa": [
        "statutu",
        "statut",
        "regulamin_organizacyjny",
        "rada_naukowa",
        "rady_naukowej",
        "rn",
        "wybory",
        "wyborow",
        "komisja_dyscyplinarna",
        "rzecznik_dyscyplinarny",
        "siedziby",
        "jednoznacznej_form",
        "ustawa_o_polskiej_akademii_nauk",
        "poczta_sluzbowa",
        "uchylenie_regulaminow",
    ],
    "biblioteka-i-zbiory": ["biblioteki", "biblioteka", "skontrum_zbiorow"],
    "wydawnictwa-i-czasopisma": ["czasopism", "wydawniczej", "wydawniczy", "wydawnicza"],
    "wyjazdy-konferencje": ["wyjazdow", "wyjazdy", "przyjazdow", "konferencje"],
    "majatek-sprzet-inwentaryzacja-energia": [
        "inwentaryzacja",
        "sprzet",
        "energii",
        "okulary",
        "refundacji_kosztow_zakupu_okularow",
        "ochrony_indywidualnej",
        "antresoli",
    ],
    "szkola-doktorska-anthropos": ["anthropos"],
    "etyka-i-dyscyplina": ["kodeks_etyki", "komisja_dyscyplinarna", "rzecznik_dyscyplinarny"],
    "wlasnosc-intelektualna": [
        "wł_intel",
        "wl_intel",
        "wlasnosc_intelektualna",
        "własność_intelektualna",
        "otwartego_mandatu",
    ],
    "wynajem-sal": ["wynajmu_sal"],
    "nostryfikacja": ["nostryfikacja"],
    "mobbing": ["mobbing", "mobbingowi", "antymobbingowej", "dyskryminacyjnych", "regulamin_pracy_ih_pan", 
                "naruszen_prawa"],
}


EXACT_FILE_TOPICS = set(TOPICS)


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
    for topic, queries in sorted(TOPICS.items()):
        seen = set()
        if topic not in EXACT_FILE_TOPICS:
            for query in queries:
                for result in kb.search(query, limit=12):
                    key = result["path"]
                    if key not in seen:
                        grouped[topic].append(result)
                        seen.add(key)
        file_keywords = TOPIC_FILE_KEYWORDS.get(topic, [])
        for document in kb.documents:
            haystack = f"{document.path} {document.title}".replace("-", "_").casefold()
            if any(keyword.casefold() in haystack for keyword in file_keywords) and document.path not in seen:
                grouped[topic].append(asdict(document))
                seen.add(document.path)

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
