# Cookidoo Family Voting Bot 🍽

Ein Telegram-Bot für Familien mit Thermomix: Jeden Tag schlägt der Bot Rezepte aus euren Cookidoo-Sammlungen vor, die Familie stimmt per Knopfdruck ab, und das Gewinner-Rezept landet automatisch auf der Einkaufsliste.

## Features

- **Rezeptvorschläge** aus euren eigenen Cookidoo-Sammlungen (managed + custom)
- **Inline-Button-Abstimmung** in der Telegram-Familiengruppe
- **Eine Stimme pro Person** – erster Klick zählt
- **Automatische Einkaufsliste** – wird direkt in Cookidoo eingetragen
- **Schwierigkeitsfilter** – keine "schweren" Rezepte (konfigurierbar)
- **Süßspeisen-Filter** – filtert Desserts heraus (mit Ausnahme-Whitelist)
- **Rezept-Historie** – Gewinner der letzten 14 Tage werden nicht erneut vorgeschlagen
- **Stichentscheid** – bei Gleichstand wird zufällig gelost und transparent angezeigt
- **Abstimmungszeit verlängern** – „Liste bis 17:00 laufen lassen“ direkt im Chat
- **Feature-Requests per Chat** – `/wunsch`, `/feature` oder `/idee` im Gruppenchat

## Voraussetzungen

