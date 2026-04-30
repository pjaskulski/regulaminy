# regulaminy
AI Asystent regulaminów i zarządzeń IH PAN

## Uruchomienie lokalne

```bash
source venv/bin/activate
python app.py
```

Przykładowe uruchomienie przez gunicorn:

```bash
source venv/bin/activate
gunicorn -w 2 -b 127.0.0.1:8010 app:app
```

## Diagnostyka wyszukiwania

Żeby sprawdzić, jakie fragmenty dokumentów zostały znalezione dla pytania i jakie źródła trafiły do odpowiedzi, można włączyć log RAG:

```bash
REGULAMINY_TRACE_RAG=1 python app.py
```

Wartości `full`, `verbose` albo `context` dopisują do logu także pełny kontekst przekazany do modelu i pełną odpowiedź:

```bash
REGULAMINY_TRACE_RAG=full python app.py
```

Jeżeli pierwsza odpowiedź modelu wskazuje, że brakuje źródeł, aplikacja wykonuje jeden dodatkowy przebieg wyszukiwania na podstawie brakujących dokumentów i pojęć wymienionych w odpowiedzi, a następnie generuje odpowiedź ponownie z poszerzonym kontekstem.

W logu diagnostycznym zapisywane są też metadane odpowiedzi Gemini, w tym `finish_reasons` i liczby tokenów. Limit odpowiedzi można zmienić zmienną:

```bash
GEMINI_MAX_OUTPUT_TOKENS=4000 python app.py
```
