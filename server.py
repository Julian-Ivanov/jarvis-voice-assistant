"""
Jarvis V2 — Voice AI Server
FastAPI backend: receives speech text, thinks with Claude Haiku,
speaks with ElevenLabs, controls browser with Playwright.

V2.1 Changes:
- TaskManager class: structured task management
- REST API: GET/POST/PUT/DELETE /api/tasks
- File Watcher: auto-sync when Obsidian changes
- WebSocket Broadcast: push updates to all clients
- active_connections list for multi-client support
"""

import asyncio
import base64
import json
import os
import re
import time
from dataclasses import dataclass, asdict
from typing import Optional, List
from uuid import uuid4
from datetime import datetime

import anthropic
import httpx
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

# ═══════════════════════════════════════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════════════════════════════════════

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")
with open(CONFIG_PATH, "r") as f:
    config = json.load(f)

ANTHROPIC_API_KEY = config["anthropic_api_key"]
ELEVENLABS_API_KEY = config["elevenlabs_api_key"]
ELEVENLABS_VOICE_ID = config.get("elevenlabs_voice_id", "rDmv3mOhK6TnhYWckFaD")
USER_NAME = config.get("user_name", "Julius")
USER_ADDRESS = config.get("user_address", "Sir")
CITY = config.get("city", "Wolfenbuettel")
TASKS_FILE = config.get("obsidian_inbox_path", "")

ai = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
http = httpx.AsyncClient(timeout=30)

app = FastAPI()

import browser_tools
import screen_capture


# ═══════════════════════════════════════════════════════════════════════════════
# TASK DATACLASS
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class Task:
    """Structured task representation."""
    id: str
    title: str
    priority: str = "medium"        # high, medium, low
    deadline: Optional[str] = None  # "2026-06-05"
    tags: List[str] = None
    project: Optional[str] = None
    status: str = "open"            # open, completed
    created: str = ""
    updated: str = ""

    def __post_init__(self):
        if self.tags is None:
            self.tags = []
        if not self.created:
            self.created = datetime.now().isoformat()
        if not self.updated:
            self.updated = datetime.now().isoformat()


# ═══════════════════════════════════════════════════════════════════════════════
# TASK MANAGER
# ═══════════════════════════════════════════════════════════════════════════════

