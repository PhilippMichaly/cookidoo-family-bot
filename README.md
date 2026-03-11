# Cookidoo Family Voting Bot 🍽

Ein Telegram-Bot, der Rezepte aus deinen Cookidoo-Sammlungen holt, die Familie per Inline-Buttons abstimmen lässt und dann automatisch eine Einkaufsliste erstellt.

## Ablauf

1. **Rezepte laden** – Der Bot holt Rezepte aus deinen Cookidoo-Sammlungen (managed + custom), filtert nach Schwierigkeitsgrad und wählt 5–10 zufällige Kandidaten aus.
2. **Abstimmung** – Die Kandidaten werden als Telegram-Nachricht mit Inline-Buttons an den Familien-Chat geschickt.
3. **Stimmen sammeln** – Über einen konfigurierbaren Zeitraum (Standard: 2 Stunden) werden die Stimmen eingesammelt. Jeder darf einmal wählen (Umentscheiden erlaubt).
4. **Gewinner verkünden** – Das Gewinnerrezept wird mit Einkaufsliste im Chat gepostet.
5. **Cookidoo-Einkaufsliste** – Die Zutaten werden automatisch in die Cookidoo-Einkaufsliste eingetragen.

## Voraussetzungen

- Python 3.11+
- Ein Cookidoo-Abo (Thermomix)
- Ein Telegram-Bot (erstellt über [@BotFather](https://t.me/BotFather))
- Der Bot muss Mitglied im Familien-Gruppenchat sein

## Setup

### 1. Telegram-Bot einrichten

Falls noch nicht geschehen:
1. Öffne [@BotFather](https://t.me/BotFather) in Telegram
2. Sende `/newbot` und folge den Anweisungen
3. Notiere dir den **Bot-Token**

### 2. Familien-Gruppenchat vorbereiten

1. Erstelle eine Telegram-Gruppe (oder verwende eine bestehende)
2. Füge den Bot als Mitglied hinzu
3. Sende eine Nachricht in der Gruppe
4. Führe `setup_chat_id.py` aus, um die Chat-ID zu ermitteln:
   ```bash
   python3 setup_chat_id.py
   ```

### 3. Umgebungsvariablen setzen

```bash
export COOKIDOO_EMAIL="deine@email.de"
export COOKIDOO_PASSWORD="dein-passwort"
export COOKIDOO_COUNTRY="de"
export COOKIDOO_LANGUAGE="de-DE"
export COOKIDOO_URL="https://cookidoo.de/foundation/de-DE"
export TELEGRAM_CHAT_ID="123456789"

# Optional:
export NUM_RECIPE_CANDIDATES="7"        # Anzahl Vorschläge (5-10)
export VOTING_DURATION_MINUTES="120"    # Abstimmungsdauer in Minuten
export MAX_DIFFICULTY="medium"          # easy, medium, difficult
```

### 4. Abhängigkeiten installieren

```bash
pip install -r requirements.txt
```

### 5. Bot starten

```bash
python3 bot.py
```

## Dateien

| Datei | Beschreibung |
|-------|-------------|
| `bot.py` | Hauptskript – orchestriert den gesamten Ablauf |
| `cookidoo_client.py` | Cookidoo-API-Wrapper – Rezepte laden, Einkaufsliste erstellen |
| `telegram_client.py` | Telegram-Funktionen – Abstimmung senden, Stimmen sammeln |
| `config.py` | Konfiguration aus Umgebungsvariablen |
| `setup_chat_id.py` | Hilfsskript zum Ermitteln der Telegram-Chat-ID |

## Schwierigkeitsfilter

- `easy` – Nur einfache Rezepte
- `medium` – Einfache + mittlere Rezepte (Standard)
- `difficult` – Alle Rezepte

## Hinweise

- Der Bot verwendet die [cookidoo-api](https://github.com/miaucl/cookidoo-api) (MIT-Lizenz)
- Zum Sammeln der Zutaten werden Rezepte kurzzeitig zur Einkaufsliste hinzugefügt und wieder entfernt
- Das Gewinnerrezept wird am Ende dauerhaft in die Cookidoo-Einkaufsliste eingetragen
- Die bisherige Einkaufsliste wird dabei geleert – bei Bedarf vorher Einkäufe erledigen!
