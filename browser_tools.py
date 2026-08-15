"""
Jarvis V2 — Browser Tools
Web search via DuckDuckGo Lite, page visits via Playwright, URL opening.
"""

import asyncio
import platform
import re
import subprocess
import webbrowser
from urllib.parse import unquote, parse_qs, urlparse
import httpx
from playwright.async_api import async_playwright

_browser = None
_context = None
_browser_lock = asyncio.Lock()

IS_MAC = platform.system() == "Darwin"
IS_WINDOWS = platform.system() == "Windows"


def _bring_chromium_to_front():
    """Bring the Playwright Chromium window to the foreground."""
    try:
        if IS_MAC:
            subprocess.run([
                "osascript", "-e",
                'tell application "System Events" to set frontmost of '
                '(first process whose name contains "Chromium" or name contains "Chrome") to true'
            ], capture_output=True, timeout=3)
        elif IS_WINDOWS:
            subprocess.run([
                "powershell", "-Command",
                '(Get-Process -Name "chromium","chrome" -ErrorAction SilentlyContinue | '
                'Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -Last 1).MainWindowHandle | '
                'ForEach-Object { Add-Type "using System; using System.Runtime.InteropServices; '
                'public class W { [DllImport(\\\"user32.dll\\\")] public static extern bool SetForegroundWindow(IntPtr h); }"; '
                '[W]::SetForegroundWindow($_) }'
            ], capture_output=True, timeout=3)
    except Exception:
        pass


async def _get_browser():
    global _browser, _context
    async with _browser_lock:
        if _browser is None:
            pw = await async_playwright().start()
            _browser = await pw.chromium.launch(headless=False, args=["--start-maximized"])
            ua = (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
                if IS_MAC
                else "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            )
            _context = await _browser.new_context(
                user_agent=ua,
                no_viewport=True,
            )
    return _context


async def search_and_read(query: str) -> dict:
    """Search Google in visible browser, click first organic result, read the page.
    NOTE: We deliberately leave the page open so the Boss can see what was opened.
    Old pages from previous searches DO get cleaned up below to prevent Chromium leaks.
    """
    from urllib.parse import quote_plus
    ctx = await _get_browser()

    # Cleanup: keep at most the last 2 pages alive — close any older ones to prevent
    # tab buildup and memory leak across many searches.
    try:
        existing = list(ctx.pages)
        if len(existing) > 2:
            for old in existing[:-2]:
                try:
                    await old.close()
                except Exception:
                    pass
    except Exception:
        pass

    page = await ctx.new_page()
    try:
        # Google search — German results, ignore ads/sitelinks
        search_url = f"https://www.google.com/search?q={quote_plus(query)}&hl=de&gl=de"
        await page.goto(search_url, timeout=15000)
        _bring_chromium_to_front()
        await page.wait_for_timeout(1500)

        # Dismiss Google cookie consent banner if it appears
        for label in ["Alle akzeptieren", "Accept all", "Alle ablehnen", "Reject all"]:
            try:
                btn = page.get_by_role("button", name=label)
                if await btn.count() > 0:
                    await btn.first.click(timeout=2000)
                    await page.wait_for_timeout(800)
                    break
            except Exception:
                pass

        # Click first organic result. Google's structure: #search > result > <a><h3>...
        first_link = page.locator('#search a:has(h3)').first
        if await first_link.count() == 0:
            first_link = page.locator('div.g a h3').first  # fallback selector

        if await first_link.count() > 0:
            try:
                await first_link.click(timeout=5000)
            except Exception:
                # Result link may target _blank; navigate directly via href instead
                href = await first_link.get_attribute("href")
                if href:
                    await page.goto(href, timeout=15000, wait_until="domcontentloaded")
            await page.wait_for_timeout(2500)

            title = await page.title()
            url = page.url
            text = await page.evaluate("""
                () => {
                    const selectors = ['main', 'article', '[role="main"]', '.content', '#content', 'body'];
                    for (const sel of selectors) {
                        const el = document.querySelector(sel);
                        if (el && el.innerText.trim().length > 100) {
                            return el.innerText.trim();
                        }
                    }
                    return document.body?.innerText?.trim() || '';
                }
            """)
            return {"title": title, "url": url, "content": text[:3000]}
        else:
            return {"title": "Keine Ergebnisse", "url": search_url, "content": "Google lieferte keine Ergebnisse."}
    except Exception as e:
        return {"error": str(e), "url": query}


async def visit(url: str, max_chars: int = 5000) -> dict:
    """Visit a URL and extract main text content."""
    ctx = await _get_browser()
    page = await ctx.new_page()
    try:
        await page.goto(url, timeout=15000, wait_until="domcontentloaded")
        text = await page.evaluate("""
            () => {
                const selectors = ['main', 'article', '[role="main"]', '.content', '#content', 'body'];
                for (const sel of selectors) {
                    const el = document.querySelector(sel);
                    if (el && el.innerText.trim().length > 100) {
                        return el.innerText.trim();
                    }
                }
                return document.body?.innerText?.trim() || '';
            }
        """)
        title = await page.title()
        return {"title": title, "url": url, "content": text[:max_chars]}
    except Exception as e:
        return {"error": str(e), "url": url}
    finally:
        await page.close()


async def fetch_news() -> str:
    """Fetch current world news from worldmonitor.app in visible browser."""
    ctx = await _get_browser()
    page = await ctx.new_page()
    try:
        await page.goto("https://www.worldmonitor.app/", timeout=20000)
        _bring_chromium_to_front()
        await page.wait_for_timeout(6000)  # Wait for JS to render
        text = await page.evaluate("() => document.body.innerText")
        # Extract the news sections
        content = text[:4000]
        return f"World Monitor Nachrichten:\n{content}"
    except Exception as e:
        return f"News konnten nicht geladen werden: {e}"
    finally:
        pass  # Keep page open so user can see it


async def open_url(url: str):
    """Open URL in user's default browser (non-blocking)."""
    import asyncio
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, webbrowser.open, url)
    return {"success": True, "url": url}


async def close():
    global _browser, _context
    if _browser:
        await _browser.close()
        _browser = None
        _context = None