class TaskManager:
    """Manages tasks: read from Obsidian, cache in memory, sync back."""

    def __init__(self, vault_path: str):
        self.vault_path = vault_path
        self.tasks_path = os.path.join(vault_path, "Tasks.md") if vault_path else ""
        self.tasks: dict[str, Task] = {}
        self.load_from_obsidian()

    def load_from_obsidian(self):
        """Parse Tasks.md and populate in-memory cache."""
        if not self.tasks_path or not os.path.exists(self.tasks_path):
            print("[TaskManager] Tasks.md nicht gefunden.", flush=True)
            self.tasks = {}
            return

        try:
            with open(self.tasks_path, "r", encoding="utf-8") as f:
                content = f.read()
            self.tasks = self._parse_tasks(content)
            print(f"[TaskManager] {len(self.tasks)} Tasks geladen.", flush=True)
        except Exception as e:
            print(f"[TaskManager] Fehler beim Laden: {e}", flush=True)
            self.tasks = {}

    def _parse_tasks(self, content: str) -> dict[str, Task]:
        """Parse markdown checkboxes into Task objects."""
        tasks = {}
        lines = content.split("\n")

        for line in lines:
            stripped = line.strip()
            if stripped.startswith("- [ ]") or stripped.startswith("- [x]"):
                status = "completed" if "[x]" in stripped else "open"
                title = stripped.replace("- [ ]", "").replace("- [x]", "").strip()
                if not title:
                    continue
                task_id = str(uuid4())
                task = Task(
                    id=task_id,
                    title=title,
                    status=status,
                )
                tasks[task_id] = task

        return tasks

    def get_all_tasks(self) -> List[Task]:
        """All tasks sorted: high priority first."""
        priority_order = {"high": 0, "medium": 1, "low": 2}
        return sorted(
            self.tasks.values(),
            key=lambda t: (
                priority_order.get(t.priority, 1),
                t.deadline or "9999-12-31",
            )
        )

    def get_open_tasks(self) -> List[Task]:
        """Only open tasks."""
        return [t for t in self.get_all_tasks() if t.status == "open"]

    def add_task(self, title: str, priority: str = "medium",
                 deadline: Optional[str] = None, tags: List[str] = None,
                 project: Optional[str] = None) -> Task:
        """Create new task and persist to Obsidian."""
        task_id = str(uuid4())
        task = Task(
            id=task_id,
            title=title,
            priority=priority,
            deadline=deadline,
            tags=tags or [],
            project=project,
            status="open",
        )
        self.tasks[task_id] = task
        self._persist_to_obsidian()
        print(f"[TaskManager] Task hinzugefügt: {title}", flush=True)
        return task

    def update_task(self, task_id: str, **kwargs) -> Optional[Task]:
        """Update task fields and persist."""
        if task_id not in self.tasks:
            return None
        task = self.tasks[task_id]
        for key, value in kwargs.items():
            if hasattr(task, key):
                setattr(task, key, value)
        task.updated = datetime.now().isoformat()
        self._persist_to_obsidian()
        print(f"[TaskManager] Task aktualisiert: {task_id}", flush=True)
        return task

    def delete_task(self, task_id: str) -> bool:
        """Remove task from cache and Obsidian."""
        if task_id in self.tasks:
            del self.tasks[task_id]
            self._persist_to_obsidian()
            print(f"[TaskManager] Task gelöscht: {task_id}", flush=True)
            return True
        return False

    def complete_task_by_text(self, task_text: str) -> str:
        """Mark task as completed by searching title (for voice commands)."""
        for task in self.tasks.values():
            if task_text.lower() in task.title.lower() and task.status == "open":
                task.status = "completed"
                task.updated = datetime.now().isoformat()
                self._persist_to_obsidian()
                return f"Erledigt: {task.title}"
        return f"Task nicht gefunden: {task_text}"

    def add_task_by_text(self, task_text: str) -> str:
        """Add task by plain text (for voice commands)."""
        task = self.add_task(title=task_text)
        return f"Task hinzugefügt: {task_text}"

    def _persist_to_obsidian(self):
        """Write all tasks back to Tasks.md."""
        if not self.tasks_path:
            return
        try:
            lines = [
                "---",
                "tags: [tasks]",
                "status: active",
                f"last_updated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
                "---",
                "",
                "# Offene Aufgaben",
                "",
            ]

            open_tasks = [t for t in self.get_all_tasks() if t.status == "open"]
            done_tasks = [t for t in self.get_all_tasks() if t.status == "completed"]

            for task in open_tasks:
                lines.append(f"- [ ] {task.title}")
            if open_tasks:
                lines.append("")

            if done_tasks:
                lines.append("## Erledigt")
                lines.append("")
                for task in done_tasks:
                    lines.append(f"- [x] {task.title}")

            content = "\n".join(lines)
            with open(self.tasks_path, "w", encoding="utf-8") as f:
                f.write(content)
            print(f"[TaskManager] {len(self.tasks)} Tasks gespeichert.", flush=True)
        except Exception as e:
            print(f"[TaskManager] Fehler beim Speichern: {e}", flush=True)


# ═══════════════════════════════════════════════════════════════════════════════
# FILE WATCHER
# ═══════════════════════════════════════════════════════════════════════════════

