"""
Jarvis V2 — Browser Tools
Web search via DuckDuckGo Lite, page visits via Playwright, URL opening.
"""

import re
import webbrowser
import subprocess
from urllib.parse import unquote, parse_qs, urlparse
import httpx
from playwright.async_api import async_playwright

_browser = None
_context = None


def _bring_chromium_to_front():
    """Bring the Playwright Chromium window to the foreground on Windows."""
    try:
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
    if _browser is None:
        pw = await async_playwright().start()
        _browser = await pw.chromium.launch(headless=False, args=["--start-maximized"])
        _context = await _browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            no_viewport=True,
        )
    return _context


async def search_and_read(query: str) -> dict:
    """Search DuckDuckGo in visible browser, click first result, read the page."""
    ctx = await _get_browser()
    page = await ctx.new_page()
    try:
        # DuckDuckGo search (no cookie banner, no reCAPTCHA)
        search_url = f"https://duckduckgo.com/?q={query}"
        await page.goto(search_url, timeout=15000)
        _bring_chromium_to_front()
        await page.wait_for_timeout(2000)

        # Click first organic result
        first_link = page.locator('[data-testid="result-title-a"]').first
        if await first_link.count() > 0:
            await first_link.click()
            await page.wait_for_timeout(3000)

            # Read page content
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
            return {"title": "Keine Ergebnisse", "url": search_url, "content": "Keine Ergebnisse gefunden."}
    except Exception as e:
        return {"error": str(e), "url": query}
    finally:
        pass


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
    """Open URL in Chrome (non-blocking)."""
    import asyncio
    # Add https:// if missing
    if not url.startswith("http://") and not url.startswith("https://"):
        url = "https://" + url
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(
        None,
        lambda: subprocess.Popen(f'start "" "{url}"', shell=True)
    )
    return {"success": True, "url": url}


def close_tab():
    """Close the current/active browser tab via Ctrl+W (Windows SendKeys)."""
    try:
        subprocess.run([
            "powershell", "-Command",
            """
            $chrome = Get-Process -Name 'chrome','msedge','firefox' -ErrorAction SilentlyContinue |
                Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -Last 1
            if ($chrome) {
                Add-Type @'
using System;
using System.Runtime.InteropServices;
public class WinHelper {
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
}
'@
                [WinHelper]::SetForegroundWindow($chrome.MainWindowHandle)
                Start-Sleep -Milliseconds 300
                Add-Type -AssemblyName System.Windows.Forms
                [System.Windows.Forms.SendKeys]::SendWait("^w")
            }
            """
        ], capture_output=True, timeout=5)
    except Exception:
        pass


def close_browser():
    """Close all Chrome/Edge browser windows."""
    try:
        subprocess.run(
            ["taskkill", "/f", "/im", "chrome.exe"],
            capture_output=True, timeout=5
        )
        subprocess.run(
            ["taskkill", "/f", "/im", "msedge.exe"],
            capture_output=True, timeout=5
        )
    except Exception:
        pass


async def close():
    global _browser, _context
    if _browser:
        await _browser.close()
        _browser = None
        _context = None
