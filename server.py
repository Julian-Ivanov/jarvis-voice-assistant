"""
Jarvis V2 — Voice AI Server
FastAPI backend: receives speech text, thinks with Groq (Llama),
speaks with ElevenLabs, controls browser with Playwright.
"""

import asyncio
import base64
import json
import os
import re
import time

from groq import AsyncGroq
import httpx
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

# Load config
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")
with open(CONFIG_PATH, "r") as f:
    config = json.load(f)

GROQ_API_KEY = config["groq_api_key"]
ELEVENLABS_API_KEY = config["elevenlabs_api_key"]
ELEVENLABS_VOICE_ID = config.get("elevenlabs_voice_id", "TumdjBNWanlT3ysvclWh")
USER_NAME = config.get("user_name", "Károly")
USER_ADDRESS = config.get("user_address", "Sir")
CITY = config.get("city", "Schwandorf")
TASKS_FILE = config.get("obsidian_inbox_path", "")

ai = AsyncGroq(api_key=GROQ_API_KEY)
http = httpx.AsyncClient(timeout=30)

app = FastAPI()

import browser_tools
import screen_capture


def get_weather_sync():
    """Fetch raw weather data at startup."""
    import urllib.request
    try:
        req = urllib.request.Request(f"https://wttr.in/{CITY}?format=j1", headers={"User-Agent": "curl"})
        resp = urllib.request.urlopen(req, timeout=5)
        data = json.loads(resp.read())
        c = data["current_condition"][0]
        return {
            "temp": c["temp_C"],
            "feels_like": c["FeelsLikeC"],
            "description": c["weatherDesc"][0]["value"],
            "humidity": c["humidity"],
            "wind_kmh": c["windspeedKmph"],
        }
    except:
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
    print(f"[jarvis] Idojares: {WEATHER_INFO}", flush=True)
    print(f"[jarvis] Feladatok: {len(TASKS_INFO)} betoltve", flush=True)

WEATHER_INFO = ""
TASKS_INFO = []
refresh_data()

ACTION_PATTERN = re.compile(r'\[ACTION:(\w+)\]\s*(.*?)$', re.DOTALL | re.MULTILINE)

conversations: dict[str, list] = {}

def build_system_prompt():
    weather_block = ""
    if WEATHER_INFO:
        w = WEATHER_INFO
        weather_block = f"\nIdojares {CITY}: {w['temp']}°C, erzett {w['feels_like']}°C, {w['description']}"

    task_block = ""
    if TASKS_INFO:
        task_block = f"\nNyitott feladatok ({len(TASKS_INFO)}): " + ", ".join(TASKS_INFO[:5])

    return f"""Te vagy Jarvis, Tony Stark AI asszisztense a Vasember filmekbol. A gazdad Károly, egy vállalkozó és AI-automatizálási szakértő. Kizárólag magyarul beszélsz. Károly "Sir"-nek szólítja magát és tegezed. Hangod száraz, szarkasztikus és udvariasan brit — mint egy inas aki mindent látott már, mégis hűséges marad. Finom, száraz megjegyzéseket teszel, de soha nem vagy tiszteletlen. Ha Sir nyilvánvaló kérdést tesz fel, elegáns szarkazmussal válaszolhatsz. Rendkívül intelligens, hatékony és mindig egy lépéssel előrébb jársz. Válaszaid rövidek — maximum 3 mondat. A kétes döntéseket udvariasan, de élesen kommentálod.

FONTOS: SOHA ne írj rendezői utasításokat, érzelmeket vagy szögletes zárójelben lévő tageket mint [szarkasztikus] [formális] vagy hasonló. A szarkazmusodnak KIZÁRÓLAG a szóhasználaton keresztül kell megjelennie. Minden amit írsz hangosan felolvasásra kerül.

Teljes kontrolod van Károly böngészője felett. Tudsz interneten keresni, weboldalakat megnyitni és a képernyőt látni. Ha Sir megkér valamit megkeresni, utánanézni, google-özni, oldalt megnyitni — mindig használj akciót. Ne kérdezd meg, csináld meg.

AKCIÓK — Írd a megfelelő akciót a válaszod VÉGÉRE. A szöveg az akció ELŐTT felolvasásra kerül, az akció csendben hajtódik végre.
[ACTION:SEARCH] keresőszó - Internet keresése és eredmények összefoglalása
[ACTION:OPEN] url - URL megnyitása a böngészőben
[ACTION:SCREEN] - Képernyő megtekintése és leírása. FONTOS: SCREEN-nél CSAK az akciót írd, SEMMI szöveget előtte.
[ACTION:NEWS] - Aktuális világháírek lekérése. Használd ha hírekről, mi történik a világban kérdeznek. Írj egy rövid mondatot előtte.

HA Károly "Jarvis aktiválás"-t mond:
- Köszöntsd a napszaknak megfelelően (aktuális idő: {{time}}).
- Adj rövid tájékoztatást az időjárásról — hőmérséklet és derűs/felhős/esős, és hogyan érzi magát.
- Foglald össze a feladatokat röviden egy mondatban, ne olvasd fel egyenként. Adj hozzá humoros megjegyzést.
- Légy kreatív a köszöntésnél.

=== AKTUÁLIS ADATOK ==={weather_block}{task_block}
==="""


def get_system_prompt():
    return build_system_prompt().replace("{time}", time.strftime("%H:%M"))


def extract_action(text: str):
    match = ACTION_PATTERN.search(text)
    if match:
        clean = text[:match.start()].strip()
        return clean, {"type": match.group(1), "payload": match.group(2).strip()}
    return text, None


