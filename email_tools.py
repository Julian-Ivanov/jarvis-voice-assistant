"""
Jarvis V2 — Email tools via macOS Apple Mail (AppleScript).
Reads from whatever accounts the Boss has configured in Mail.app — zero setup.
"""

import asyncio
import shlex


async def _run_osa(script: str, timeout: int = 15) -> tuple[bool, str]:
    proc = await asyncio.create_subprocess_exec(
        "osascript", "-e", script,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        return False, "AppleScript timed out"
    if proc.returncode == 0:
        return True, stdout.decode("utf-8", errors="ignore").strip()
    return False, stderr.decode("utf-8", errors="ignore").strip()


async def read_unread(limit: int = 5) -> str:
    """Return up to `limit` unread message summaries from Apple Mail."""
    script = f'''
    set output to ""
    tell application "Mail"
        set msgs to (messages of inbox whose read status is false)
        set total to count of msgs
        if total is 0 then
            return "Keine ungelesenen Mails."
        end if
        set output to "Sie haben " & total & " ungelesene Mails. Hier die wichtigsten: "
        set lim to {limit}
        if total < lim then set lim to total
        repeat with i from 1 to lim
            set m to item i of msgs
            set s to subject of m
            set sName to ""
            try
                set sName to (extract name from sender of m)
            end try
            if sName is "" then set sName to sender of m
            set output to output & "Von " & sName & ": " & s & ". "
        end repeat
    end tell
    return output
    '''
    ok, out = await _run_osa(script, timeout=20)
    if not ok:
        return f"Mail-Fehler: {out[:200]}"
    return out


async def draft_email(to: str, subject: str, body: str) -> str:
    """Open a new mail draft in Apple Mail with the fields prefilled.
    The Boss reviews & sends manually — Jarvis never sends without approval."""
    # Escape AppleScript string literals
    def esc(s: str) -> str:
        return s.replace("\\", "\\\\").replace("\"", "\\\"")

    script = f'''
    tell application "Mail"
        set newMsg to make new outgoing message with properties {{visible:true, subject:"{esc(subject)}", content:"{esc(body)}"}}
        tell newMsg
            make new to recipient at end of to recipients with properties {{address:"{esc(to)}"}}
        end tell
        activate
    end tell
    '''
    ok, out = await _run_osa(script, timeout=15)
    if not ok:
        return f"Entwurf konnte nicht erstellt werden: {out[:200]}"
    return f"Entwurf an {to} mit Betreff '{subject}' erstellt — bitte pruefen und senden."