def start_file_watcher(vault_path: str, task_manager: TaskManager):
    """Watch Obsidian vault for changes and reload tasks."""
    try:
        from watchdog.observers import Observer
        from watchdog.events import FileSystemEventHandler

        class VaultHandler(FileSystemEventHandler):
            def on_modified(self, event):
                if event.src_path.endswith("Tasks.md"):
                    print("[Watcher] Tasks.md geändert – lade neu...", flush=True)
                    task_manager.load_from_obsidian()

        observer = Observer()
        observer.schedule(VaultHandler(), path=vault_path, recursive=False)
        observer.daemon = True
        observer.start()
        print(f"[Watcher] Beobachte: {vault_path}", flush=True)
    except ImportError:
        print("[Watcher] watchdog nicht installiert. Führe aus: pip install watchdog", flush=True)
    except Exception as e:
        print(f"[Watcher] Fehler: {e}", flush=True)


# ═══════════════════════════════════════════════════════════════════════════════
# WEBSOCKET BROADCAST
# ═══════════════════════════════════════════════════════════════════════════════

active_connections: List[WebSocket] = []

async def broadcast_to_clients(message: dict):
    """Send message to all connected WebSocket clients."""
    disconnected = []
    for ws in active_connections:
        try:
            await ws.send_json(message)
        except Exception:
            disconnected.append(ws)
    for ws in disconnected:
        if ws in active_connections:
            active_connections.remove(ws)


# ═══════════════════════════════════════════════════════════════════════════════
# WEATHER & DATA
# ═══════════════════════════════════════════════════════════════════════════════

def get_weather_sync():
    """Fetch raw weather data at startup."""
    import urllib.request
    try:
        req = urllib.request.Request(
            f"https://wttr.in/{CITY}?format=j1",
            headers={"User-Agent": "curl"}
        )
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


VAULT_SKIP_DIRS = {".obsidian", ".claude", ".claudian", ".trash", "07 Anhänge", ".git"}

def load_vault_context():
    """Dynamisch Kontext aus Vault-Dateien laden."""
    context = {}
    if not TASKS_FILE:
        return context

    files = {
        "about":       ("00 Kontext", "Über mich.md",    1000),
        "icp":         ("00 Kontext", "ICP.md",           800),
        "angebot":     ("00 Kontext", "Angebot.md",       800),
        "schreibstil": ("00 Kontext", "Schreibstil.md",   600),
        "books":       ("04 Ressourcen", "Bücher/Gelesene Bücher.md", 2000),
    }

    for key, (folder, filename, limit) in files.items():
        try:
            path = os.path.join(TASKS_FILE, folder, filename)
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    context[key] = f.read()[:limit]
        except:
            context[key] = None

    return context


def search_vault(query: str, max_results: int = 5, max_chars_per_file: int = 1500) -> list:
    """Search all markdown files in the vault for a query string."""
    if not TASKS_FILE or not os.path.isdir(TASKS_FILE):
        return []

    query_lower = query.lower()
    query_terms = query_lower.split()
    results = []

    for root, dirs, files in os.walk(TASKS_FILE):
        dirs[:] = [d for d in dirs if d not in VAULT_SKIP_DIRS]
        for filename in files:
            if not filename.endswith(".md"):
                continue
            filepath = os.path.join(root, filename)
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    content = f.read()
            except Exception:
                continue

            content_lower = content.lower()
            name_lower = filename.lower()

            score = 0
            for term in query_terms:
                if term in name_lower:
                    score += 3
                score += content_lower.count(term)

            if score > 0:
                rel_path = os.path.relpath(filepath, TASKS_FILE)
                results.append({
                    "file": rel_path,
                    "score": score,
                    "content": content[:max_chars_per_file],
                })

    results.sort(key=lambda r: r["score"], reverse=True)
    return results[:max_results]


def list_vault_files() -> list:
    """List all markdown files in the vault with their folder structure."""
    if not TASKS_FILE or not os.path.isdir(TASKS_FILE):
        return []

    files = []
    for root, dirs, filenames in os.walk(TASKS_FILE):
        dirs[:] = [d for d in dirs if d not in VAULT_SKIP_DIRS]
        for filename in filenames:
            if not filename.endswith(".md"):
                continue
            filepath = os.path.join(root, filename)
            rel_path = os.path.relpath(filepath, TASKS_FILE)
            size = os.path.getsize(filepath)
            files.append({"file": rel_path, "size": size})

    return files


