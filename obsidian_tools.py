"""
Jarvis V2 — Obsidian inbox notes.
Appends timestamped notes to a markdown file in the user's Obsidian inbox path.
"""

import asyncio
import os
from datetime import datetime
from pathlib import Path


def _now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def _today_filename() -> str:
    return datetime.now().strftime("Jarvis-%Y-%m-%d.md")


async def append_note(inbox_path: str, body: str, tag: str = "") -> str:
    """Append a note to today's daily file in the Obsidian inbox.
    Returns the absolute path of the file written.
    """
    if not inbox_path:
        raise RuntimeError("Obsidian inbox_path ist nicht konfiguriert")

    inbox = Path(os.path.expanduser(inbox_path))
    inbox.mkdir(parents=True, exist_ok=True)
    target = inbox / _today_filename()

    header = "" if target.exists() else f"# Jarvis Notizen — {datetime.now():%A, %d. %B %Y}\n\n"
    tag_line = f" #{tag}" if tag else ""
    entry = f"## {_now_iso()}{tag_line}\n\n{body.strip()}\n\n"

    def _write():
        with target.open("a", encoding="utf-8") as f:
            f.write(header + entry)
    await asyncio.to_thread(_write)
    return str(target)


async def list_today(inbox_path: str) -> str:
    """Return the contents of today's daily note, or empty string if none."""
    target = Path(os.path.expanduser(inbox_path)) / _today_filename()
    if not target.exists():
        return ""
    return await asyncio.to_thread(target.read_text, "utf-8")
