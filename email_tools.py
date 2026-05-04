"""
Jarvis V2 — Email tools via macOS Apple Mail (AppleScript).
Reads from whatever accounts the Boss has configured in Mail.app — zero setup.
"""

import asyncio
import shlex

# Unique separators that won't appear in normal email content.
_FS = "\x1f"  # field separator within one record
_RS = "\x1e"  # record separator between multiple records


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

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


def _esc(s: str) -> str:
    """Escape a Python string for embedding in an AppleScript double-quoted string."""
    return s.replace("\\", "\\\\").replace('"', '\\"')


async def _check_mail_running() -> None:
    ok, out = await _run_osa('return application "Mail" is running')
    if not ok or out.strip().lower() != "true":
        raise RuntimeError("Mail.app is not running")


def _parse_records(raw: str) -> list[list[str]]:
    """Split raw AppleScript output into a list of field lists."""
    if not raw:
        return []
    return [rec.split(_FS) for rec in raw.split(_RS) if rec.strip()]


# ---------------------------------------------------------------------------
# Existing public functions (kept intact)
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# New structured functions
# ---------------------------------------------------------------------------

async def list_unread(limit: int = 10) -> list[dict]:
    """Return up to `limit` unread messages as structured dicts."""
    await _check_mail_running()
    script = f'''
set fs to "{_FS}"
set rs to "{_RS}"
set output to ""
tell application "Mail"
    set msgs to (messages of inbox whose read status is false)
    set lim to {limit}
    if (count of msgs) < lim then set lim to count of msgs
    repeat with i from 1 to lim
        set m to item i of msgs
        set msgId to (id of m) as string
        set msgFrom to sender of m
        set msgSubj to subject of m
        set msgDate to (date received of m) as string
        set msgContent to content of m
        -- preview: first 120 chars
        if (length of msgContent) > 120 then
            set preview to (characters 1 through 120 of msgContent as string) & "..."
        else
            set preview to msgContent
        end if
        if output is not "" then set output to output & rs
        set output to output & msgId & fs & msgFrom & fs & msgSubj & fs & preview & fs & msgDate
    end repeat
end tell
return output
'''
    ok, out = await _run_osa(script, timeout=25)
    if not ok:
        return []
    results = []
    for fields in _parse_records(out):
        if len(fields) < 5:
            continue
        results.append({
            "id": fields[0],
            "from": fields[1],
            "subject": fields[2],
            "preview": fields[3],
            "received": fields[4],
        })
    return results


async def get_message(msg_id: str) -> dict:
    """Return full message details for the given Mail.app message id."""
    await _check_mail_running()
    safe_id = _esc(msg_id)
    script = f'''
set fs to "{_FS}"
set output to ""
tell application "Mail"
    set targetId to {safe_id} as integer
    set m to first message of inbox whose id is targetId
    set msgFrom to sender of m
    set recipList to ""
    repeat with r in to recipients of m
        if recipList is not "" then set recipList to recipList & ", "
        set recipList to recipList & address of r
    end repeat
    set ccList to ""
    repeat with r in cc recipients of m
        if ccList is not "" then set ccList to ccList & ", "
        set ccList to ccList & address of r
    end repeat
    set msgSubj to subject of m
    set msgDate to (date received of m) as string
    set msgBody to content of m
    set output to msgFrom & fs & recipList & fs & ccList & fs & msgSubj & fs & msgDate & fs & msgBody
end tell
return output
'''
    ok, out = await _run_osa(script, timeout=20)
    if not ok:
        raise RuntimeError(f"Nachricht konnte nicht geladen werden: {out[:200]}")
    fields = out.split(_FS, 5)
    if len(fields) < 6:
        raise RuntimeError(f"Unerwartetes Antwortformat von Mail.app: {out[:100]}")
    return {
        "from": fields[0],
        "to": fields[1],
        "cc": fields[2],
        "subject": fields[3],
        "received": fields[4],
        "body": fields[5],
    }


