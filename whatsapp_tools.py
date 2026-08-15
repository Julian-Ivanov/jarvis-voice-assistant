"""
Jarvis — WhatsApp Web via Playwright with persistent session.
First call shows the QR code; after scanning, the session is saved in a
Chromium user-data dir so subsequent calls skip the QR entirely.
"""

import asyncio
import os
import subprocess
from playwright.async_api import async_playwright, BrowserContext, Page

WA_PROFILE_DIR = os.path.join(os.path.expanduser("~"), ".jarvis-whatsapp-profile")
WA_URL = "https://web.whatsapp.com"

_context: BrowserContext | None = None
_page: Page | None = None
_lock = asyncio.Lock()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _bring_to_front() -> None:
    """Raise the Chromium window on macOS."""
    try:
        subprocess.run(
            [
                "osascript",
                "-e",
                'tell application "System Events" to set frontmost of '
                '(first process whose name contains "Chromium" or name contains "Chrome") to true',
            ],
            capture_output=True,
            timeout=3,
        )
    except Exception:
        pass


async def _get_page() -> Page:
    """Return the shared WhatsApp page, launching the browser if needed."""
    global _context, _page
    async with _lock:
        if _context is None:
            os.makedirs(WA_PROFILE_DIR, exist_ok=True)
            pw = await async_playwright().start()
            _context = await pw.chromium.launch_persistent_context(
                WA_PROFILE_DIR,
                headless=False,
                args=["--start-maximized"],
                no_viewport=True,
            )
        if _page is None or _page.is_closed():
            _page = _context.pages[0] if _context.pages else await _context.new_page()
    return _page


async def _is_qr_visible(page: Page) -> bool:
    """Return True when the QR canvas / landing screen is shown."""
    try:
        # WhatsApp Web shows a <canvas> or a div with data-testid="qrcode" before login
        qr = await page.locator('[data-testid="qrcode"], canvas').count()
        return qr > 0
    except Exception:
        return False


async def _wait_for_ready(page: Page, timeout_ms: int = 8_000) -> bool:
    """Return True when the main chat list is visible."""
    try:
        await page.locator('[data-testid="chat-list"]').wait_for(
            state="visible", timeout=timeout_ms
        )
        return True
    except Exception:
        return False


async def _find_chat(page: Page, contact: str) -> bool:
    """Search for a contact and click the first result. Returns True on success."""
    for sel in (
        'div[contenteditable="true"][data-tab="3"]',
        '[placeholder="Suchen oder neuen Chat beginnen"]',
        '[placeholder="Search or start new chat"]',
        '[data-testid="chat-list-search"]',
    ):
        loc = page.locator(sel).first
        try:
            if await loc.count() > 0:
                search_box = loc
                break
        except Exception:
            continue
    else:
        return False

    await search_box.click()
    await search_box.fill("")
    await page.wait_for_timeout(300)
    await search_box.type(contact, delay=60)
    await page.wait_for_timeout(1_500)

    result = page.locator('[data-testid="cell-frame-container"]').first
    try:
        await result.wait_for(state="visible", timeout=6_000)
        await result.click()
        await page.wait_for_timeout(800)
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def open_whatsapp() -> str:
    """Navigate to WhatsApp Web.

    Returns:
        "QR_SCAN_REQUIRED" if the user needs to scan the QR code,
        "READY" if already logged in.
    """
    page = await _get_page()

    if page.url.startswith(WA_URL):
        # Already on WhatsApp — check state without a full reload
        if await _wait_for_ready(page, timeout_ms=4_000):
            return "READY"
    else:
        await page.goto(WA_URL, timeout=20_000, wait_until="domcontentloaded")

    _bring_to_front()
    await page.wait_for_timeout(2_000)

    if await _wait_for_ready(page, timeout_ms=6_000):
        return "READY"

    if await _is_qr_visible(page):
        _bring_to_front()
        return "QR_SCAN_REQUIRED"

    # Intermediate loading state — give it a bit more time
    if await _wait_for_ready(page, timeout_ms=15_000):
        return "READY"

    return "QR_SCAN_REQUIRED"


