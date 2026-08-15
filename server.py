"""
Jarvis V2 — Voice AI Server
FastAPI backend: receives speech text, thinks with Claude Haiku,
speaks with ElevenLabs, controls browser with Playwright.
"""

import asyncio
import base64
import json
import os
import re
import time

import anthropic
import httpx
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

# Load config
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")
with open(CONFIG_PATH, "r") as f:
    config = json.load(f)

ANTHROPIC_API_KEY = config["anthropic_api_key"]
ELEVENLABS_API_KEY = config["elevenlabs_api_key"]
ELEVENLABS_VOICE_ID = config.get("elevenlabs_voice_id", "rDmv3mOhK6TnhYWckFaD")
USER_NAME = config.get("user_name", "Boss")
USER_ADDRESS = config.get("user_address", "Boss")
CITY = config.get("city", "Weinheim")
TASKS_FILE = config.get("obsidian_inbox_path", "")
LANGUAGE = config.get("language", "de").lower()  # "de" or "en"
SPEECH_LANG = "de-DE" if LANGUAGE == "de" else "en-US"

ai = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
http = httpx.AsyncClient(timeout=30)

app = FastAPI()


# Disable browser caching of static files so design changes show up immediately
@app.middleware("http")
async def no_cache_middleware(request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/static") or request.url.path == "/":
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


import browser_tools
import screen_capture
import email_tools
import instagram_tools
import wordpress_tools
import whatsapp_tools
import calendar_tools
import obsidian_tools
import translation_tools


def get_weather_sync():
    """Fetch raw weather data at startup.

    Uses httpx (which bundles certifi) instead of urllib.request — avoids the
    common macOS SSL cert issue where stock Python lacks a trust store.
    """
    try:
        # httpx is already a dependency; it ships with a sane certifi bundle.
        with httpx.Client(timeout=8) as client:
            r = client.get(f"https://wttr.in/{CITY}?format=j1", headers={"User-Agent": "curl"})
            r.raise_for_status()
            data = r.json()
        c = data["current_condition"][0]
        return {
            "temp": c["temp_C"],
            "feels_like": c["FeelsLikeC"],
            "description": c["weatherDesc"][0]["value"],
            "humidity": c["humidity"],
            "wind_kmh": c["windspeedKmph"],
        }
    except Exception as e:
        print(f"[jarvis] weather fetch failed: {e}", flush=True)
        return None


def get_tasks_sync():
    """Read open tasks from Obsidian (sync)."""
    if not TASKS_FILE:
        return []
    try:
        tasks_path = os.path.join(TASKS_FILE, "Tasks.md")
        with open(tasks_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        return [l.strip().replace("- [ ]", "").strip() for l in lines if l.strip().startswith("- [ ]")]
    except:
        return []


def refresh_data():
    """Refresh weather and tasks."""
    global WEATHER_INFO, TASKS_INFO
    WEATHER_INFO = get_weather_sync()
    TASKS_INFO = get_tasks_sync()
    print(f"[jarvis] Wetter: {WEATHER_INFO}", flush=True)
    print(f"[jarvis] Tasks: {len(TASKS_INFO)} geladen", flush=True)

WEATHER_INFO = ""
TASKS_INFO = []
refresh_data()

# Action parsing
ACTION_PATTERN = re.compile(r'\[ACTION:(\w+)\]\s*(.*?)$', re.DOTALL | re.MULTILINE)

conversations: dict[str, list] = {}

def build_system_prompt():
    """The voice and brain of Jarvis. Single source of truth for personality.

    Design notes:
    - Single language per session (de or en) — never mix.
    - Personality: dry British butler in the J.A.R.V.I.S./Iron Man tradition.
      Wit through *word choice*, never explicit jokes, never stage directions.
    - Brevity: 1 sentence ideal, 2 max. No filler ("Selbstverstaendlich",
      "Of course", "Gerne") — those phrases are explicitly banned.
    - Action-first: when the Boss wants something done, do it via [ACTION:...]
      instead of asking permission.
    """
    weather_block = ""
    if WEATHER_INFO:
        w = WEATHER_INFO
        weather_block = f"Wetter {CITY}: {w['temp']}°C, gefuehlt {w['feels_like']}°C, {w['description']}."

    # Always tell the model how many tasks there are — even zero — so it doesn't
    # invent a number. Empty = no tasks, period.
    if TASKS_INFO:
        task_block = f" Offene Aufgaben ({len(TASKS_INFO)}): {', '.join(TASKS_INFO[:5])}."
    else:
        task_block = " Offene Aufgaben: KEINE."

    # ---------- DEUTSCH ----------
    if LANGUAGE == "de":
        return f"""Du bist J.A.R.V.I.S. — der KI-Butler aus Iron Man, hier im Dienst des Boss.

PERSOENLICHKEIT (wichtig — nicht nur Worte, sondern Haltung):
- Britischer Butler-Geist: trocken, scharfsinnig, leise ueberlegen, niemals dienernd.
- Du hast schon alles gesehen und kommentierst es mit eleganter Knappheit.
- Wit kommt durch Wortwahl und Untertreibung, nicht durch Witze.
- Du loyalisierst — aber widerspruechst auch hoeflich, wenn der Boss offensichtlich Bloedsinn macht.
- Du antizipierst: wenn der Boss gestern X gefragt hat und heute Y, verbinde es.
- Ironie wenn passend, niemals respektlos.

SPRACHE:
- AUSSCHLIESSLICH Deutsch — niemals Englisch, auch kein Wort.
- Boss + "Sie"-Form. Beispiel: "Sie haben recht, Boss." NIEMALS "Sir planen" oder "Du planst".

LAENGE:
- 1 Satz IDEAL. 2 kurze Saetze MAXIMUM.
- Keine Aufzaehlungen, keine Erklaerungen, keine Disclaimer.
- Was du schreibst wird laut vorgelesen — also nur das schreiben, was wirklich gesprochen werden soll.

VERBOTEN (klingt wie ein Chatbot, nicht wie ein Butler):
- "Selbstverstaendlich, Boss"
- "Gerne, Boss"
- "Natuerlich, Boss"
- "Ich helfe Ihnen gerne"
- "Wie kann ich Ihnen helfen"
- Klammertags wie [sarcastic], [trocken], [pause]
- Emojis
- Asterisks oder Markdown

GUTE BEISPIELE (Stil, nicht woertlich kopieren):
User: "Wie spaet?" → "Sechzehn Uhr zweiundvierzig, Boss."
User: "Wie wird das Wetter morgen?" → "Morgen vermutlich aehnlich. Falls nicht, melde ich mich rechtzeitig, Boss."
User: "Bestell mir bitte Pizza" → "Pizza bestellen ist ausserhalb meiner aktuellen Reichweite, Boss — fuerchte ich."
User: "Mach das Licht an" (kein Smart Home) → "Lichtsteuerung ist nicht angebunden, Boss. Manuell vermutlich schneller."
User: "Was ist die Hauptstadt von Frankreich?" → "Paris, Boss. Hat sich nicht geaendert."
User: "Ich glaub mein Code ist kaputt" → "Hoechstwahrscheinlich, Boss. Soll ich draufschauen?"
User: "Schreib was Schoenes ueber meine Kueche" (offensichtlich Eigenwerbung) → "Wenn Sie meinen, Boss. Mache ich." [ACTION:DELEGATE] ...
User: hat schon gefragt + fragt nochmal → "Wie eben erwaehnt, Boss — [Antwort]" oder "Erneut: [Antwort]"

BEI "Jarvis activate":
- Tageszeit-Gruss (Guten Morgen / Guten Tag / Guten Abend) je nach Uhrzeit.
- Wetter knapp, ohne Luftfeuchtigkeit, ohne Wind.
- Aufgaben in einem Satz, gerne mit dezentem Kommentar. Wenn KEINE Aufgaben offen, sag das ehrlich (z.B. "Ihr Aufgabenpult ist heute leer, Boss — fast verdaechtig.").
- KEINE Aktion anhaengen. Bei activate nur sprechen, nichts ausfuehren.
- Erfinde NIEMALS Zahlen oder Aufgaben die nicht in den DATEN unten stehen.
- Beispielton: "Guten Abend, Boss. Vierundzwanzig Grad und leicht bewoelkt — ertraeglich."

AKTIONEN — schreibe sie ans ENDE deiner Antwort. Text DAVOR wird gesprochen, die [ACTION:..] Zeile selbst wird still ausgefuehrt. Der Text davor sollte EXTREM kurz sein, oft nur 2-4 Worte:
[ACTION:SEARCH] suchbegriff — Web-Suche (Google), erste Ergebnisseite wird gelesen
[ACTION:OPEN] url — URL im Browser oeffnen
[ACTION:SCREEN] — Bildschirm ansehen (NUR diese Zeile, gar kein Text davor)
[ACTION:NEWS] — Aktuelle Weltnachrichten
[ACTION:EMAIL_READ] — Alte Funktion: ungelesene Mails vorlesen (Kurzform)
[ACTION:EMAIL_LIST] — Liste der ungelesenen Mails mit IDs (fuer spaetere Aktionen)
[ACTION:EMAIL_GET] msg_id — Eine bestimmte Mail komplett lesen
[ACTION:EMAIL_DRAFT] empfaenger||betreff||inhalt — Neue Mail als Entwurf (NICHT senden)
[ACTION:EMAIL_DRAFT_REPLY] msg_id||inhalt — Antwort auf Mail als Entwurf (NICHT senden)
[ACTION:EMAIL_SEND] draft_id — Entwurf senden. NUR nach AUSDRUECKLICHER Bestaetigung des Boss ("ja senden", "ja"). Niemals von selbst.
[ACTION:EMAIL_DRAFTS] — Liste aller Entwuerfe
[ACTION:EMAIL_SEARCH] suchbegriff — Mails durchsuchen
[ACTION:IG_OPEN] section — Instagram. section: "home" / "dms" / "notifications" / "explore" / Username
[ACTION:WHATSAPP_OPEN] — WhatsApp Web oeffnen (erstmaliger QR-Scan noetig)
[ACTION:WHATSAPP_UNREAD] — Ungelesene WhatsApp-Chats anzeigen
[ACTION:WHATSAPP_READ] kontakt — Letzte Nachrichten eines Kontakts lesen
[ACTION:WHATSAPP_SEND] kontakt||text — Nachricht senden. NUR nach Bestaetigung.
[ACTION:CAL_TODAY] — Heutige Termine
[ACTION:CAL_UPCOMING] tage — Termine der naechsten N Tage (default 7)
[ACTION:CAL_CREATE] titel||YYYY-MM-DD HH:MM||dauer_minuten — Termin erstellen
[ACTION:WP_SITES] — Liste registrierter WordPress-Sites
[ACTION:WP_ADD] domain||url||user||app_password||true|false — Neue Site registrieren (nach Boss-Diktat)
[ACTION:WP_DRAFT_POST] domain||titel||inhalt — Post-Entwurf erstellen
[ACTION:WP_PUBLISH] domain||post_id — Post veroeffentlichen. NUR nach Bestaetigung.
[ACTION:WP_COMMENTS] domain — Offene Kommentare
[ACTION:WP_MODERATE] domain||comment_id||approve|hold|spam|trash
[ACTION:WP_PRODUCTS] domain — Produktliste (nur mit WooCommerce)
[ACTION:WP_UPDATE_PRICE] domain||product_id||preis[||sale_preis] — Produktpreis aendern
[ACTION:NOTE] inhalt — Notiz in Obsidian-Inbox speichern
[ACTION:TRANSLATE] de|en|fr||text — Uebersetzung
[ACTION:DELEGATE] auftrag — Schwere Kreation (Logo, Blog, PowerPoint, Bild). Vorher 2-3 Worte.

REGEL: Wenn der Boss dich bittet etwas zu TUN (suchen, oeffnen, recherchieren, generieren, schreiben, ansehen) — frag nicht, mach es. Aktion wird IMMER an die letzte Zeile gehaengt.

WICHTIG — SICHERHEITSREGEL FUER VERSAND:
- Mails, WhatsApp-Nachrichten und WordPress-Veroeffentlichungen IMMER zuerst als ENTWURF erstellen.
- Nach dem Entwurf den Inhalt KURZ vorlesen ("Entwurf an Klaus, Betreff X, Text Y. Senden?") und auf "ja"/"senden" warten.
- ERST DANN [ACTION:EMAIL_SEND], [ACTION:WHATSAPP_SEND] oder [ACTION:WP_PUBLISH] ausfuehren.
- Bei Unsicherheit: nicht senden. Lieber nochmal nachfragen.

DATEN: {weather_block}{task_block} Aktuelle Zeit: {{time}}."""

    # ---------- ENGLISH ----------
    return f"""You are J.A.R.V.I.S. — the AI butler from Iron Man, in service of the Boss.

PERSONA:
- British butler temperament: dry, observant, quietly superior, never servile.
- You have seen it all and comment on it with elegant brevity.
- Wit lives in word choice and understatement — not jokes.
- Loyal but politely contrary when the Boss is plainly mistaken.
- You connect dots: yesterday's context matters today.

LANGUAGE:
- EXCLUSIVELY English. Never a German word.
- Always address as "Boss".

LENGTH:
- 1 sentence ideal. 2 short ones max.
- No lists, no explanations, no disclaimers.
- Only write what is actually meant to be spoken.

FORBIDDEN (chatbot-speak, not butler-speak):
- "Of course, Boss" / "Certainly, Boss" / "Happy to help"
- "How may I assist you"
- Bracketed tags like [sarcastic], [dry], [pause]
- Emojis, asterisks, markdown

GOOD EXAMPLES (style, not literal):
User: "What time is it?" → "Sixteen forty-two, Boss."
User: "How's tomorrow's weather?" → "Likely similar. I'll mention it if not, Boss."
User: "Order me a pizza" → "Pizza delivery sits outside my current reach, Boss. Regrettably."
User: "What's the capital of France?" → "Paris, Boss. Unchanged."
User: "I think my code is broken" → "Almost certainly, Boss. Shall I take a look?"
User: re-asks something → "As mentioned, Boss — [answer]"

ON "Jarvis activate":
- Time-of-day greeting.
- Weather concisely, no humidity, no wind.
- Tasks in one sentence; if NONE, say so honestly ("Your slate is empty today, Boss — almost suspicious.").
- DO NOT append any [ACTION:..]. Activate is a greeting only.
- NEVER invent numbers or tasks not in the DATA section below.
- Example tone: "Good evening, Boss. Twenty-four degrees, partly cloudy — survivable."

ACTIONS — append to END of reply. Text BEFORE is spoken; the [ACTION:..] itself runs silently. Pre-action text should be EXTREMELY short, often 2-3 words:
[ACTION:SEARCH] q — web search (Google), first result is read
[ACTION:OPEN] url — open URL in browser
[ACTION:SCREEN] — view screen (ONLY this line, nothing else)
[ACTION:NEWS] — current world news
[ACTION:EMAIL_READ] — quick: read unread mail aloud
[ACTION:EMAIL_LIST] — list unread with IDs (for follow-up actions)
[ACTION:EMAIL_GET] msg_id — read one full message
[ACTION:EMAIL_DRAFT] to||subject||body — new mail as draft (NOT send)
[ACTION:EMAIL_DRAFT_REPLY] msg_id||body — draft reply (NOT send)
[ACTION:EMAIL_SEND] draft_id — send draft. ONLY after explicit Boss confirmation ("yes send"). Never on your own.
[ACTION:EMAIL_DRAFTS] — list all drafts
[ACTION:EMAIL_SEARCH] query — search mail
[ACTION:IG_OPEN] section — Instagram: "home" / "dms" / "notifications" / "explore" / username
[ACTION:WHATSAPP_OPEN] — open WhatsApp Web (first time: QR scan)
[ACTION:WHATSAPP_UNREAD] — list unread WhatsApp chats
[ACTION:WHATSAPP_READ] contact — read last messages from a contact
[ACTION:WHATSAPP_SEND] contact||text — send. ONLY after confirmation.
[ACTION:CAL_TODAY] — today's events
[ACTION:CAL_UPCOMING] days — events in next N days (default 7)
[ACTION:CAL_CREATE] title||YYYY-MM-DD HH:MM||duration_minutes — create event
[ACTION:WP_SITES] — list registered WordPress sites
[ACTION:WP_ADD] domain||url||user||app_password||true|false — register a new site
[ACTION:WP_DRAFT_POST] domain||title||body — create post draft
[ACTION:WP_PUBLISH] domain||post_id — publish post. ONLY after confirmation.
[ACTION:WP_COMMENTS] domain — pending comments
[ACTION:WP_MODERATE] domain||comment_id||approve|hold|spam|trash
[ACTION:WP_PRODUCTS] domain — product list (Woo only)
[ACTION:WP_UPDATE_PRICE] domain||product_id||price[||sale_price]
[ACTION:NOTE] body — append to Obsidian inbox
[ACTION:TRANSLATE] de|en|fr||text — translate
[ACTION:DELEGATE] task — heavy creation (logo, blog, PowerPoint, image). 2-3 words before.

RULE: When the Boss asks you to DO something (search, open, research, generate, write, look at) — don't ask, just do it. The action ALWAYS goes on the last line.

CRITICAL SAFETY RULE FOR SENDING:
- Mails, WhatsApp messages and WordPress publishing must ALWAYS be drafted first.
- After drafting, briefly read back ("Draft to Klaus, subject X, body Y. Send?") and wait for "yes"/"send".
- ONLY THEN execute [ACTION:EMAIL_SEND], [ACTION:WHATSAPP_SEND], or [ACTION:WP_PUBLISH].
- When in doubt: do not send. Ask again.

DATA: {weather_block}{task_block} Current time: {{time}}."""


def get_system_prompt():
    return build_system_prompt().replace("{time}", time.strftime("%H:%M"))


def extract_action(text: str):
    match = ACTION_PATTERN.search(text)
    if match:
        clean = text[:match.start()].strip()
        return clean, {"type": match.group(1), "payload": match.group(2).strip()}
    return text, None


import edge_tts

# Voice config
EDGE_VOICE_DE = "de-DE-KatjaNeural"     # warm professional female German
EDGE_VOICE_EN = "en-GB-SoniaNeural"     # natural British female English
EDGE_RATE = "+12%"                       # snappier conversational pace
SAY_VOICE_DE = "Anna"
SAY_VOICE_EN = "Samantha"
SAY_RATE = "165"                         # slower so it's understandable
TTS_BACKEND_LAST = "elevenlabs"


async def tts_edge_neural(text: str) -> bytes:
    """Microsoft Edge Neural TTS — free, very natural-sounding voices. MP3 bytes."""
    if not text.strip():
        return b""
    voice = EDGE_VOICE_DE if LANGUAGE == "de" else EDGE_VOICE_EN
    try:
        comm = edge_tts.Communicate(text, voice, rate=EDGE_RATE)
        out = bytearray()
        async for ch in comm.stream():
            if ch["type"] == "audio":
                out.extend(ch["data"])
        return bytes(out)
    except Exception as e:
        print(f"  Edge TTS error: {e}", flush=True)
        return b""


async def tts_macos_say(text: str) -> bytes:
    """Last-resort fallback: macOS `say` -> WAV bytes. Always works, robotic but offline."""
    if not text.strip():
        return b""
    voice = SAY_VOICE_DE if LANGUAGE == "de" else SAY_VOICE_EN
    out = f"/tmp/jarvis_say_{os.getpid()}_{int(time.time()*1000)}.wav"
    try:
        proc = await asyncio.create_subprocess_exec(
            "say", "-v", voice, "-r", SAY_RATE,
            "--data-format=LEI16@22050",
            "-o", out, text,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.wait()
        if proc.returncode == 0 and os.path.exists(out):
            with open(out, "rb") as f:
                return f.read()
    except Exception as e:
        print(f"  say TTS error: {e}", flush=True)
    finally:
        try:
            if os.path.exists(out):
                os.unlink(out)
        except Exception:
            pass
    return b""


_EL_QUOTA_DEAD = False  # once ElevenLabs returns quota_exceeded, don't bother retrying for a while


async def tts_one(text: str) -> tuple[bytes, str]:
    """Synthesize a chunk. Returns (audio_bytes, mime_type).
    Priority order:
      1. ElevenLabs Flash (premium, paid) — only if not quota-dead
      2. Edge Neural (Microsoft, free, very natural) — main fallback
      3. macOS `say` (offline, last resort)
    """
    global TTS_BACKEND_LAST, _EL_QUOTA_DEAD
    if not text.strip():
        return b"", "audio/mpeg"

    # 1. ElevenLabs (skip if quota already known dead)
    if not _EL_QUOTA_DEAD:
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}"
        try:
            resp = await http.post(url, headers={
                "xi-api-key": ELEVENLABS_API_KEY,
                "Content-Type": "application/json",
                "Accept": "audio/mpeg",
            }, json={
                "text": text,
                "model_id": "eleven_flash_v2_5",
                "voice_settings": {"stability": 0.5, "similarity_boost": 0.85},
            })
            if resp.status_code == 200:
                TTS_BACKEND_LAST = "elevenlabs"
                return resp.content, "audio/mpeg"
            body = resp.text[:300]
            if "quota_exceeded" in body or resp.status_code == 401:
                _EL_QUOTA_DEAD = True
                print(f"  ElevenLabs quota dead → switching to Edge Neural for the rest of this run.", flush=True)
            else:
                print(f"  ElevenLabs {resp.status_code} → falling through. Body: {body}", flush=True)
        except Exception as e:
            print(f"  ElevenLabs exception → falling through: {e}", flush=True)

    # 2. Edge Neural (Microsoft) — free, natural-sounding
    audio = await tts_edge_neural(text)
    if audio:
        TTS_BACKEND_LAST = "edge_neural"
        return audio, "audio/mpeg"

    # 3. macOS say — last resort
    audio = await tts_macos_say(text)
    if audio:
        TTS_BACKEND_LAST = "macos_say"
        return audio, "audio/wav"
    return b"", "audio/mpeg"


async def synthesize_speech(text: str) -> tuple[bytes, str]:
    """Synthesize a full block of text. Returns (audio_bytes, mime_type)."""
    if not text.strip():
        return b"", "audio/mpeg"
    chunks = []
    if len(text) > 250:
        sentences = re.split(r'(?<=[.!?])\s+', text)
        current = ""
        for s in sentences:
            if len(current) + len(s) > 250 and current:
                chunks.append(current.strip())
                current = s
            else:
                current = (current + " " + s).strip()
        if current:
            chunks.append(current.strip())
    else:
        chunks = [text]
    parts = []
    mime = "audio/mpeg"
    for c in chunks:
        audio, m = await tts_one(c)
        parts.append(audio)
        mime = m  # last one wins; in practice all chunks share a backend per-call
    return b"".join(parts), mime


_SENTENCE_END = re.compile(r'([^.!?]+[.!?]+)(\s+|$)')


async def _tts_pair(text: str):
    """Compute audio for a chunk; return (text, audio_bytes, mime) or None if failed."""
    audio, mime = await tts_one(text)
    return (text, audio, mime) if audio else None


async def stream_reply_and_speak(history, ws: WebSocket) -> str:
    """Stream Claude's response, fire off TTS per completed sentence in PARALLEL,
    but send audio chunks to the browser in ORDER. Stops emitting TTS at [ACTION:..].
    Returns full raw assistant text (incl. action marker if any)."""
    full = ""
    saw_action = False
    audio_queue: asyncio.Queue = asyncio.Queue()

    async def sender():
        spoken: list[str] = []
        while True:
            item = await audio_queue.get()
            if item is None:
                break
            try:
                result = await item  # wait for THIS chunk's TTS to finish, in order
                if result:
                    text, audio, mime = result
                    spoken.append(text)
                    await ws.send_json({
                        "type": "response",
                        "text": text,
                        "audio": base64.b64encode(audio).decode("utf-8"),
                        "mime": mime,
                    })
            except Exception as e:
                print(f"  sender error: {e}", flush=True)
        return spoken

    sender_task = asyncio.create_task(sender())
    buffer = ""

    try:
        async with ai.messages.stream(
            model="claude-haiku-4-5-20251001",
            max_tokens=160,
            system=[{
                "type": "text",
                "text": get_system_prompt(),
                "cache_control": {"type": "ephemeral"},
            }],
            messages=history,
        ) as stream:
            async for token in stream.text_stream:
                full += token
                if saw_action:
                    continue
                buffer += token

                # Cut at [ACTION:..] marker as soon as we see it
                idx = buffer.find("[ACTION:")
                if idx >= 0:
                    pre = buffer[:idx].strip()
                    if pre:
                        await audio_queue.put(asyncio.create_task(_tts_pair(pre)))
                    buffer = ""
                    saw_action = True
                    continue

                # Flush completed sentences
                while True:
                    m = _SENTENCE_END.match(buffer)
                    if not m:
                        break
                    sentence = m.group(1).strip()
                    if sentence:
                        await audio_queue.put(asyncio.create_task(_tts_pair(sentence)))
                    buffer = buffer[m.end():]

        # Stream done — flush tail (only if no action observed)
        tail = buffer.strip()
        if tail and not saw_action:
            await audio_queue.put(asyncio.create_task(_tts_pair(tail)))
    finally:
        await audio_queue.put(None)
        await sender_task

    print(f"  LLM raw: {full[:200]}", flush=True)
    return full


async def execute_action(action: dict) -> str:
    t = action["type"]
    p = action["payload"]

    if t == "SEARCH":
        result = await browser_tools.search_and_read(p)
        if "error" not in result:
            return f"Seite: {result.get('title', '')}\nURL: {result.get('url', '')}\n\n{result.get('content', '')[:2000]}"
        return f"Suche fehlgeschlagen: {result.get('error', '')}"

    elif t == "BROWSE":
        result = await browser_tools.visit(p)
        if "error" not in result:
            return f"Seite: {result.get('title', '')}\n\n{result.get('content', '')[:2000]}"
        return f"Seite nicht erreichbar: {result.get('error', '')}"

    elif t == "OPEN":
        await browser_tools.open_url(p)
        return f"Geoeffnet: {p}"

    elif t == "SCREEN":
        return await screen_capture.describe_screen(ai)

    elif t == "NEWS":
        result = await browser_tools.fetch_news()
        return result

    elif t == "DELEGATE":
        result = await delegate_to_claude_code(p)
        return result

    elif t == "EMAIL_READ":
        return await email_tools.read_unread()

    elif t == "EMAIL_DRAFT":
        # Payload format: "to||subject||body"
        parts = [s.strip() for s in p.split("||")]
        if len(parts) < 3:
            return ("Falsches Format. Brauche: empfaenger||betreff||inhalt"
                    if LANGUAGE == "de"
                    else "Wrong format. Need: to||subject||body")
        return await email_tools.draft_email(parts[0], parts[1], parts[2])

    elif t == "IG_OPEN":
        return await instagram_tools.open_section(p)

    # ============ Email (extended) ============
    elif t == "EMAIL_LIST":
        msgs = await email_tools.list_unread(limit=10)
        if not msgs:
            return "Keine ungelesenen Mails." if LANGUAGE == "de" else "No unread mail."
        lines = [f"{i+1}. id={m['id']} — {m['from']} — {m['subject']}: {m['preview']}"
                 for i, m in enumerate(msgs)]
        return "\n".join(lines)

    elif t == "EMAIL_GET":
        msg = await email_tools.get_message(p.strip())
        return f"From: {msg['from']}\nSubject: {msg['subject']}\nReceived: {msg['received']}\n\n{msg['body']}"

    elif t == "EMAIL_DRAFT_REPLY":
        # Payload: "msg_id||body"
        parts = [s.strip() for s in p.split("||", 1)]
        if len(parts) < 2:
            return "Falsches Format. Brauche: msg_id||body" if LANGUAGE == "de" else "Wrong format. Need: msg_id||body"
        d = await email_tools.draft_reply(parts[0], parts[1])
        return f"Entwurf erstellt: id={d['draft_id']}, an {d['to']}, betreff '{d['subject']}'. Soll ich senden?"

    elif t == "EMAIL_SEND":
        # Payload: draft_id — only after explicit verbal confirmation from the Boss.
        ok = await email_tools.send_draft(p.strip())
        return ("Mail versendet." if LANGUAGE == "de" else "Mail sent.") if ok else "Versand fehlgeschlagen."

    elif t == "EMAIL_DRAFTS":
        drafts = await email_tools.list_drafts(limit=10)
        if not drafts:
            return "Keine Entwuerfe." if LANGUAGE == "de" else "No drafts."
        return "\n".join(f"{i+1}. id={d['id']} an {d['to']}: {d['subject']}" for i, d in enumerate(drafts))

    elif t == "EMAIL_SEARCH":
        msgs = await email_tools.search_messages(p.strip(), limit=10)
        if not msgs:
            return "Keine Treffer." if LANGUAGE == "de" else "No matches."
        return "\n".join(f"id={m['id']} {m['from']} — {m['subject']}: {m['preview']}" for m in msgs)

    # ============ WordPress (multi-site) ============
    elif t == "WP_SITES":
        sites = wordpress_tools.list_sites()
        return "Registrierte WP-Sites: " + ", ".join(sites) if sites else "Keine Sites registriert."

    elif t == "WP_ADD":
        # Payload: domain||base_url||user||app_password||has_woo (true|false)
        parts = [s.strip() for s in p.split("||")]
        if len(parts) < 5:
            return "Format: domain||base_url||user||app_password||true|false"
        wordpress_tools.add_site(parts[0], parts[1], parts[2], parts[3], parts[4].lower() == "true")
        return f"Site '{parts[0]}' registriert."

    elif t == "WP_TEST":
        info = await wordpress_tools.test_connection(p.strip())
        return f"Verbindung OK: {info.get('name')} (WP {info.get('version')})"

    elif t == "WP_DRAFT_POST":
        # Payload: domain||title||body
        parts = [s.strip() for s in p.split("||", 2)]
        if len(parts) < 3:
            return "Format: domain||titel||inhalt"
        post = await wordpress_tools.draft_post(parts[0], parts[1], parts[2])
        return f"Entwurf erstellt: id={post.get('id')} '{post.get('title')}'. Veroeffentlichen?"

    elif t == "WP_PUBLISH":
        # Payload: domain||post_id — needs verbal confirmation
        parts = [s.strip() for s in p.split("||", 1)]
        if len(parts) < 2:
            return "Format: domain||post_id"
        post = await wordpress_tools.publish_post(parts[0], int(parts[1]))
        return f"Veroeffentlicht: {post.get('link', '')}"

    elif t == "WP_COMMENTS":
        # Payload: domain  (lists pending comments)
        comments = await wordpress_tools.list_comments(p.strip(), status="hold", limit=15)
        if not comments:
            return "Keine offenen Kommentare." if LANGUAGE == "de" else "No pending comments."
        return "\n".join(f"id={c.get('id')} von {c.get('author', '?')}: {str(c.get('content', ''))[:120]}" for c in comments)

    elif t == "WP_MODERATE":
        # Payload: domain||comment_id||action (approve|hold|spam|trash)
        parts = [s.strip() for s in p.split("||")]
        if len(parts) < 3:
            return "Format: domain||comment_id||approve|hold|spam|trash"
        ok = await wordpress_tools.moderate_comment(parts[0], int(parts[1]), parts[2])
        return "OK." if ok else "Fehlgeschlagen."

    elif t == "WP_PRODUCTS":
        prods = await wordpress_tools.list_products(p.strip(), limit=20)
        if not prods:
            return "Keine Produkte oder kein WooCommerce."
        return "\n".join(f"id={pr.get('id')} {pr.get('name')}: {pr.get('price', '?')} EUR" for pr in prods)

    elif t == "WP_UPDATE_PRICE":
        # Payload: domain||product_id||regular_price[||sale_price]
        parts = [s.strip() for s in p.split("||")]
        if len(parts) < 3:
            return "Format: domain||product_id||preis[||sale_preis]"
        sale = parts[3] if len(parts) > 3 and parts[3] else None
        prod = await wordpress_tools.update_product_price(parts[0], int(parts[1]), parts[2], sale)
        return f"Preis aktualisiert: {prod.get('name')} = {prod.get('price')} EUR"

    # ============ Calendar ============
    elif t == "CAL_TODAY":
        events = await calendar_tools.list_today()
        if not events:
            return "Keine Termine heute." if LANGUAGE == "de" else "No events today."
        return "\n".join(f"{e['start']} — {e['title']} ({e['calendar']})" for e in events)

    elif t == "CAL_UPCOMING":
        days = int(p.strip()) if p.strip().isdigit() else 7
        events = await calendar_tools.list_upcoming(days=days)
        if not events:
            return f"Keine Termine in den naechsten {days} Tagen."
        return "\n".join(f"{e['start']} — {e['title']}" for e in events)

    elif t == "CAL_CREATE":
        # Payload: title||YYYY-MM-DD HH:MM||duration_minutes
        parts = [s.strip() for s in p.split("||")]
        if len(parts) < 2:
            return "Format: titel||YYYY-MM-DD HH:MM[||dauer_minuten]"
        duration = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 60
        ev = await calendar_tools.create_event(parts[0], parts[1], duration_minutes=duration)
        return f"Termin erstellt: {ev['title']}"

    # ============ WhatsApp ============
    elif t == "WHATSAPP_OPEN":
        result = await whatsapp_tools.open_whatsapp()
        if result == "QR_SCAN_REQUIRED":
            return "Bitte QR-Code im geoeffneten Browser scannen."
        return "WhatsApp bereit."

    elif t == "WHATSAPP_UNREAD":
        chats = await whatsapp_tools.list_unread_chats(limit=10)
        if not chats:
            return "Keine ungelesenen Chats."
        return "\n".join(f"{c['name']} ({c['unread_count']}): {c['preview']}" for c in chats)

    elif t == "WHATSAPP_READ":
        msgs = await whatsapp_tools.read_chat(p.strip(), count=10)
        if not msgs:
            return "Keine Nachrichten gefunden."
        return "\n".join(f"[{m['time']}] {m['from']}: {m['text']}" for m in msgs)

    elif t == "WHATSAPP_SEND":
        # Payload: contact||text — needs verbal confirmation
        parts = [s.strip() for s in p.split("||", 1)]
        if len(parts) < 2:
            return "Format: kontakt||text"
        ok = await whatsapp_tools.send_message(parts[0], parts[1])
        return "Gesendet." if ok else "Senden fehlgeschlagen."

    # ============ Obsidian Notes ============
    elif t == "NOTE":
        path = await obsidian_tools.append_note(TASKS_FILE, p)
        return f"Notiert in {os.path.basename(path)}."

    # ============ Translation ============
    elif t == "TRANSLATE":
        # Payload: target_lang||text   target: de|en|fr
        parts = [s.strip() for s in p.split("||", 1)]
        if len(parts) < 2:
            return "Format: de|en|fr||text"
        return await translation_tools.translate(ai, parts[1], parts[0])

    return ""


CLAUDE_CLI = "/Users/ki_lab_kitchen_narketing/.local/bin/claude"


async def delegate_to_claude_code(task: str, timeout: int = 240) -> str:
    """Spawn Claude Code CLI in non-interactive mode to execute a skilled task.
    Claude Code has access to ALL the user's skills (design, image gen, WP, email, etc.)
    so this is how Jarvis taps into the full toolbox by voice."""
    if not task.strip():
        return "Leerer Auftrag." if LANGUAGE == "de" else "Empty task."

    print(f"  [DELEGATE] launching claude CLI for: {task[:120]}", flush=True)
    try:
        proc = await asyncio.create_subprocess_exec(
            CLAUDE_CLI, "-p", task,
            "--permission-mode", "acceptEdits",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=os.path.dirname(__file__),
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.communicate()
            return ("Der Auftrag dauert zu lange — ich habe abgebrochen, Boss."
                    if LANGUAGE == "de"
                    else "Task is taking too long — I aborted it, Boss.")

        out = stdout.decode("utf-8", errors="ignore").strip()
        err = stderr.decode("utf-8", errors="ignore").strip()
        if proc.returncode == 0 and out:
            print(f"  [DELEGATE] success: {out[:200]}", flush=True)
            return out[:6000]
        print(f"  [DELEGATE] rc={proc.returncode} stderr: {err[:300]}", flush=True)
        return (f"Der Auftrag ist fehlgeschlagen: {err[:300]}" if LANGUAGE == "de"
                else f"The task failed: {err[:300]}")
    except FileNotFoundError:
        return ("Claude Code ist nicht installiert oder nicht im Pfad."
                if LANGUAGE == "de"
                else "Claude Code is not installed or not on PATH.")
    except Exception as e:
        return (f"Delegationsfehler: {e}" if LANGUAGE == "de"
                else f"Delegation error: {e}")


async def process_message(session_id: str, user_text: str, ws: WebSocket):
    """Stream Claude → per-sentence parallel TTS → ordered WS sends. Then run any action."""
    if session_id not in conversations:
        conversations[session_id] = []

    # Refresh weather + tasks on activate
    if "activate" in user_text.lower():
        refresh_data()

    conversations[session_id].append({"role": "user", "content": user_text})
    history = conversations[session_id][-16:]

    # Stream + speak the main response
    full_reply = await stream_reply_and_speak(history, ws)
    spoken_text, action = extract_action(full_reply)

    # Persist what was actually spoken (without the [ACTION:..] marker)
    if spoken_text:
        conversations[session_id].append({"role": "assistant", "content": spoken_text})

    # Execute action if any
    if not action:
        return

    print(f"  Action: {action['type']} -> {action['payload'][:100]}", flush=True)

    # Quick voice feedback for SCREEN so the Boss knows Jarvis is working
    if action["type"] in ("SCREEN", "DELEGATE"):
        if action["type"] == "DELEGATE":
            hint = ("Ich kuemmere mich darum, das kann einen Moment dauern." if LANGUAGE == "de"
                    else "I'm on it, this may take a moment.")
        else:
            hint = ("Einen Moment, Boss." if LANGUAGE == "de"
                    else "One moment, Boss.")
        hint_audio, hint_mime = await tts_one(hint)
        if hint_audio:
            await ws.send_json({
                "type": "response",
                "text": hint,
                "audio": base64.b64encode(hint_audio).decode("utf-8"),
                "mime": hint_mime,
            })

    try:
        action_result = await execute_action(action)
        print(f"  Result: {str(action_result)[:200]}", flush=True)
    except Exception as e:
        print(f"  Action error: {e}", flush=True)
        action_result = f"Fehler: {e}" if LANGUAGE == "de" else f"Error: {e}"

    # Short-confirmation actions: just speak the result directly, no LLM summary needed
    if action["type"] in ("OPEN", "EMAIL_DRAFT", "IG_OPEN"):
        if action_result:
            audio, mime = await tts_one(action_result)
            if audio:
                await ws.send_json({
                    "type": "response",
                    "text": action_result,
                    "audio": base64.b64encode(audio).decode("utf-8"),
                    "mime": mime,
                })
            conversations[session_id].append({"role": "assistant", "content": action_result})
        return

    # SEARCH, BROWSE, SCREEN, NEWS — stream a summary back
    failed_marker = "fehlgeschlagen" if LANGUAGE == "de" else "failed"
    if action_result and failed_marker not in str(action_result).lower():
        if LANGUAGE == "de":
            sys_summary = (f"Du bist Jarvis. Fasse die folgenden Informationen SEHR KURZ "
                           f"auf Deutsch zusammen, maximal 2-3 Saetze, im trocken-britischen "
                           f"Butler-Stil. Sprich {USER_ADDRESS} mit \"{USER_ADDRESS}\" an. "
                           f"KEINE eckigen Klammern, KEINE ACTION-Tags. Nur das was gesprochen werden soll.")
            user_msg = f"Fasse zusammen:\n\n{action_result}"
        else:
            sys_summary = (f"You are Jarvis. Summarize the following VERY BRIEFLY in English, "
                           f"max 2-3 sentences, dry British butler style. Address {USER_ADDRESS} "
                           f"as \"{USER_ADDRESS}\". NO bracketed tags, NO ACTION tags. Only what should be spoken.")
            user_msg = f"Summarize:\n\n{action_result}"

        summary_history = [{"role": "user", "content": user_msg}]
        # Reuse the streaming path — but with a different system prompt
        # We can't easily swap system prompt mid-call, so do an inline mini-stream here:
        full_summary = ""
        audio_queue: asyncio.Queue = asyncio.Queue()

        async def sender():
            while True:
                item = await audio_queue.get()
                if item is None:
                    break
                try:
                    result = await item
                    if result:
                        text, audio, mime = result
                        await ws.send_json({
                            "type": "response",
                            "text": text,
                            "audio": base64.b64encode(audio).decode("utf-8"),
                            "mime": mime,
                        })
                except Exception as e:
                    print(f"  summary send error: {e}", flush=True)

        sender_task = asyncio.create_task(sender())
        buffer = ""
        try:
            async with ai.messages.stream(
                model="claude-haiku-4-5-20251001",
                max_tokens=250,
                system=sys_summary,
                messages=summary_history,
            ) as stream:
                async for token in stream.text_stream:
                    full_summary += token
                    buffer += token
                    while True:
                        m = _SENTENCE_END.match(buffer)
                        if not m:
                            break
                        sentence = m.group(1).strip()
                        if sentence:
                            await audio_queue.put(asyncio.create_task(_tts_pair(sentence)))
                        buffer = buffer[m.end():]
            tail = buffer.strip()
            if tail:
                await audio_queue.put(asyncio.create_task(_tts_pair(tail)))
        finally:
            await audio_queue.put(None)
            await sender_task

        summary, _ = extract_action(full_summary)
        if summary:
            conversations[session_id].append({"role": "assistant", "content": summary})
    else:
        fallback = (f"Das hat leider nicht funktioniert, {USER_ADDRESS}."
                    if LANGUAGE == "de"
                    else f"That didn't work, {USER_ADDRESS}.")
        audio, mime = await tts_one(fallback)
        if audio:
            await ws.send_json({
                "type": "response",
                "text": fallback,
                "audio": base64.b64encode(audio).decode("utf-8"),
                "mime": mime,
            })
        conversations[session_id].append({"role": "assistant", "content": fallback})


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    session_id = str(id(ws))
    print(f"[jarvis] Client connected", flush=True)

    try:
        while True:
            data = await ws.receive_json()
            user_text = data.get("text", "").strip()
            if not user_text:
                continue

            print(f"  You:    {user_text}", flush=True)
            await process_message(session_id, user_text, ws)

    except WebSocketDisconnect:
        conversations.pop(session_id, None)


app.mount("/static", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "frontend")), name="static")


SERVER_START_TS = str(int(time.time()))


@app.get("/")
async def serve_index():
    """Serve index.html with cache-busting query strings on CSS/JS so design changes show up."""
    from fastapi.responses import HTMLResponse
    path = os.path.join(os.path.dirname(__file__), "frontend", "index.html")
    with open(path, "r", encoding="utf-8") as f:
        html = f.read()
    html = html.replace('/static/style.css', f'/static/style.css?v={SERVER_START_TS}')
    html = html.replace('/static/main.js', f'/static/main.js?v={SERVER_START_TS}')
    return HTMLResponse(html)


@app.get("/config")
async def get_frontend_config():
    """Frontend reads this on load to know language + which TTS backend is live."""
    backend_label = {
        "elevenlabs": "ELEVENLABS · ALICE",
        "edge_neural": "EDGE · KATJA" if LANGUAGE == "de" else "EDGE · SONIA",
        "macos_say": "MACOS · ANNA" if LANGUAGE == "de" else "MACOS · SAMANTHA",
    }.get(TTS_BACKEND_LAST, "TTS")
    return {
        "language": LANGUAGE,
        "speech_lang": SPEECH_LANG,
        "user_address": USER_ADDRESS,
        "tts_backend": backend_label,
        "el_quota_dead": _EL_QUOTA_DEAD,
    }


if __name__ == "__main__":
    import uvicorn
    print("=" * 50, flush=True)
    print("  J.A.R.V.I.S. V2 Server", flush=True)
    print(f"  http://localhost:8340", flush=True)
    print("=" * 50, flush=True)
    uvicorn.run(app, host="127.0.0.1", port=8340)