- Python 3.11+
- Ein [Cookidoo-Abo](https://cookidoo.de) (Thermomix)
- Ein Telegram-Bot-Token (kostenlos über [@BotFather](https://t.me/BotFather))

## Schnellstart

### 1. Repository klonen

```bash
git clone https://github.com/PhilippMichaly/cookidoo-family-bot.git
cd cookidoo-family-bot
```

### 2. Abhängigkeiten installieren

```bash
pip install -r requirements.txt
```

### 3. Telegram-Bot erstellen

1. Öffne [@BotFather](https://t.me/BotFather) in Telegram
2. Sende `/newbot` und folge den Anweisungen
3. Kopiere den **Bot-Token** (sieht aus wie `123456789:ABCdef...`)
4. Füge den Bot zu deiner Familiengruppe hinzu

### 4. Konfiguration

Kopiere die Beispiel-Datei und trage deine Werte ein:

```bash
cp .env.example .env
nano .env   # oder dein Editor
```

Mindestens nötig:
- `COOKIDOO_EMAIL` – Deine Cookidoo-E-Mail
- `COOKIDOO_PASSWORD` – Dein Cookidoo-Passwort
- `TELEGRAM_BOT_TOKEN` – Token von @BotFather
- `TELEGRAM_CHAT_ID` – ID der Familiengruppe

### 5. Chat-ID ermitteln

```bash
python3 setup_chat_id.py
```

Sende dann eine Nachricht in der Gruppe – das Skript zeigt die Chat-ID an.

### 6. Bot starten

**Einmaliger Durchlauf** (Abstimmung senden → warten → Ergebnis):
```bash
python3 bot.py
```

**Oder als Zwei-Phasen-Setup** (z.B. für Cron/Systemd):
```bash
# Morgens: Abstimmung senden
python3 run_vote.py

# 2 Stunden später: Ergebnis auswerten
python3 tally_votes.py
```

## Zeitgesteuert betreiben (Cron / Systemd)

Der Bot ist dafür ausgelegt, zeitgesteuert zu laufen – kein dauerhafter Daemon nötig.

### Beispiel mit Cron

```cron
# Jeden Morgen um 07:00 Abstimmung senden
0 7 * * * cd /opt/cookidoo-bot && /opt/cookidoo-bot/venv/bin/python3 run_vote.py

# Um 09:00 Ergebnis auswerten
0 9 * * * cd /opt/cookidoo-bot && /opt/cookidoo-bot/venv/bin/python3 tally_votes.py
```

### Beispiel mit Systemd Timer

Siehe das [Self-Hosting Konzept](docs/) für eine vollständige Anleitung mit Podman, Systemd und Monitoring.

## Dateien

| Datei | Beschreibung |
|-------|-------------|
| `bot.py` | All-in-One: Abstimmung senden → warten → Ergebnis (für manuelle Tests) |
| `run_vote.py` | Phase 1: Rezepte holen, Abstimmung senden, State speichern |
| `tally_votes.py` | Phase 2: Stimmen auswerten, Gewinner verkünden, Einkaufsliste |
| `cookidoo_client.py` | Cookidoo-API-Wrapper – Rezepte laden, filtern, Einkaufsliste |
| `telegram_client.py` | Telegram Bot API – Nachrichten, Inline-Buttons, Voting |
| `voting.py` | Gewinner-Ermittlung mit Stichentscheid (Tie-Breaking) |
| `feature_listener.py` | Prüft auf `/wunsch`-Kommandos im Chat |
| `feature_requests.py` | Parst Sonderbefehle (z.B. Abstimmungszeit verlängern) |
| `config.py` | Konfiguration aus Umgebungsvariablen / `.env` |
| `setup_chat_id.py` | Hilfsskript zum Ermitteln der Telegram-Chat-ID |
| `.env.example` | Vorlage für die Konfigurationsdatei |

## Konfiguration

Alle Einstellungen erfolgen über Umgebungsvariablen oder die `.env`-Datei:

| Variable | Pflicht | Beschreibung | Standard |
|----------|---------|-------------|----------|
| `COOKIDOO_EMAIL` | ✅ | Cookidoo-Login-E-Mail | – |
| `COOKIDOO_PASSWORD` | ✅ | Cookidoo-Passwort | – |
| `TELEGRAM_BOT_TOKEN` | ✅ | Bot-Token von @BotFather | – |
| `TELEGRAM_CHAT_ID` | ✅ | Chat-ID der Familiengruppe | – |
| `COOKIDOO_COUNTRY` | | Ländercode | `de` |
| `COOKIDOO_LANGUAGE` | | Sprache | `de-DE` |
| `COOKIDOO_URL` | | Cookidoo-URL | `https://cookidoo.de/foundation/de-DE` |
| `NUM_RECIPE_CANDIDATES` | | Anzahl Vorschläge | `7` |
| `VOTING_DURATION_MINUTES` | | Abstimmungsdauer (Minuten) | `120` |
| `VOTING_DURATION_MAX_MINUTES` | | Max. Verlängerung per Chat (Minuten) | `720` |
| `MAX_DIFFICULTY` | | Max. Schwierigkeit (`easy`/`medium`/`difficult`) | `medium` |
| `RECIPE_HISTORY_DAYS` | | Tage, in denen Gewinner nicht wiederholt werden | `14` |

## Süßspeisen-Filter

Der Bot filtert automatisch Desserts und Süßspeisen heraus, basierend auf:
- Cookidoo-Kategorien (Desserts, Backen süß)
- Schlüsselwörtern im Rezeptnamen (Kuchen, Torte, Muffin, ...)

**Ausnahmen** (in `SWEET_WHITELIST` in `cookidoo_client.py`):
- Kaiserschmarrn
- Milchreis

Du kannst die Whitelist jederzeit in `cookidoo_client.py` anpassen.

## Feature-Requests per Chat

Familienmitglieder können im Gruppenchat Wünsche äußern:

```
/wunsch Rezepte nach Saison filtern
/feature Portionen anpassen können
/idee Nur vegetarische Rezepte zur Auswahl
```

Der Bot bestätigt den Eingang und gibt die Requests als JSON aus (`feature_listener.py`), damit sie weiterverarbeitet werden können.

## Abhängigkeiten

- [cookidoo-api](https://github.com/miaucl/cookidoo-api) – Inoffizielle Python-Bibliothek für die Cookidoo-API (MIT-Lizenz)
- [requests](https://docs.python-requests.org/) – HTTP-Requests für die Telegram Bot API
- [aiohttp](https://docs.aiohttp.org/) – Async HTTP für die Cookidoo-API
- [python-dotenv](https://github.com/theskumar/python-dotenv) – `.env`-Datei laden (optional, aber empfohlen)

## Lizenz

MIT