async def draft_reply(msg_id: str, body: str) -> dict:
    """Create a reply draft in Mail.app prefilled with `body`. Does NOT send.

    Returns {"draft_id": str, "to": str, "subject": str}.
    """
    await _check_mail_running()
    safe_id = _esc(msg_id)
    safe_body = _esc(body)
    fs = _FS
    script = f'''
set fs to "{fs}"
tell application "Mail"
    set targetId to {safe_id} as integer
    set origMsg to first message of inbox whose id is targetId
    set origFrom to sender of origMsg
    set origSubj to subject of origMsg
    set replySubj to "Re: " & origSubj
    set newMsg to make new outgoing message with properties {{subject:replySubj, content:"{safe_body}", visible:false}}
    tell newMsg
        make new to recipient at end of to recipients with properties {{address:origFrom}}
    end tell
    save newMsg
    set draftId to (id of newMsg) as string
    return draftId & fs & origFrom & fs & replySubj
end tell
'''
    ok, out = await _run_osa(script, timeout=20)
    if not ok:
        raise RuntimeError(f"Antwort-Entwurf konnte nicht erstellt werden: {out[:200]}")
    fields = out.split(_FS, 2)
    if len(fields) < 3:
        raise RuntimeError(f"Unerwartetes Antwortformat von Mail.app: {out[:100]}")
    return {"draft_id": fields[0], "to": fields[1], "subject": fields[2]}


async def send_draft(draft_id: str) -> bool:
    """Send a previously saved draft identified by `draft_id`."""
    await _check_mail_running()
    safe_id = _esc(draft_id)
    script = f'''
tell application "Mail"
    set targetId to {safe_id} as integer
    set draftBox to first mailbox whose name is "Drafts"
    set m to first message of draftBox whose id is targetId
    send m
end tell
return "ok"
'''
    ok, out = await _run_osa(script, timeout=30)
    if not ok:
        raise RuntimeError(f"Entwurf konnte nicht gesendet werden: {out[:200]}")
    return out.strip().lower() == "ok"


async def list_drafts(limit: int = 10) -> list[dict]:
    """Return up to `limit` drafts from Mail.app's Drafts mailbox."""
    await _check_mail_running()
    script = f'''
set fs to "{_FS}"
set rs to "{_RS}"
set output to ""
tell application "Mail"
    set draftBox to first mailbox whose name is "Drafts"
    set msgs to messages of draftBox
    set lim to {limit}
    if (count of msgs) < lim then set lim to count of msgs
    repeat with i from 1 to lim
        set m to item i of msgs
        set msgId to (id of m) as string
        set recipList to ""
        repeat with r in to recipients of m
            if recipList is not "" then set recipList to recipList & ", "
            set recipList to recipList & address of r
        end repeat
        set msgSubj to subject of m
        set msgDate to (date sent of m) as string
        if output is not "" then set output to output & rs
        set output to output & msgId & fs & recipList & fs & msgSubj & fs & msgDate
    end repeat
end tell
return output
'''
    ok, out = await _run_osa(script, timeout=20)
    if not ok:
        return []
    results = []
    for fields in _parse_records(out):
        if len(fields) < 4:
            continue
        results.append({
            "id": fields[0],
            "to": fields[1],
            "subject": fields[2],
            "date": fields[3],
        })
    return results


async def search_messages(query: str, limit: int = 10) -> list[dict]:
    """Search all inboxes for messages matching `query` (keyword/sender/subject)."""
    await _check_mail_running()
    safe_query = _esc(query)
    script = f'''
set fs to "{_FS}"
set rs to "{_RS}"
set output to ""
set resultCount to 0
tell application "Mail"
    set allAccounts to every account
    repeat with acc in allAccounts
        set inboxes to every mailbox of acc whose name is "INBOX"
        repeat with mb in inboxes
            set allMsgs to messages of mb
            repeat with m in allMsgs
                if resultCount >= {limit} then exit repeat
                set msgSubj to subject of m
                set msgFrom to sender of m
                set msgBody to content of m
                set q to "{safe_query}"
                if (msgSubj contains q) or (msgFrom contains q) or (msgBody contains q) then
                    set msgId to (id of m) as string
                    set msgDate to (date received of m) as string
                    set preview to ""
                    if (length of msgBody) > 120 then
                        set preview to (characters 1 through 120 of msgBody as string) & "..."
                    else
                        set preview to msgBody
                    end if
                    if output is not "" then set output to output & rs
                    set output to output & msgId & fs & msgFrom & fs & msgSubj & fs & preview & fs & msgDate
                    set resultCount to resultCount + 1
                end if
            end repeat
            if resultCount >= {limit} then exit repeat
        end repeat
        if resultCount >= {limit} then exit repeat
    end repeat
end tell
return output
'''
    ok, out = await _run_osa(script, timeout=40)
    if not ok:
        return []
    results = []
    for fields in _parse_records(out):
        if len(fields) < 5:
            continue
        results.append({
            "id": fields[0],
            "from": fields[1],
            "subject": fields[2],
            "preview": fields[3],
            "received": fields[4],
        })
    return results
