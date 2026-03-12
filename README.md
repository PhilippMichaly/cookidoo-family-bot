# Cookidoo Family Voting Bot v2

Telegram-Bot für Familien mit Thermomix: Rezeptvorschläge aus Cookidoo, Abstimmung per Inline-Buttons, Gewinner → Einkaufsliste.

## Was ist neu in v2?

- **SQLite-Cache**: Rezepte werden einmal pro Tag synchronisiert → tägliche Votes brauchen **null Cookidoo-API-Calls** bis zum Gewinner
- **Webhook-Modus**: Kein Polling mehr — Telegram pusht Updates direkt (oder Polling als Fallback)
- **Live-Stimmenzähler**: Vote-Message zeigt live die Anzahl Stimmen pro Rezept
- **Stimme änderbar**: Letzter Klick zählt, keine frustrierende "erster Klick ist final"-Logik
- **Vote-Bestätigung**: Toast-Notification bei jedem Vote ("✓ Stimme registriert!")
- **`/config` im Chat**: Alle Einstellungen live änderbar durch Admins
- **Rezeptbilder**: Erster Kandidat mit Thumbnail in der Vote-Message
- **Docker-Ready**: Dockerfile + Compose für einfaches Self-Hosting
- **Ein Entrypoint**: `cli.py` mit Subcommands statt 4 separate Scripts
- **Token-effizient**: Filter-Keywords ausgelagert, kein duplizierter Boilerplate
- **Nur aiohttp**: `requests`-Dependency entfernt, alles async

## Schnellstart

### Docker (empfohlen)

```bash
cp .env.example .env
# .env ausfüllen
docker compose up -d
```

### Lokal

```bash
pip install -r requirements.txt
cp .env.example .env
# .env ausfüllen

# Webhook-Modus (empfohlen wenn öffentliche URL vorhanden):
python cli.py serve

# Polling-Modus (keine öffentliche URL nötig):
python cli.py poll

# Einmaliger Durchlauf:
python cli.py vote

# Cache manuell aktualisieren:
python cli.py sync
```

## Telegram-Befehle

| Befehl | Beschreibung |
|--------|-------------|
| `/config show` | Aktuelle Konfiguration anzeigen |
| `/config anzahl 5` | 5 Vorschläge statt 7 |
| `/config ende 17:00` | Abstimmung endet um 17:00 |
| `/config dauer 90` | 90 Minuten Abstimmungsdauer |
| `/config schwierigkeit leicht` | Nur einfache Rezepte |
| `/config filter desserts aus` | Süßspeisen erlauben |
| `/config filter drinks an` | Getränke ausfiltern |
| `/config historie 7` | Gewinner 7 Tage nicht wiederholen |
| `/config reset` | Alle Überschreibungen zurücksetzen |
| `/status` | Bot-Status anzeigen |
| `/vote` | Abstimmung manuell starten |
| `/sync` | Rezept-Cache aktualisieren |
| `/wunsch ...` | Feature-Wunsch einreichen |

Admin-Befehle (`/config`, `/vote`, `/sync`) können auf bestimmte User beschränkt werden via `ADMIN_USER_IDS` in `.env`.

## Architektur

```
cli.py               → Zentraler Entrypoint
config.py            → Env-Vars + Runtime-Overrides
runtime_config.py    → /config Handler + JSON-Persistenz
cache.py             → SQLite Rezept-Cache
cookidoo_client.py   → Nur noch Shopping-List (3 API-Calls)
telegram_client.py   → Async TG-Client (aiohttp)
webhook_server.py    → Webhook + Scheduler + Command-Router
voting.py            → Gewinner-Logik
filters.json         → Externe Keyword-Listen
```

### API-Call-Vergleich

| Aktion | v1 | v2 |
|--------|----|----|
| Täglicher Vote | ~25 Calls | 0 (Cache) |
| Cache-Sync (1x/Tag) | — | ~N Calls (einmalig) |
| Gewinner → Einkaufsliste | 3 Calls | 3 Calls |
| Vote-Polling (2h) | ~720 Calls | 0 (Webhook) |

## Konfiguration

Alle Einstellungen in `.env` (siehe `.env.example`). Zusätzlich können viele Werte live per `/config` im Telegram-Chat überschrieben werden — diese werden in `data/runtime_config.json` gespeichert und überleben Neustarts.

### Filter anpassen

Die Keyword-Listen für Süßspeisen/Getränke-Filter liegen in `filters.json` und können ohne Code-Änderung angepasst werden.

## Datenverzeichnis

Alle persistenten Daten liegen in `data/` (bzw. `DATA_DIR`):

- `recipe_cache.db` — SQLite mit allen Rezepten
- `runtime_config.json` — Überschreibungen aus `/config`
- `recipe_history.json` — Gewinner-Historie (Legacy, jetzt in SQLite)

Im Docker-Setup wird `data/` als benanntes Volume gemountet.

---

## Self-Hosting mit Docker (Schritt-für-Schritt)

Diese Anleitung bringt den Bot auf einem beliebigen Linux-Server (Raspberry Pi, VPS, NAS, Homelab) zum Laufen. Voraussetzung: Docker und Docker Compose sind installiert.

### 1. Telegram-Bot erstellen

```bash
# In Telegram: @BotFather öffnen und /newbot senden.
# Einen Namen und Username vergeben.
# Den Bot-Token kopieren (sieht aus wie 123456789:ABCdef...).
# Den Bot in die Familiengruppe einladen.
```

### 2. Chat-ID ermitteln

