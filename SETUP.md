# Jarvis Setup Guide

Dein persoenlicher KI-Assistent — inspiriert von Iron Mans Jarvis.

**Was du bekommst:**
- Zweimal klatschen → dein komplettes Arbeits-Setup startet
- Jarvis begruesst dich mit Wetter und deinen Aufgaben
- Du sprichst frei mit Jarvis — er antwortet per Stimme
- Jarvis kann deinen Browser steuern (suchen, Seiten oeffnen)
- Jarvis kann deinen Bildschirm sehen und beschreiben

---

## Voraussetzungen

- **macOS 12+** (auf Apple Silicon und Intel getestet)
- **Google Chrome** (fuer Spracheingabe + Jarvis UI)
- **Claude Code** installiert

Python, alle Dependencies und Browser-Treiber werden automatisch von Claude Code installiert. Du musst lediglich nach dem Setup einmalig die macOS-Systemberechtigungen erteilen (siehe unten).

---

## Setup starten

Oeffne diesen Ordner in VS Code, starte Claude Code, und sag:

> Richte Jarvis fuer mich ein.

Claude Code fragt dich dann nach:

1. **Dein Name** Sir
2. **Anthropic API Key** — von https://console.anthropic.com (fuer Claude Haiku, das Gehirn)
3. **ElevenLabs API Key** — von https://elevenlabs.io (fuer die Stimme)
4. **Spotify-Song** — Link zum Song der beim Start spielen soll
5. **Programme** — welche Apps sollen beim Doppelklatschen starten?
6. **Website** — welche Seite soll im Browser aufgehen?
7. **Stadt fuers Wetter** — z.B. Hamburg
8. **Obsidian Vault** — optional, welcher Ordner soll Jarvis kennen?

---

## Was Claude Code fuer dich einrichtet

### 1. Voraussetzungen installieren
Claude Code prueft und installiert automatisch:
- **Python 3.10+** (falls nicht vorhanden, via Homebrew: `brew install python@3.12`)
- **Alle Python-Pakete** (`pip3 install -r requirements.txt`)
- **Playwright Chromium** (`python3 -m playwright install chromium`)

### 1b. macOS-Berechtigungen (manuell vom Nutzer)
Damit Jarvis Mikrofon, Bildschirm und Fenstersteuerung nutzen darf, muessen folgende Berechtigungen erteilt werden in *System Settings → Privacy & Security*:
- **Microphone** → Terminal (oder iTerm/VS Code, je nachdem wo du Jarvis startest)
- **Screen Recording** → Terminal (fuer `[ACTION:SCREEN]`)
- **Accessibility** → Terminal (fuer AppleScript-Fensterpositionierung)

macOS fragt beim ersten Start automatisch — einfach erlauben.

### 2. config.json erstellen
Claude Code erstellt `config.json` aus `config.example.json` mit deinen echten Daten:
```json
{
  "anthropic_api_key": "sk-ant-...",
  "elevenlabs_api_key": "sk_...",
  "elevenlabs_voice_id": "VOICE_ID",
  "user_name": "Dein Name",
  "user_address": "Sir",
  "city": "Hamburg",
  "workspace_path": "/Users/deinuser/path/to/jarvis-voice-assistant",
  "spotify_track": "spotify:track:DEIN_TRACK_ID",
  "browser_url": "https://deine-website.com",
  "obsidian_inbox_path": "/Users/deinuser/path/to/obsidian/inbox",
  "apps": ["obsidian://open"]
}
```

### 3. ElevenLabs Stimme
Eine deutsche Stimme auswaehlen und die Voice ID in die Config eintragen. Empfehlung: **Felix Serenitas** (Starter Plan noetig) oder eine der Standard-Stimmen (Free Plan).

### 4. Systemprompt
Der Systemprompt wird in `server.py` automatisch aus der Config generiert. Er enthaelt:
- Jarvis-Persoenlichkeit (trocken, sarkastisch, britisch-hoeflich)
- Siezen mit gewaehlter Anrede
- Wetter- und Aufgaben-Integration
- Browser-Steuerung via Action-Tags
- Screen-Capture-Faehigkeit

---

## Architektur

```
Mikrofon (Chrome) → Web Speech API → WebSocket → FastAPI Server
                                                      ↓
                                                Claude Haiku (denkt)
                                                      ↓
                                    ┌─────────────────┼──────────────────┐
                                    ↓                 ↓                  ↓
                            ElevenLabs TTS     Playwright Browser   Screen Capture
                            (spricht)          (sucht/oeffnet)     (sieht Bildschirm)
                                    ↓
                            Audio → Browser Speaker
```

---

## Starten

### Jarvis manuell starten
```
python3 server.py
```
Dann http://localhost:8340 in Chrome oeffnen.

### Alles per Doppelklatschen starten
```
python3 scripts/clap-trigger.py
```
Zweimal klatschen → Spotify, VS Code, Obsidian, Chrome mit Jarvis starten automatisch und werden in Quadranten angeordnet.

### Clap Trigger beim macOS-Login

**WICHTIG — macOS TCC-Stolperstein:** Wenn `clap-trigger.py` direkt ueber `launchd` (LaunchAgent) gestartet wird, bekommt der Python-Prozess **stillschweigend kein Mikrofon-Audio** (alle RMS-Werte sind 0.0), weil launchd-Prozesse keinen TCC-Permission-Prompt zeigen koennen. Loesung: ueber **Terminal.app** starten — Terminal hat bereits Mikrofon-Berechtigung, und das Python-Kind erbt sie.

Im Repo liegt dafuer `scripts/clap-listener.command` — ein bash-Wrapper, der genau das macht.