def refresh_data():
    """Refresh weather and tasks."""
    global WEATHER_INFO
    WEATHER_INFO = get_weather_sync()
    TASK_MANAGER.load_from_obsidian()
    print(f"[jarvis] Wetter: {WEATHER_INFO}", flush=True)
    print(f"[jarvis] Tasks: {len(TASK_MANAGER.get_open_tasks())} offen", flush=True)


# ═══════════════════════════════════════════════════════════════════════════════
# INIT
# ═══════════════════════════════════════════════════════════════════════════════

WEATHER_INFO = ""
TASK_MANAGER = TaskManager(TASKS_FILE)

if TASKS_FILE:
    start_file_watcher(TASKS_FILE, TASK_MANAGER)

refresh_data()

ACTION_PATTERN = re.compile(r'\[ACTION:(\w+)\]\s*(.*?)$', re.DOTALL | re.MULTILINE)
conversations: dict[str, list] = {}


# ═══════════════════════════════════════════════════════════════════════════════
# SYSTEM PROMPT
# ═══════════════════════════════════════════════════════════════════════════════

def build_system_prompt():
    weather_block = ""
    if WEATHER_INFO:
        w = WEATHER_INFO
        weather_block = f"\nWetter {CITY}: {w['temp']}°C, gefuehlt {w['feels_like']}°C, {w['description']}"

    open_tasks = TASK_MANAGER.get_open_tasks()
    task_block = ""
    if open_tasks:
        task_titles = [t.title for t in open_tasks[:5]]
        task_block = f"\nOffene Aufgaben ({len(open_tasks)}): " + ", ".join(task_titles)

    vault_context = load_vault_context()
    context_block = ""
    if vault_context.get("about"):
        context_block += "\n=== JULIUS PROFIL ===\n" + vault_context["about"][:600]
    if vault_context.get("icp"):
        context_block += "\n\n=== ZIELGRUPPEN (ICP) ===\n" + vault_context["icp"][:500]
    if vault_context.get("angebot"):
        context_block += "\n\n=== SERVICES & ANGEBOT ===\n" + vault_context["angebot"][:500]
    if vault_context.get("schreibstil"):
        context_block += "\n\n=== SCHREIBSTIL ===\n" + vault_context["schreibstil"][:400]
    if vault_context.get("books"):
        context_block += "\n\n=== JULIUS' GELESENE BÜCHER & LEARNINGS ===\n" + vault_context["books"][:1500]

    return f"""Du bist Jarvis, der KI-Assistent von Tony Stark aus Iron Man. Dein Dienstherr ist Julius, selbstständiger Handelsverteter bei EKD Solar und angestellt bei Funke Medien. Du sprichst ausschliesslich Deutsch. Julius moechte mit "Sir" angesprochen und gesiezt werden. Nutze "Sie" als Pronomen — FALSCH: "Sir planen", RICHTIG: "Sie planen, Sir". Dein Ton ist trocken, sarkastisch und britisch-hoeflich - wie ein Butler der alles gesehen hat und trotzdem loyal bleibt. Du machst subtile, trockene Bemerkungen, bist aber niemals respektlos. Wenn Sir eine offensichtliche Frage stellt, darfst du mit elegantem Sarkasmus antworten. Du bist hochintelligent, effizient und immer einen Schritt voraus. Halte deine Antworten kurz - maximal 3 Saetze. Du kommentierst fragwuerdige Entscheidungen hoeflich aber spitz.

WICHTIG: Schreibe NIEMALS Regieanweisungen, Emotionen oder Tags in eckigen Klammern wie [sarcastic] [formal] [amused] [dry] oder aehnliches. Dein Sarkasmus muss REIN durch die Wortwahl kommen. Alles was du schreibst wird laut vorgelesen.

Du hast die volle Kontrolle ueber den Browser von Julius. Du kannst im Internet suchen, Webseiten oeffnen und den Bildschirm sehen. Wenn Sir dich bittet etwas nachzuschauen, zu recherchieren, zu googeln, eine Seite zu oeffnen, oder irgendetwas im Internet zu tun — nutze IMMER eine Aktion. Frag nicht ob du es tun sollst, tu es einfach.

AKTIONEN - Schreibe die passende Aktion ans ENDE deiner Antwort. Der Text VOR der Aktion wird vorgelesen, die Aktion selbst wird still ausgefuehrt.
[ACTION:SEARCH] suchbegriff - Internet durchsuchen und Ergebnisse zusammenfassen
[ACTION:OPEN] url - URL im Browser oeffnen
[ACTION:SCREEN] - Bildschirm ansehen und beschreiben. WICHTIG: Bei SCREEN schreibe NUR die Aktion, KEINEN Text davor. Also NUR "[ACTION:SCREEN]" und sonst nichts.
[ACTION:NEWS] - Aktuelle Weltnachrichten abrufen.
[ACTION:ADD_TASK] Aufgabenbeschreibung - Neue Task zu Obsidian Tasks.md hinzufuegen.
[ACTION:COMPLETE_TASK] Aufgabenbeschreibung - Task in Obsidian als erledigt markieren.
[ACTION:VAULT_SEARCH] suchbegriff - Im Obsidian Vault nach Notizen, Projekten, Ressourcen suchen. Nutze das wenn Sir nach seinen Notizen, Projekten, Zielen, Kunden, Finanzen, Buechern oder anderen Vault-Inhalten fragt.

WENN Sir "Jarvis activate" sagt:
- Begruesse ihn passend zur Tageszeit (aktuelle Zeit: {{time}}).
- Gebe eine kurze Info ueber das Wetter.
- Fasse die Aufgaben kurz zusammen, ohne jede einzelne vorzulesen.
- Sei kreativ bei der Begruessung.

=== VAULT-KONTEXT (Automatisch geladen) ==={context_block}

=== AKTUELLE DATEN ==={weather_block}{task_block}
==="""


