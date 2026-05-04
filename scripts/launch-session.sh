#!/usr/bin/env bash
# Jarvis — Launch Session (macOS)
# Reads ../config.json, starts the Jarvis server, opens Spotify track + apps + Chrome,
# then snaps the four key windows into screen quadrants via AppleScript.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_PATH="$SCRIPT_DIR/../config.json"

if [[ ! -f "$CONFIG_PATH" ]]; then
    echo "[jarvis] config.json not found at $CONFIG_PATH" >&2
    exit 1
fi

# Pull values out of config.json with python3 (avoids jq dependency)
read_cfg() {
    python3 -c "import json,sys; print(json.load(open('$CONFIG_PATH')).get('$1',''))"
}

WORKSPACE_PATH="$(read_cfg workspace_path)"
SPOTIFY_URI="$(read_cfg spotify_track)"
BROWSER_URL="$(read_cfg browser_url)"

# Read apps array
APPS_JSON=$(python3 -c "import json; print('\n'.join(json.load(open('$CONFIG_PATH')).get('apps', [])))")

# 1. Start Jarvis server in a new Terminal window — only if not already running on port 8340
if lsof -iTCP:8340 -sTCP:LISTEN -nP 2>/dev/null | grep -q LISTEN; then
    echo "[jarvis] server already running on :8340 — skipping"
else
    osascript <<EOF
tell application "Terminal"
    activate
    do script "cd '$WORKSPACE_PATH' && python3 server.py"
end tell
EOF
fi

# 2. Spotify track (works for spotify: URIs and https://open.spotify.com links)
if [[ -n "$SPOTIFY_URI" ]]; then
    open "$SPOTIFY_URI" || true
fi

# 3. Open VS Code at workspace
if command -v code >/dev/null 2>&1; then
    code "$WORKSPACE_PATH" || true
else
    open -a "Visual Studio Code" "$WORKSPACE_PATH" 2>/dev/null || true
fi

# 4. Configured apps (URIs like obsidian:// or app names)
while IFS= read -r app; do
    [[ -z "$app" ]] && continue
    open "$app" 2>/dev/null || open -a "$app" 2>/dev/null || true
done <<< "$APPS_JSON"

# 5. Chrome with Jarvis UI + configured site — only open tabs that aren't already open
chrome_has_url() {
    osascript <<EOF 2>/dev/null
tell application "Google Chrome"
    if not running then return "no"
    repeat with w in windows
        repeat with t in tabs of w
            if URL of t starts with "$1" then return "yes"
        end repeat
    end repeat
    return "no"
end tell
EOF
}

if [[ "$(chrome_has_url 'http://localhost:8340')" != "yes" ]]; then
    open -a "Google Chrome" "http://localhost:8340" || true
fi
if [[ -n "$BROWSER_URL" && "$(chrome_has_url "$BROWSER_URL")" != "yes" ]]; then
    open -a "Google Chrome" "$BROWSER_URL" || true
fi

# 6. Wait for windows to appear, then snap into quadrants via AppleScript
sleep 3

osascript <<'EOF'
tell application "Finder" to set screenBounds to bounds of window of desktop
set screenW to item 3 of screenBounds
set screenH to item 4 of screenBounds
set halfW to screenW / 2
set halfH to screenH / 2

-- menu bar offset (~25px on most Macs)
set topOffset to 25

on snap(appName, x, y, w, h)
    try
        tell application "System Events"
            if exists (process appName) then
                tell process appName
                    if (count of windows) > 0 then
                        set position of front window to {x, y}
                        set size of front window to {w, h}
                    end if
                end tell
            end if
        end tell
    on error
        -- silently skip apps that can't be positioned
    end try
end snap

-- Top-left: VS Code
my snap("Code", 0, topOffset, halfW, halfH)

-- Top-right: Obsidian
my snap("Obsidian", halfW, topOffset, halfW, halfH)

-- Bottom-left: Chrome (Jarvis UI)
my snap("Google Chrome", 0, halfH + topOffset, halfW, halfH)

-- Bottom-right: Spotify
my snap("Spotify", halfW, halfH + topOffset, halfW, halfH)
EOF
