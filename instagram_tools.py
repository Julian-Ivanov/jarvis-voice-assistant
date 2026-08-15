"""
Jarvis V2 — Instagram via Playwright with persistent session.
First call asks the Boss to log in once; the session cookies are persisted
in a Chromium user-data dir, so subsequent calls just navigate where asked.
"""

import asyncio
import os
import subprocess
from playwright.async_api import async_playwright

# Persistent profile dir so login survives between sessions
IG_PROFILE_DIR = os.path.join(os.path.expanduser("~"), ".jarvis-instagram-profile")

_ig_browser = None
_ig_page = None


SECTION_URLS = {
    "home":          "https://www.instagram.com/",
    "dms":           "https://www.instagram.com/direct/inbox/",
    "messages":      "https://www.instagram.com/direct/inbox/",
    "notifications": "https://www.instagram.com/accounts/activity/",
    "explore":       "https://www.instagram.com/explore/",
    "reels":         "https://www.instagram.com/reels/",
}


async def _get_ig_browser():
    global _ig_browser, _ig_page
    if _ig_browser is None:
        os.makedirs(IG_PROFILE_DIR, exist_ok=True)
        pw = await async_playwright().start()
        _ig_browser = await pw.chromium.launch_persistent_context(
            IG_PROFILE_DIR,
            headless=False,
            args=["--start-maximized"],
            no_viewport=True,
        )
        if _ig_browser.pages:
            _ig_page = _ig_browser.pages[0]
        else:
            _ig_page = await _ig_browser.new_page()
    return _ig_page


def _bring_to_front():
    """Bring the IG browser window to focus (mac)."""
    try:
        subprocess.run([
            "osascript", "-e",
            'tell application "System Events" to set frontmost of '
            '(first process whose name contains "Chromium" or name contains "Chrome") to true'
        ], capture_output=True, timeout=3)
    except Exception:
        pass


async def open_section(section: str) -> str:
    """Open the requested IG section in the persistent browser.
    On first run, the Boss has to log in manually — session is saved after."""
    sec = (section or "home").strip().lower()
    url = SECTION_URLS.get(sec)
    if not url:
        # Treat as a username
        sec_clean = sec.lstrip("@").strip()
        url = f"https://www.instagram.com/{sec_clean}/"

    try:
        page = await _get_ig_browser()
        await page.goto(url, timeout=20000, wait_until="domcontentloaded")
        _bring_to_front()
        # Quick check: are we on the login page?
        await page.wait_for_timeout(1500)
        try:
            login_visible = await page.locator('input[name="username"]').count() > 0
        except Exception:
            login_visible = False
        if login_visible:
            return ("Instagram braucht Login — bitte einmal im Browser anmelden, "
                    "danach merkt sich Jarvis die Session.")
        return f"Instagram geoeffnet: {sec}"
    except Exception as e:
        return f"Instagram konnte nicht geoeffnet werden: {e}"


async def close():
    global _ig_browser, _ig_page
    if _ig_browser:
        await _ig_browser.close()
        _ig_browser = None
        _ig_page = None
