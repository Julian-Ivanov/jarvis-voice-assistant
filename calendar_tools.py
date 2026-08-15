"""
Jarvis V2 — Calendar tools via macOS Calendar.app (AppleScript).
Reads from whatever calendars are configured (Google Calendar usually syncs here).
Zero auth, zero API tokens — Calendar.app already knows.
"""

import asyncio


FS = "\x1f"
RS = "\x1e"


def _esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


async def _run_osa(script: str, timeout: int = 20) -> tuple[bool, str]:
    proc = await asyncio.create_subprocess_exec(
        "osascript", "-e", script,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.communicate()
        return False, "AppleScript timed out"
    if proc.returncode == 0:
        return True, stdout.decode("utf-8", errors="ignore").strip()
    return False, stderr.decode("utf-8", errors="ignore").strip()


async def _check_calendar_running() -> None:
    ok, _ = await _run_osa('tell application "Calendar" to launch')
    if not ok:
        raise RuntimeError("Calendar.app konnte nicht gestartet werden")


def _parse_records(raw: str) -> list[list[str]]:
    if not raw:
        return []
    return [r.split(FS) for r in raw.split(RS) if r]


async def list_today() -> list[dict]:
    """Return all events scheduled for today across all calendars."""
    await _check_calendar_running()
    script = f'''
    set output to ""
    set d to current date
    set hours of d to 0
    set minutes of d to 0
    set seconds of d to 0
    set tomorrow to d + (24 * 60 * 60)
    tell application "Calendar"
        repeat with c in calendars
            try
                set evs to (every event of c whose start date >= d and start date < tomorrow)
                repeat with e in evs
                    set output to output & (uid of e) & "{FS}" & (summary of e) & "{FS}" & ¬
                        ((start date of e) as «class isot» as string) & "{FS}" & ¬
                        ((end date of e) as «class isot» as string) & "{FS}" & (name of c) & "{RS}"
                end repeat
            end try
        end repeat
    end tell
    return output
    '''
    ok, out = await _run_osa(script, timeout=25)
    if not ok:
        raise RuntimeError(f"Calendar list_today failed: {out}")
    return [
        {"id": r[0], "title": r[1], "start": r[2], "end": r[3], "calendar": r[4]}
        for r in _parse_records(out) if len(r) >= 5
    ]


async def list_upcoming(days: int = 7) -> list[dict]:
    """Return events scheduled in the next `days` days."""
    await _check_calendar_running()
    secs = days * 24 * 60 * 60
    script = f'''
    set output to ""
    set d to current date
    set future to d + {secs}
    tell application "Calendar"
        repeat with c in calendars
            try
                set evs to (every event of c whose start date >= d and start date < future)
                repeat with e in evs
                    set output to output & (uid of e) & "{FS}" & (summary of e) & "{FS}" & ¬
                        ((start date of e) as «class isot» as string) & "{FS}" & ¬
                        ((end date of e) as «class isot» as string) & "{FS}" & (name of c) & "{RS}"
                end repeat
            end try
        end repeat
    end tell
    return output
    '''
    ok, out = await _run_osa(script, timeout=30)
    if not ok:
        raise RuntimeError(f"Calendar list_upcoming failed: {out}")
    return [
        {"id": r[0], "title": r[1], "start": r[2], "end": r[3], "calendar": r[4]}
        for r in _parse_records(out) if len(r) >= 5
    ]


async def create_event(
    title: str,
    start_iso: str,
    duration_minutes: int = 60,
    calendar_name: str | None = None,
    notes: str = "",
) -> dict:
    """Create a new event. start_iso = 'YYYY-MM-DD HH:MM'. Calendar defaults to first."""
    cal_clause = (
        f'set targetCal to calendar "{_esc(calendar_name)}"' if calendar_name
        else 'set targetCal to first calendar'
    )
    script = f'''
    set startDate to date "{_esc(start_iso)}"
    set endDate to startDate + ({duration_minutes} * 60)
    tell application "Calendar"
        {cal_clause}
        set newEvent to make new event at end of events of targetCal with properties ¬
            {{summary:"{_esc(title)}", start date:startDate, end date:endDate, description:"{_esc(notes)}"}}
        return (uid of newEvent) & "{FS}" & (summary of newEvent)
    end tell
    '''
    ok, out = await _run_osa(script, timeout=20)
    if not ok:
        raise RuntimeError(f"Calendar create_event failed: {out}")
    parts = out.split(FS)
    return {"id": parts[0], "title": parts[1] if len(parts) > 1 else title}
