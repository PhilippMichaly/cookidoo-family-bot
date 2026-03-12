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