def get_system_prompt():
    return build_system_prompt().replace("{time}", time.strftime("%H:%M"))


def extract_action(text: str):
    match = ACTION_PATTERN.search(text)
    if match:
        clean = text[:match.start()].strip()
        return clean, {"type": match.group(1), "payload": match.group(2).strip()}
    return text, None


# ═══════════════════════════════════════════════════════════════════════════════
# TTS (Browser Fallback)
# ═══════════════════════════════════════════════════════════════════════════════

async def synthesize_speech(text: str) -> bytes:
    """TTS disabled — browser Web Speech API handles it."""
    if not text.strip():
        return b""
    return b""


# ═══════════════════════════════════════════════════════════════════════════════
# ACTION EXECUTOR
# ═══════════════════════════════════════════════════════════════════════════════

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
        return await browser_tools.fetch_news()

    elif t == "ADD_TASK":
        result = TASK_MANAGER.add_task_by_text(p)
        await broadcast_to_clients({"type": "tasks_updated"})
        return result

    elif t == "COMPLETE_TASK":
        result = TASK_MANAGER.complete_task_by_text(p)
        await broadcast_to_clients({"type": "tasks_updated"})
        return result

    elif t == "VAULT_SEARCH":
        results = search_vault(p, max_results=3, max_chars_per_file=2000)
        if not results:
            return f"Keine Vault-Einträge gefunden für: {p}"
        parts = []
        for r in results:
            parts.append(f"=== {r['file']} ===\n{r['content']}")
        return "\n\n".join(parts)

    return ""


# ═══════════════════════════════════════════════════════════════════════════════
# MESSAGE PROCESSOR
# ═══════════════════════════════════════════════════════════════════════════════

