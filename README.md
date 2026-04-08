# J.A.R.V.I.S. — Personal AI Voice Assistant

> Double-clap. Jarvis wakes up, greets you with the weather and your tasks, answers your questions with dry British wit, controls your browser, and sees your screen.

Built entirely with [Claude Code](https://claude.ai/code) — no code written manually.

---

## Demo

https://github.com/user-attachments/assets/PLACEHOLDER

> *Replace with your demo video or GIF*

---

## Features

- **Double-Clap Trigger** — Clap twice and your entire workspace launches: Spotify, VS Code, Obsidian, Chrome with Jarvis UI
- **Voice Conversation** — Speak freely with Jarvis through your microphone. He listens, thinks, and responds with voice
- **Sarcastic British Butler** — Jarvis speaks German with the personality of Tony Stark's AI: dry, witty, and always one step ahead
- **Weather & Tasks** — On startup, Jarvis greets you with the current weather and a humorous summary of your open tasks from Obsidian
- **Browser Automation** — "Search for MiroFish" → Jarvis opens a real browser, navigates to the page, reads the content, and summarizes it for you
- **Screen Vision** — "What's on my screen?" → Jarvis takes a screenshot, analyzes it with Claude Vision, and describes what he sees
- **World News** — "What's happening in the world?" → Jarvis opens worldmonitor.app and summarizes current global events
- **Window Snapping** — All launched apps automatically snap into quadrants on your screen

---

## Architecture

```
You (speak) → Chrome Browser (Web Speech API) → FastAPI Server (local)
                                                       ↓
                                                Claude Haiku (thinks)
                                                       ↓
                                    ┌──────────────────┼───────────────────┐
                                    ↓                  ↓                   ↓
                             ElevenLabs TTS     Playwright Browser    Screen Capture
                             (speaks back)      (searches/opens)     (Claude Vision)
                                    ↓
                             Audio → Chrome → You (hear)
```

| Component | Technology | Purpose |
|-----------|-----------|---------|
| Speech Input | Web Speech API (Chrome) | Converts your voice to text |
| Server | FastAPI (Python) | Local orchestration — runs on your machine |
| Brain | Claude Haiku (Anthropic) | Thinks, decides, formulates responses |
| Voice | ElevenLabs TTS | Converts text to natural German speech |
| Browser Control | Playwright | Automates a real browser you can see |
| Screen Vision | Claude Vision + Pillow | Screenshots and describes your screen |
| Clap Detection | sounddevice + numpy | Listens for double-clap to launch everything |
| Window Management | PowerShell + Win32 API | Snaps windows into screen quadrants |

---

## Prerequisites

- **Windows 10/11**
- **Python 3.10+**
- **Google Chrome**
- **[Claude Code](https://claude.ai/code)** (recommended for setup)

### API Keys Needed

| Service | What For | Cost | Link |
|---------|----------|------|------|
| Anthropic | Claude Haiku (the brain) | ~$0.25 / 1M tokens | [console.anthropic.com](https://console.anthropic.com) |
| ElevenLabs | Voice (text-to-speech) | Free tier: 10k chars/month | [elevenlabs.io](https://elevenlabs.io) |

---

## Quick Start

### Option A: Setup with Claude Code (Recommended)

1. Clone the repo:
   ```bash
   git clone https://github.com/Julian-Ivanov/jarvis-voice-assistant.git
   cd jarvis-voice-assistant
   ```

2. Open in VS Code, start Claude Code, and say:
   ```
   Set up Jarvis for me.
   ```

3. Claude Code will ask for your API keys, name, preferences, and configure everything automatically.

### Option B: Manual Setup

1. **Clone and install dependencies:**
   ```bash
   git clone https://github.com/Julian-Ivanov/jarvis-voice-assistant.git
   cd jarvis-voice-assistant
   pip install -r requirements.txt
   playwright install chromium
   ```

2. **Create `config.json`** from the template:
   ```bash
   cp config.example.json config.json
   ```

3. **Edit `config.json`** with your API keys and preferences:
   ```json
   {
     "anthropic_api_key": "sk-ant-...",
     "elevenlabs_api_key": "sk_...",
     "elevenlabs_voice_id": "YOUR_VOICE_ID",
     "user_name": "Your Name",
     "user_address": "Sir",
     "city": "Hamburg",
     "workspace_path": "C:\\path\\to\\jarvis-voice-assistant",
     "spotify_track": "spotify:track:YOUR_TRACK_ID",
     "browser_url": "https://your-website.com",
     "obsidian_inbox_path": "C:\\path\\to\\obsidian\\inbox",
     "apps": ["obsidian://open"]
   }
   ```

4. **Start Jarvis:**
   ```bash
   python server.py
   ```

5. **Open Chrome** and go to `http://localhost:8340`

6. **Click anywhere** on the page, then speak!

---

## Usage

### Start Jarvis manually
```bash
python server.py
```
Then open `http://localhost:8340` in Chrome.

### Start everything with a double-clap
```bash
python scripts/clap-trigger.py
```
Clap twice → Spotify plays your song, VS Code opens, Obsidian opens, Chrome opens with Jarvis. All windows snap into quadrants.

### Auto-start on Windows login
1. Open Task Scheduler (`Win + R` → `taskschd.msc`)
2. Create Task → Trigger: "At log on"
3. Action: `powershell` with argument:
   ```
   -ExecutionPolicy Bypass -Command "python C:\path\to\scripts\clap-trigger.py"
   ```

---

## What You Can Say

| Command | What Happens |
|---------|-------------|
| *"Good morning, Jarvis"* | Jarvis greets you with weather + tasks |
| *"Search for AI news"* | Opens browser, searches, summarizes results |
| *"Open skool.com"* | Opens the URL in your browser |
| *"What's on my screen?"* | Takes screenshot, describes what he sees |
| *"What's happening in the world?"* | Opens worldmonitor.app, summarizes global news |
| *Any question* | Jarvis answers in his sarcastic butler style |

---

## Project Structure

```
jarvis-voice-assistant/
├── server.py              # FastAPI backend — the brain
├── browser_tools.py       # Playwright browser automation
├── screen_capture.py      # Screenshot + Claude Vision
├── config.json            # Your personal config (gitignored)
├── config.example.json    # Template for new users
├── requirements.txt       # Python dependencies
├── frontend/
│   ├── index.html         # Jarvis web UI
│   ├── main.js            # Speech recognition + WebSocket + audio
│   └── style.css          # Dark theme with animated orb
├── scripts/
│   ├── clap-trigger.py    # Double-clap detection
│   └── launch-session.ps1 # Launches all apps + window snapping
├── CLAUDE.md              # Instructions for Claude Code
└── SETUP.md               # Detailed setup guide
```

---

## Customization

### Change Jarvis's personality
Edit the system prompt in `server.py` → `build_system_prompt()`. The personality, greeting behavior, and action instructions are all defined there.

### Change which apps launch
Edit `config.json`:
```json
{
  "spotify_track": "spotify:track:YOUR_TRACK_ID",
  "browser_url": "https://your-website.com",
  "apps": ["obsidian://open", "slack://"]
}
```

### Change the voice
Find a voice on [elevenlabs.io](https://elevenlabs.io), copy the Voice ID, and set it in `config.json`:
```json
{
  "elevenlabs_voice_id": "YOUR_VOICE_ID"
}
```

### Change the weather city
```json
{
  "city": "Berlin"
}
```

### Adjust clap sensitivity
In `scripts/clap-trigger.py`:
```python
THRESHOLD = 0.15  # Lower = more sensitive
MAX_GAP = 1.2     # Seconds between claps
```

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Jarvis doesn't speak | Check if server is running. Kill old process: `taskkill /f /im python.exe` then restart |
| "Connection lost" in browser | Old server still running on port 8340. Kill it and restart |
| Clap not detected | Lower `THRESHOLD` in `clap-trigger.py` (try 0.10) |
| Browser search fails | Run `playwright install chromium` |
| No audio in Chrome | Click anywhere on the page first (Chrome autoplay policy) |
| Jarvis says "Sir planen" instead of "Sie planen" | Update the system prompt grammar rules in `server.py` |

---

## Mac Users

This template is built for Windows. If you're on macOS, clone the repo and tell Claude Code:

```
Convert this project to work on macOS.
```

Claude Code will adapt the PowerShell scripts to shell scripts, adjust paths, and handle macOS-specific differences.

---

## Tech Stack

- **[FastAPI](https://fastapi.tiangolo.com/)** — Python web framework for the local server
- **[Claude Haiku](https://anthropic.com)** — Fast, affordable AI model (the brain)
- **[ElevenLabs](https://elevenlabs.io)** — Natural text-to-speech (the voice)
- **[Playwright](https://playwright.dev)** — Browser automation
- **[Web Speech API](https://developer.mozilla.org/en-US/docs/Web/API/Web_Speech_API)** — Browser-native speech recognition
- **[sounddevice](https://python-sounddevice.readthedocs.io/)** — Audio input for clap detection

---

## Credits

Built by [Julian](https://skool.com/ki-automatisierung) with [Claude Code](https://claude.ai/code).

Inspired by Iron Man's J.A.R.V.I.S. — *"At your service, Sir."*

---

## License

MIT — use it, modify it, build on it. If you build something cool, let me know!
