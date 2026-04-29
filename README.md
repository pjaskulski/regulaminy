# regulaminy
Asysten regulaminów i zarządzeń IH PAN

## Uruchomienie lokalne

```bash
source venv/bin/activate
python app.py
```

## Konfiguracja

Utwórz plik `.env` na podstawie `.env.example` i ustaw co najmniej:

```text
AUTH_USERNAME=regulaminy
AUTH_PASSWORD=ustaw_wspolne_haslo
SECRET_KEY=ustaw_dlugi_losowy_klucz_sesji
GOOGLE_API_KEY=uzupelnij_klucz
```

`SECRET_KEY` powinien być losowy i inny niż hasło użytkownika.

## Wdrożenie pod `/regulaminy/`

Jeśli aplikacja działa za nginx pod ścieżką `/regulaminy/`, uruchom gunicorn na lokalnym porcie,
np. `127.0.0.1:8010`, a w nginx użyj konfiguracji z obcięciem prefiksu i nagłówkiem
`X-Forwarded-Prefix`:

```nginx
location = /regulaminy {
    return 301 /regulaminy/;
}

location /regulaminy/ {
    proxy_pass http://127.0.0.1:8010/;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-Prefix /regulaminy;
}
```

Końcowy ukośnik w `proxy_pass http://127.0.0.1:8010/;` jest istotny: nginx przekaże wtedy
do Flask ścieżki bez prefiksu, a Flask wygeneruje linki z prefiksem dzięki
`X-Forwarded-Prefix`.

Przykładowe uruchomienie przez gunicorn:

```bash
source venv/bin/activate
gunicorn -w 2 -b 127.0.0.1:8010 app:app
```
