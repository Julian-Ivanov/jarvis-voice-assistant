# J.A.R.V.I.S. — Personal AI Voice Assistant

> Double-clap. Jarvis wakes up, greets you with the weather and your tasks, answers your questions with dry British wit, controls your browser, and sees your screen.

Built entirely with [Claude Code](https://claude.ai/code) — no code written manually.

---

## Youtube Video

[Demo & Explaination](https://youtu.be/XsceN-hEit4)

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
| Window Management | AppleScript (macOS) / PowerShell + Win32 (Windows) | Snaps windows into screen quadrants |

---

## Prerequisites

- **macOS 12+** *(this fork)* or **Windows 10/11** *(original template — see legacy `launch-session.ps1`)*
- **Python 3.10+**
- **Google Chrome**
- **[Claude Code](https://claude.ai/code)** (recommended for setup)

### macOS-only — system permissions
Grant these once in *System Settings → Privacy & Security* before running Jarvis:
- **Microphone** for Terminal (clap detection)
- **Screen Recording** for Terminal (`[ACTION:SCREEN]` screenshots)
- **Accessibility** for Terminal (AppleScript window snapping)

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
   pip3 install -r requirements.txt
   python3 -m playwright install chromium
   ```

2. **Create `config.json`** from the template:
   ```bash
   cp config.example.json config.json
   ```

3. **Edit `config.json`** with your API keys and preferences (POSIX paths on macOS):
   ```json
   {
     "anthropic_api_key": "sk-ant-...",
     "elevenlabs_api_key": "sk_...",
     "elevenlabs_voice_id": "YOUR_VOICE_ID",
     "user_name": "Your Name",
     "user_address": "Sir",
     "city": "Hamburg",
     "workspace_path": "/Users/youruser/path/to/jarvis-voice-assistant",
     "spotify_track": "spotify:track:YOUR_TRACK_ID",
     "browser_url": "https://your-website.com",
     "obsidian_inbox_path": "/Users/youruser/path/to/obsidian/inbox",
     "apps": ["obsidian://open"]
   }
   ```

4. **Start Jarvis:**
   ```bash
   python3 server.py
   ```

5. **Open Chrome** and go to `http://localhost:8340`

6. **Click anywhere** on the page, then speak!

---

## Usage

### Start Jarvis manually
```bash
python3 server.py
```
Then open `http://localhost:8340` in Chrome.

### Start everything with a double-clap
```bash
python3 scripts/clap-trigger.py
```
Clap twice → Spotify plays your song, VS Code opens, Obsidian opens, Chrome opens with Jarvis. All windows snap into quadrants.

### Auto-start on macOS login
Easiest path: drop a small `.command` wrapper into *System Settings → General → Login Items*:
```bash
#!/usr/bin/env bash
cd "/Users/youruser/path/to/jarvis-voice-assistant"
/usr/bin/python3 scripts/clap-trigger.py
```
Make it executable: `chmod +x ~/jarvis-clap.command`

For a more robust option, use a `launchd` LaunchAgent at `~/Library/LaunchAgents/com.jarvis.clap.plist`.

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
│   ├── clap-trigger.py    # Double-clap detection (cross-platform)
│   ├── launch-session.sh  # macOS launcher (bash + AppleScript snapping)
│   └── launch-session.ps1 # Windows launcher (PowerShell + Win32)
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
| Jarvis doesn't speak | Check if server is running. Kill old process: `pkill -f "python.*server.py"` (macOS) / `taskkill /f /im python.exe` (Windows), then restart |
| "Connection lost" in browser | Old server still running on port 8340. Kill it and restart |
| Clap not detected | Lower `THRESHOLD` in `clap-trigger.py` (try 0.10), or grant Microphone permission to Terminal (macOS Privacy & Security) |
| Black screenshot from `[ACTION:SCREEN]` | Grant Screen Recording permission to Terminal/Python (macOS Privacy & Security) |
| Window snapping silently does nothing | Grant Accessibility permission to Terminal (macOS Privacy & Security) |
| Browser search fails | Run `python3 -m playwright install chromium` |
| No audio in Chrome | Click anywhere on the page first (Chrome autoplay policy) |
| Jarvis says "Sir planen" instead of "Sie planen" | Update the system prompt grammar rules in `server.py` |

---

## Platform Notes

This fork has been adapted for **macOS** (bash + AppleScript launcher, osascript-based browser focus, POSIX paths). The original PowerShell launcher (`launch-session.ps1`) is kept for Windows users — `clap-trigger.py` auto-detects the platform and runs the right one.

If you're on Linux, both launchers will fall back to `bash launch-session.sh`; tweak the AppleScript window-snapping block (it will be silently skipped on non-Mac systems) and use `xdotool`/`wmctrl` if you want quadrant snapping.

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
