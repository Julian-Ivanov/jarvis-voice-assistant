# CLAUDE.md

Dieses Workspace ist **Jarvis** — ein persoenlicher KI-Assistent mit Sprachsteuerung, Browser-Kontrolle und Doppelklatschen-Trigger.

**Dieses Setup ist fuer macOS angepasst.** (Original-Template war fuer Windows.)

---

## Fuer Claude Code: Setup-Modus

Wenn der Nutzer nach dem Setup fragt oder "Richte Jarvis ein" sagt, folge den Anweisungen in `SETUP.md`. Frage den Nutzer nach seinem Namen, seiner Taetigkeit, und wie er angesprochen werden moechte — diese Infos muessen in den Systemprompt in `server.py` eingetragen werden (ersetze die aktuellen Platzhalter "Julian", "KI-Berater und Automatisierungsexperte", "Sir").

**WICHTIG — Pruefe und installiere zuerst alle Voraussetzungen (macOS):**

1. **Python**: Pruefe ob Python 3.10+ installiert ist (`python3 --version`). Falls nicht:
   - Empfehlung: Homebrew + `brew install python@3.12`
   - Falls Homebrew fehlt: `/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"`

2. **Google Chrome**: Pruefe mit `ls "/Applications/Google Chrome.app"`. Falls nicht installiert, weise den Nutzer auf https://google.com/chrome hin.

3. **pip Dependencies**: `pip3 install -r requirements.txt`

4. **Playwright Browser**: `python3 -m playwright install chromium`

5. **macOS-Berechtigungen** (muss der Nutzer manuell in *System Settings → Privacy & Security* erteilen):
   - **Screen Recording** fuer Terminal/Python — fuer `[ACTION:SCREEN]` (Screenshots)
   - **Microphone** fuer Terminal/Python — fuer Doppelklatschen-Erkennung
   - **Accessibility** fuer Terminal — fuer AppleScript-Fenstersteuerung in `launch-session.sh`

Erst NACHDEM alle Voraussetzungen installiert sind, fahre mit dem Setup in `SETUP.md` fort (API Keys abfragen, config.json erstellen, etc.).

---

## Workspace Structure

```
.
├── CLAUDE.md                  # This file
├── SETUP.md                   # Setup-Anleitung fuer Claude Code
├── config.json                # Persoenliche Config (gitignored)
├── config.example.json        # Template mit Platzhaltern
├── requirements.txt           # Python Dependencies
├── server.py                  # FastAPI Backend (Claude Haiku + ElevenLabs TTS)
├── browser_tools.py           # Playwright Browser-Steuerung (Mac/Win)
├── screen_capture.py          # Screenshot + Claude Vision
├── frontend/
│   ├── index.html             # Jarvis Web-UI
│   ├── main.js                # Speech Recognition + WebSocket + Audio
│   └── style.css              # Dark Theme mit Orb-Animation
└── scripts/
    ├── clap-trigger.py        # Doppelklatschen-Erkennung (Mac/Win)
    ├── launch-session.sh      # macOS Session-Launcher (bash + AppleScript)
    └── launch-session.ps1     # Windows Session-Launcher (legacy)
```