async def process_message(session_id: str, user_text: str, ws: WebSocket):
    """Process message and send responses via WebSocket."""
    if session_id not in conversations:
        conversations[session_id] = []

    if "activate" in user_text.lower():
        refresh_data()

    conversations[session_id].append({"role": "user", "content": user_text})
    history = conversations[session_id][-16:]

    response = await ai.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=400,
        system=get_system_prompt(),
        messages=history,
    )
    reply = response.content[0].text
    print(f"  LLM raw: {reply[:200]}", flush=True)
    spoken_text, action = extract_action(reply)

    if spoken_text:
        audio = await synthesize_speech(spoken_text)
        print(f"  Jarvis: {spoken_text[:80]}", flush=True)
        conversations[session_id].append({"role": "assistant", "content": spoken_text})
        await ws.send_json({
            "type": "response",
            "text": spoken_text,
            "audio": base64.b64encode(audio).decode("utf-8") if audio else "",
        })

    if action:
        print(f"  Action: {action['type']} -> {action['payload'][:100]}", flush=True)

        if action["type"] == "SCREEN":
            hint = "Lassen Sie mich einen Blick auf Ihren Bildschirm werfen."
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
            action_result = f"Fehler: {e}"

        if action["type"] == "OPEN":
            return

        if action_result and "fehlgeschlagen" not in action_result:
            summary_resp = await ai.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=250,
                system=f"Du bist Jarvis. Fasse die folgenden Informationen KURZ auf Deutsch zusammen, maximal 3 Saetze, im Jarvis-Stil. Sprich den Nutzer als {USER_ADDRESS} an. KEINE Tags in eckigen Klammern. KEINE ACTION-Tags.",
                messages=[{"role": "user", "content": f"Fasse zusammen:\n\n{action_result}"}],
            )
            summary = summary_resp.content[0].text
            summary, _ = extract_action(summary)
        else:
            summary = f"Das hat leider nicht funktioniert, {USER_ADDRESS}."

        audio2 = await synthesize_speech(summary)
        conversations[session_id].append({"role": "assistant", "content": summary})
        await ws.send_json({
            "type": "response",
            "text": summary,
            "audio": base64.b64encode(audio2).decode("utf-8") if audio2 else "",
        })