```bash
# Nachricht in die Familiengruppe senden, dann:
curl -s "https://api.telegram.org/bot<DEIN_BOT_TOKEN>/getUpdates" | python3 -m json.tool

# In der Ausgabe nach "chat":{"id": suchen.
# Gruppen-IDs sind negativ, z.B. -100123456789
```

### 3. Eigene User-ID ermitteln (für Admin-Rechte)

```bash
# Dem Bot eine private Nachricht senden, dann:
curl -s "https://api.telegram.org/bot<DEIN_BOT_TOKEN>/getUpdates" | python3 -m json.tool

# Unter "from":{"id": steht deine User-ID (positiv, z.B. 123456789)
```

### 4. Repo klonen und konfigurieren

```bash
git clone https://github.com/PhilippMichaly/cookidoo-family-bot.git
cd cookidoo-family-bot
git checkout v2-refactor
cp .env.example .env
```

### 5. `.env` ausfüllen

```bash
nano .env
```

Minimal-Konfiguration — diese 4 Werte müssen rein:

```env
COOKIDOO_EMAIL=deine@email.de
COOKIDOO_PASSWORD=dein-cookidoo-passwort
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz
TELEGRAM_CHAT_ID=-100123456789
```

Empfohlene Zusatzeinstellungen:

```env
# Deine TG User-ID — nur du kannst /config, /vote, /sync nutzen
ADMIN_USER_IDS=123456789

# Abstimmung endet jeden Tag um 15:00
VOTING_END_TIME_LOCAL=15:00

# 5 Rezeptvorschläge statt 7
NUM_RECIPE_CANDIDATES=5
```

### 6. Starten

**Variante A: Polling-Modus (einfachster Weg, keine Portfreigabe nötig)**

```bash
docker compose run --rm bot poll
```

Oder als Daemon im Hintergrund:

```bash
# docker-compose.yml anpassen: CMD ["poll"] statt CMD ["serve"]
docker compose up -d
```

**Variante B: Webhook-Modus (effizienter, braucht öffentliche URL)**

Wenn dein Server über eine Domain erreichbar ist (z.B. via Reverse Proxy, Cloudflare Tunnel, oder direkte Portfreigabe):

```env
# In .env ergänzen:
WEBHOOK_URL=https://deine-domain.de:8443
WEBHOOK_PORT=8443
```

```bash
docker compose up -d
```

### 7. Prüfen ob es läuft

```bash
# Logs anschauen
docker compose logs -f

# Health-Check (nur Webhook-Modus)
curl http://localhost:8443/health
# → "ok"

# Im Telegram-Chat:
/status
```

### 8. Erster Cache-Sync

Beim allerersten Start synchronisiert der Bot automatisch alle Rezepte aus deinen Cookidoo-Sammlungen. Das kann je nach Anzahl der Rezepte 2–10 Minuten dauern. Du kannst es auch manuell anstoßen:

```
/sync
```

### Nützliche Docker-Befehle

```bash
# Bot stoppen
docker compose down

# Bot neu starten (z.B. nach .env-Änderung)
docker compose up -d --force-recreate

# Logs live verfolgen
docker compose logs -f bot

# In den Container schauen
docker compose exec bot bash

# Cache-Datenbank inspizieren
docker compose exec bot sqlite3 /data/recipe_cache.db "SELECT count(*) FROM recipes;"

# Alles zurücksetzen (Cache, Historie, Config)
docker compose down -v
docker compose up -d
```

### Reverse Proxy (optional, für Webhook-Modus)

Falls du Nginx, Caddy oder Traefik nutzt, hier ein Beispiel für **Caddy** (automatisches HTTPS):

```
# Caddyfile
cookidoo-bot.deine-domain.de {
    reverse_proxy localhost:8443
}
```

```env
# .env
WEBHOOK_URL=https://cookidoo-bot.deine-domain.de
WEBHOOK_PORT=8443
```

Für **Nginx**:

```nginx
server {
    listen 443 ssl;
    server_name cookidoo-bot.deine-domain.de;

    ssl_certificate     /etc/letsencrypt/live/cookidoo-bot.deine-domain.de/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/cookidoo-bot.deine-domain.de/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8443;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

### Raspberry Pi / ARM

Das Dockerfile nutzt `python:3.12-slim`, das auch ARM-Images hat. Auf einem Raspberry Pi 4 funktioniert alles out of the box:

```bash
git clone https://github.com/PhilippMichaly/cookidoo-family-bot.git
cd cookidoo-family-bot && git checkout v2-refactor
cp .env.example .env && nano .env
docker compose up -d
```

### Auto-Update (optional)

Mit [Watchtower](https://github.com/containrrr/watchtower) kann der Container automatisch aktualisiert werden, wenn du ein neues Image baust:

```yaml
# In docker-compose.yml ergänzen:
services:
  watchtower:
    image: containrrr/watchtower
    restart: unless-stopped
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
    command: --interval 86400 bot
```

### Troubleshooting

| Problem | Lösung |
|---------|--------|
| `No recipes found` | `/sync` ausführen — Cache ist leer |
| `Telegram API error 401` | Bot-Token prüfen |
| `Telegram API error 400: chat not found` | Chat-ID prüfen, Bot muss in der Gruppe sein |
| `Cookidoo login failed` | E-Mail/Passwort prüfen, Cookidoo-Abo aktiv? |
| `Cache stale` warnung | Normal — Sync läuft automatisch alle 24h |
| Container startet nicht | `docker compose logs bot` für Details |
| Webhook bekommt keine Updates | URL erreichbar? `curl https://deine-domain.de:8443/health` |
| Polling-Modus: doppelte Nachrichten | Webhook vorher entfernen: Bot sendet automatisch `deleteWebhook` |