async def list_unread_chats(limit: int = 10) -> list[dict]:
    """Return up to *limit* chats that have unread messages.

    Each entry: ``{"name": str, "preview": str, "unread_count": int}``
    """
    page = await _get_page()
    chats: list[dict] = []
    try:
        rows = page.locator('[data-testid="cell-frame-container"]')
        count = min(await rows.count(), limit * 3)
        for i in range(count):
            if len(chats) >= limit:
                break
            row = rows.nth(i)
            try:
                badge = row.locator('[data-testid="icon-unread-count"]')
                if await badge.count() == 0:
                    continue
                badge_text = (await badge.first.inner_text()).strip()
                unread = int(badge_text) if badge_text.isdigit() else 1
                name_el = row.locator('[data-testid="cell-frame-title"]').first
                name = (await name_el.inner_text()).strip() if await name_el.count() > 0 else "Unknown"
                preview_el = row.locator(
                    '[data-testid="last-msg-status"] + span, [data-testid="cell-frame-secondary"]'
                ).first
                preview = (await preview_el.inner_text()).strip() if await preview_el.count() > 0 else ""
                chats.append({"name": name, "preview": preview, "unread_count": unread})
            except Exception:
                continue
    except Exception:
        pass
    return chats


async def read_chat(contact: str, count: int = 10) -> list[dict]:
    """Return the last *count* messages from the conversation with *contact*.

    Each entry: ``{"from": "me" | "them", "text": str, "time": str}``
    """
    page = await _get_page()
    messages: list[dict] = []

    if not await _find_chat(page, contact):
        return messages

    try:
        # Message rows: outgoing have data-testid="msg-container" with class containing "message-out"
        msg_rows = page.locator('[data-testid="msg-container"]')
        total = await msg_rows.count()
        start = max(0, total - count)

        for i in range(start, total):
            row = msg_rows.nth(i)
            try:
                classes = await row.get_attribute("class") or ""
                direction = "me" if "message-out" in classes else "them"

                text_el = row.locator('[data-testid="msg-text"] span.selectable-text').first
                text = ""
                if await text_el.count() > 0:
                    text = (await text_el.inner_text()).strip()

                time_el = row.locator('[data-testid="msg-meta"] span').first
                time_str = ""
                if await time_el.count() > 0:
                    time_str = (await time_el.inner_text()).strip()

                if text:
                    messages.append({"from": direction, "text": text, "time": time_str})
            except Exception:
                continue
    except Exception:
        pass

    return messages


async def send_message(contact: str, text: str) -> bool:
    """Send *text* to *contact* via WhatsApp Web.

    Navigates to the chat by name search, types the message, presses Enter,
    then polls the conversation to confirm the message appeared.

    Returns:
        True if the message was confirmed sent, False otherwise.
    """
    page = await _get_page()

    if not await _find_chat(page, contact):
        return False

    try:
        # Message input box
        input_box = page.locator(
            '[data-testid="conversation-compose-box-input"],'
            ' div[contenteditable="true"][data-tab="10"]'
        ).first
        await input_box.wait_for(state="visible", timeout=7_000)
        await input_box.click()
        await input_box.type(text, delay=40)
        await page.keyboard.press("Enter")
        await page.wait_for_timeout(1_500)

        # Verify: look for the sent text among the last few outgoing messages
        msg_rows = page.locator('[data-testid="msg-container"]')
        total = await msg_rows.count()
        check_from = max(0, total - 5)

        for i in range(check_from, total):
            row = msg_rows.nth(i)
            try:
                classes = await row.get_attribute("class") or ""
                if "message-out" not in classes:
                    continue
                text_el = row.locator('[data-testid="msg-text"] span.selectable-text').first
                if await text_el.count() > 0:
                    sent_text = (await text_el.inner_text()).strip()
                    if text.strip() in sent_text:
                        return True
            except Exception:
                continue
    except Exception:
        pass

    return False


async def close_whatsapp() -> None:
    """Close the persistent WhatsApp browser context."""
    global _context, _page
    async with _lock:
        if _context is not None:
            await _context.close()
            _context = None
            _page = None