# ═══════════════════════════════════════════════════════════════════════════════
# REST API – TASK MANAGEMENT
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/api/tasks")
async def get_tasks(status: str = None):
    """Fetch tasks. Optional: ?status=open"""
    try:
        if status == "open":
            tasks = TASK_MANAGER.get_open_tasks()
        else:
            tasks = TASK_MANAGER.get_all_tasks()
        return {
            "tasks": [asdict(t) for t in tasks],
            "count": len(tasks),
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        return {"error": str(e), "tasks": []}


@app.post("/api/tasks")
async def create_task(request: Request):
    """Create new task. Body: { title, priority?, deadline?, tags?, project? }"""
    try:
        body = await request.json()
        title = body.get("title", "").strip()
        if not title:
            return {"error": "Titel erforderlich", "created": False}
        task = TASK_MANAGER.add_task(
            title=title,
            priority=body.get("priority", "medium"),
            deadline=body.get("deadline"),
            tags=body.get("tags", []),
            project=body.get("project"),
        )
        await broadcast_to_clients({"type": "tasks_updated", "task": asdict(task)})
        return {"task": asdict(task), "created": True}
    except Exception as e:
        return {"error": str(e), "created": False}


@app.put("/api/tasks/{task_id}")
async def update_task(task_id: str, request: Request):
    """Update task fields."""
    try:
        body = await request.json()
        task = TASK_MANAGER.update_task(task_id, **body)
        if not task:
            return {"error": "Task nicht gefunden", "updated": False}
        await broadcast_to_clients({"type": "tasks_updated", "task": asdict(task)})
        return {"task": asdict(task), "updated": True}
    except Exception as e:
        return {"error": str(e), "updated": False}


@app.delete("/api/tasks/{task_id}")
async def delete_task(task_id: str):
    """Delete task by ID."""
    try:
        success = TASK_MANAGER.delete_task(task_id)
        if not success:
            return {"error": "Task nicht gefunden", "deleted": False}
        await broadcast_to_clients({"type": "task_deleted", "task_id": task_id})
        return {"task_id": task_id, "deleted": True}
    except Exception as e:
        return {"error": str(e), "deleted": False}


@app.get("/api/vault/search")
async def vault_search_endpoint(q: str = ""):
    """Search vault files. Usage: /api/vault/search?q=keyword"""
    if not q.strip():
        return {"error": "Query parameter 'q' required", "results": []}
    results = search_vault(q.strip())
    return {"query": q, "results": results, "count": len(results)}


@app.get("/api/vault/files")
async def vault_files_endpoint():
    """List all markdown files in the vault."""
    files = list_vault_files()
    return {"files": files, "count": len(files)}


@app.get("/api/vault/read")
async def vault_read_endpoint(path: str = ""):
    """Read a specific vault file. Usage: /api/vault/read?path=00 Kontext/Über mich.md"""
    if not path.strip() or not TASKS_FILE:
        return {"error": "Parameter 'path' required"}
    filepath = os.path.join(TASKS_FILE, path)
    if not os.path.realpath(filepath).startswith(os.path.realpath(TASKS_FILE)):
        return {"error": "Zugriff verweigert"}
    if not os.path.exists(filepath):
        return {"error": f"Datei nicht gefunden: {path}"}
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
        return {"path": path, "content": content, "size": len(content)}
    except Exception as e:
        return {"error": str(e)}


@app.post("/api/refresh")
async def refresh_endpoint():
    """Manually refresh tasks from Obsidian."""
    try:
        TASK_MANAGER.load_from_obsidian()
        tasks = TASK_MANAGER.get_all_tasks()
        await broadcast_to_clients({"type": "tasks_updated"})
        return {"refreshed": True, "count": len(tasks), "timestamp": datetime.now().isoformat()}
    except Exception as e:
        return {"error": str(e), "refreshed": False}


# ═══════════════════════════════════════════════════════════════════════════════
# WEBSOCKET
# ═══════════════════════════════════════════════════════════════════════════════

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    session_id = str(id(ws))
    active_connections.append(ws)
    print(f"[jarvis] Client verbunden. Aktive Sessions: {len(active_connections)}", flush=True)

    try:
        while True:
            data = await ws.receive_json()
            user_text = data.get("text", "").strip()

            # Handle refresh request from frontend
            if data.get("type") == "refresh_tasks":
                TASK_MANAGER.load_from_obsidian()
                tasks = TASK_MANAGER.get_open_tasks()
                await ws.send_json({
                    "type": "tasks_updated",
                    "tasks": [asdict(t) for t in tasks],
                })
                continue

            if not user_text:
                continue

            print(f"  You:    {user_text}", flush=True)
            await process_message(session_id, user_text, ws)

    except WebSocketDisconnect:
        conversations.pop(session_id, None)
        if ws in active_connections:
            active_connections.remove(ws)
        print(f"[jarvis] Client getrennt. Aktive Sessions: {len(active_connections)}", flush=True)


# ═══════════════════════════════════════════════════════════════════════════════
# STATIC FILES & ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

app.mount(
    "/static",
    StaticFiles(directory=os.path.join(os.path.dirname(__file__), "frontend")),
    name="static"
)


@app.get("/")
async def serve_index():
    return FileResponse(os.path.join(os.path.dirname(__file__), "frontend", "index.html"))


if __name__ == "__main__":
    import uvicorn
    print("=" * 50, flush=True)
    print("  J.A.R.V.I.S. V2.1 Server", flush=True)
    print(f"  http://localhost:8340", flush=True)
    print("=" * 50, flush=True)
    uvicorn.run(app, host="0.0.0.0", port=8340)