**Empfohlener Setup (Login Item):**
1. *System Settings → General → Login Items & Extensions → Open at Login*
2. **+** → waehle `scripts/clap-listener.command` aus dem Projektordner
3. Beim ersten Start klatschen → macOS fragt evtl. nach Mikrofon-Berechtigung fuer Terminal → **Erlauben**

**Alternative (launchd LaunchAgent):**
Plist-Datei `~/Library/LaunchAgents/com.jarvis.clap.plist` mit `ProgramArguments`:
```
/usr/bin/open -a Terminal /Pfad/zu/scripts/clap-listener.command
```
Mit `RunAtLoad=true` und `KeepAlive=false`. Das `open -a Terminal` ist entscheidend — ohne den Terminal-Wrapper bekommt der Listener silent silence statt Audio.

Aktivieren: `launchctl load ~/Library/LaunchAgents/com.jarvis.clap.plist`

---

## Was Jarvis kann

- **"Wie ist das Wetter?"** → kennt das aktuelle Wetter
- **"Such nach MiroFish"** → oeffnet Browser, sucht, liest Ergebnisse
- **"Oeffne skool.com"** → oeffnet die Seite im Browser
- **"Was siehst du auf meinem Bildschirm?"** → macht Screenshot, beschreibt was er sieht
- **Jede Frage** → antwortet im Jarvis-Stil mit Stimme

---

## Fehlerbehebung

| Problem | Loesung |
|---|---|
| Jarvis spricht nicht | Pruefen ob Server laeuft (`python3 server.py`) und Chrome offen ist |
| "Verbindung verloren" | Alter Server-Prozess laeuft noch → `pkill -f "python.*server.py"` und neu starten |
| Klatschen wird nicht erkannt | Threshold in `clap-trigger.py` anpassen, oder Mikrofon-Berechtigung pruefen (System Settings → Privacy & Security → Microphone) |
| Screenshot leer / schwarz | Screen-Recording-Berechtigung fehlt fuer Terminal/Python (System Settings → Privacy & Security → Screen Recording) |
| Fenster-Snapping funktioniert nicht | Accessibility-Berechtigung fuer Terminal fehlt (System Settings → Privacy & Security → Accessibility) |
| Browser-Suche geht nicht | `python3 -m playwright install chromium` ausfuehren |
| Kein Audio im Browser | Einmal auf die Seite klicken (Chrome Autoplay-Policy) |

---

## Fuer Claude Code: Setup-Anweisungen

Wenn ein Nutzer "Richte Jarvis ein" sagt, fuehre folgende Schritte aus:

**Schritt 0 — Voraussetzungen pruefen und installieren (macOS):**
- Pruefe ob Python 3.10+ installiert ist: `python3 --version`
- Falls nicht: `brew install python@3.12` — warte bis fertig, pruefe erneut
- Falls Homebrew fehlt: `/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"`
- Pruefe ob Google Chrome installiert ist (`ls "/Applications/Google Chrome.app"`). Falls nicht, weise den Nutzer auf https://google.com/chrome hin
- Installiere Python-Pakete: `pip3 install -r requirements.txt`
- Installiere Playwright Browser: `python3 -m playwright install chromium`
- Weise den Nutzer auf die noetigen macOS-Berechtigungen hin (Microphone, Screen Recording, Accessibility — siehe Abschnitt 1b)

**Schritt 1 — Nutzerdaten abfragen:**
Frage nach:
- Name (z.B. "Julian")
- Taetigkeit/Rolle (z.B. "KI-Berater und Automatisierungsexperte") — wird in den Systemprompt eingebaut
- Gewuenschte Anrede (z.B. "Sir", "Chef", oder einfach Vorname)
- Anthropic API Key (von https://console.anthropic.com)
- ElevenLabs API Key (von https://elevenlabs.io)
- Spotify-Song (Link zum Song der beim Start spielen soll)
- Programme die beim Doppelklatschen starten sollen (z.B. Obsidian, Notion)
- Website die im Browser aufgehen soll
- Stadt fuers Wetter (z.B. Hamburg)
- Obsidian Vault Pfad (optional)

**Schritt 2 — Config erstellen:**
Erstelle `config.json` aus `config.example.json` mit den Nutzerdaten. Setze den `workspace_path` auf den aktuellen Ordnerpfad.

**Schritt 3 — ElevenLabs Stimme einrichten:**
- Liste verfuegbare Stimmen via ElevenLabs API
- Empfehle eine deutsche Stimme
- Trage die Voice ID in die Config ein

**Schritt 4 — Systemprompt anpassen:**
Oeffne `server.py` und finde die Funktion `build_system_prompt()`. Dort steht der komplette Systemprompt als f-String. Ersetze ALLE Vorkommen der folgenden Werte im gesamten Prompt-Text:
- Jedes "Julian" → Name des Nutzers (kommt mehrfach vor im Prompt!)
- "KI-Berater und Automatisierungsexperte" → Taetigkeit/Rolle des Nutzers
- Jedes "Sir" als Anrede → gewuenschte Anrede des Nutzers
- "Hamburg" → Stadt des Nutzers

Ausserdem oben in `server.py` bei den Config-Defaults:
- `USER_NAME = config.get("user_name", "Julian")` → Default-Name anpassen
- `CITY = config.get("city", "Hamburg")` → Default-Stadt anpassen

WICHTIG: Pruefe den Prompt sorgfaeltig — "Julian" und "Sir" kommen an mehreren Stellen vor. Alle muessen ersetzt werden.

**Schritt 5 — Testen:**
- Starte den Server: `python3 server.py`
- Oeffne http://localhost:8340 in Chrome
- Pruefe ob Jarvis spricht und antwortet

**Schritt 6 — Optional: Autostart einrichten (macOS Login Items oder launchd LaunchAgent)**

---

## Credits

Template von Julian — [Skool Community](https://skool.com/ki-automatisierung)
