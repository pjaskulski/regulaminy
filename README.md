# regulaminy
Asystent regulaminów i zarządzeń IH PAN

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
