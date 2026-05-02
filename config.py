import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


load_env_file(BASE_DIR / ".env")


def env_flag(name: str) -> bool:
    return os.getenv(name, "").casefold() in {"1", "true", "yes", "on", "full", "verbose", "context"}


MD_DIR = Path(os.getenv("REGULAMINY_MD_DIR", BASE_DIR / "md"))
WIKI_DIR = Path(os.getenv("REGULAMINY_WIKI_DIR", BASE_DIR / "wiki"))
STATE_DIR = Path(os.getenv("REGULAMINY_STATE_DIR", BASE_DIR / "state"))

APP_TITLE = os.getenv("REGULAMINY_APP_TITLE", "Asystent regulaminów i zarządzeń Instytutu Historii PAN")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3-flash-preview")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
AUTH_USERNAME = os.getenv("AUTH_USERNAME", "regulaminy")
AUTH_PASSWORD = os.getenv("AUTH_PASSWORD", "")
SECRET_KEY = os.getenv("SECRET_KEY", "dev-change-this-secret-key")

MAX_CONTEXT_CHARS = int(os.getenv("MAX_CONTEXT_CHARS", "18000"))
SEARCH_LIMIT = int(os.getenv("SEARCH_LIMIT", "8"))
WIKI_TOPIC_BONUS = float(os.getenv("WIKI_TOPIC_BONUS", "0.45"))
GEMINI_MAX_OUTPUT_TOKENS = int(os.getenv("GEMINI_MAX_OUTPUT_TOKENS", "3000"))
TRACE_RAG = env_flag("REGULAMINY_TRACE_RAG")
TRACE_RAG_FULL = os.getenv("REGULAMINY_TRACE_RAG", "").casefold() in {"full", "verbose", "context"}
