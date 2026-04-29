from __future__ import annotations

import argparse

from build_wiki import main as build_wiki
from config import MD_DIR
from rag import KnowledgeBase


def print_stats() -> None:
    kb = KnowledgeBase(MD_DIR)
    stats = kb.stats()
    print(f"Dokumenty: {stats['documents']}")
    print(f"Fragmenty: {stats['chunks']}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Administracja lokalnym indeksem regulaminów.")
    parser.add_argument(
        "command",
        choices=["stats", "build-wiki", "refresh"],
        help="stats: pokaż statystyki; build-wiki/refresh: przebuduj wiki pomocniczą",
    )
    args = parser.parse_args()

    if args.command == "stats":
        print_stats()
        return

    build_wiki()
    print_stats()


if __name__ == "__main__":
    main()