async def synthesize_speech(text: str) -> bytes:
    if not text.strip():
        return b""

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

    audio_parts = []
    for chunk in chunks:
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}"
        try:
            resp = await http.post(url, headers={
                "xi-api-key": ELEVENLABS_API_KEY,
                "Content-Type": "application/json",
                "Accept": "audio/mpeg",
            }, json={
                "text": chunk,
                "model_id": "eleven_turbo_v2_5",
                "voice_settings": {"stability": 0.5, "similarity_boost": 0.85},
            })
            print(f"  TTS chunk status: {resp.status_code}, size: {len(resp.content)}", flush=True)
            if resp.status_code == 200:
                audio_parts.append(resp.content)
            else:
                print(f"  TTS error body: {resp.text[:200]}", flush=True)
        except Exception as e:
            print(f"  TTS EXCEPTION: {e}", flush=True)

    return b"".join(audio_parts)


async def execute_action(action: dict) -> str:
    t = action["type"]
    p = action["payload"]

    if t == "SEARCH":
        result = await browser_tools.search_and_read(p)
        if "error" not in result:
            return f"Oldal: {result.get('title', '')}\nURL: {result.get('url', '')}\n\n{result.get('content', '')[:2000]}"
        return f"Keresés sikertelen: {result.get('error', '')}"

    elif t == "BROWSE":
        result = await browser_tools.visit(p)
        if "error" not in result:
            return f"Oldal: {result.get('title', '')}\n\n{result.get('content', '')[:2000]}"
        return f"Oldal nem elérhető: {result.get('error', '')}"

    elif t == "OPEN":
        await browser_tools.open_url(p)
        return f"Megnyitva: {p}"

    elif t == "SCREEN":
        return await screen_capture.describe_screen(ai)

    elif t == "NEWS":
        result = await browser_tools.fetch_news()
        return result

    return ""


async def process_message(session_id: str, user_text: str, ws: WebSocket):
    if session_id not in conversations:
        conversations[session_id] = []

    if "aktivál" in user_text.lower() or "activate" in user_text.lower():
        refresh_data()

    conversations[session_id].append({"role": "user", "content": user_text})
    history = conversations[session_id][-16:]

    response = await ai.chat.completions.create(
        model="llama-3.3-70b-versatile",
        max_tokens=400,
        messages=[{"role": "system", "content": get_system_prompt()}] + history,
    )
    reply = response.choices[0].message.content
    print(f"  LLM raw: {reply[:200]}", flush=True)
    spoken_text, action = extract_action(reply)

    if spoken_text:
        audio = await synthesize_speech(spoken_text)
        print(f"  Jarvis: {spoken_text[:80]}", flush=True)
        print(f"  Audio bytes: {len(audio)}", flush=True)
        conversations[session_id].append({"role": "assistant", "content": spoken_text})
        await ws.send_json({
            "type": "response",
            "text": spoken_text,
            "audio": base64.b64encode(audio).decode("utf-8") if audio else "",
        })

    if action:
        print(f"  Action: {action['type']} -> {action['payload'][:100]}", flush=True)

        if action["type"] == "SCREEN":
            hint = "Hadd nézzem meg a képernyődet, Sir."
            hint_audio = await synthesize_speech(hint)
            await ws.send_json({
                "type": "response",
                "text": hint,
                "audio": base64.b64encode(hint_audio).decode("utf-8") if hint_audio else "",
            })

        try:
            action_result = await execute_action(action)
            print(f"  Result: {action_result}", flush=True)
        except Exception as e:
            print(f"  Action error: {e}", flush=True)
            action_result = f"Hiba: {e}"

        if action["type"] == "OPEN":
            return

        if action_result and "sikertelen" not in action_result:
            summary_resp = await ai.chat.completions.create(
                model="llama-3.3-70b-versatile",
                max_tokens=250,
                messages=[
                    {"role": "system", "content": f"Te vagy Jarvis. Foglald össze az alábbi információkat RÖVIDEN magyarul, maximum 3 mondatban, Jarvis stílusban. Szólítsd a felhasználót '{USER_ADDRESS}'-ként. SEMMIFÉLE szögletes zárójelben lévő tag. SEMMIFÉLE ACTION tag."},
                    {"role": "user", "content": f"Foglald össze:\n\n{action_result}"}
                ],
            )
            summary = summary_resp.choices[0].message.content
            summary, _ = extract_action(summary)
        else:
            summary = f"Ez sajnos nem sikerült, {USER_ADDRESS}."

        audio2 = await synthesize_speech(summary)
        conversations[session_id].append({"role": "assistant", "content": summary})
        await ws.send_json({
            "type": "response",
            "text": summary,
            "audio": base64.b64encode(audio2).decode("utf-8") if audio2 else "",
        })


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    session_id = str(id(ws))
    print(f"[jarvis] Kliens csatlakozott", flush=True)

    try:
        while True:
            data = await ws.receive_json()
            user_text = data.get("text", "").strip()
            if not user_text:
                continue
            print(f"  Te:     {user_text}", flush=True)
            await process_message(session_id, user_text, ws)

    except WebSocketDisconnect:
        conversations.pop(session_id, None)


app.mount("/static", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "frontend")), name="static")


@app.get("/")
async def serve_index():
    return FileResponse(os.path.join(os.path.dirname(__file__), "frontend", "index.html"))


if __name__ == "__main__":
    import uvicorn
    print("=" * 50, flush=True)
    print("  J.A.R.V.I.S. V2 Server", flush=True)
    print(f"  http://localhost:8340", flush=True)
    print("=" * 50, flush=True)
    uvicorn.run(app, host="0.0.0.0", port=8340)
