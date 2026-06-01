// Jarvis V2 — Premium Frontend
const orb = document.getElementById('orb');
const status = document.getElementById('status');
const statusBadge = document.querySelector('.status-text');
const transcript = document.getElementById('transcript');
const textInput = document.getElementById('text-input');
const sendBtn = document.getElementById('send-btn');

// Info Panel Elements
const infoPanel = document.getElementById('info-panel');
const overlay = document.getElementById('overlay');
const infoPanelTitle = document.getElementById('info-title');
const infoPanelBody = document.getElementById('info-body');
const closeInfoBtn = document.getElementById('close-info-btn');
const infoCloseActionBtn = document.getElementById('info-close-action');

let ws;
let audioQueue = [];
let isPlaying = false;
let audioUnlocked = false;
let isListening = false;

// ═══════════════════════════════════════════════════════════════════════════════
// AUDIO UNLOCK
// ═══════════════════════════════════════════════════════════════════════════════

function unlockAudio() {
    if (!audioUnlocked) {
        const silent = new Audio('data:audio/mp3;base64,SUQzBAAAAAAAI1RTU0UAAAAPAAADTGF2ZjU4Ljc2LjEwMAAAAAAAAAAAAAAA//tQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAWGluZwAAAA8AAAACAAABhgC7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7//////////////////////////////////////////////////////////////////8AAAAATGF2YzU4LjEzAAAAAAAAAAAAAAAAJAAAAAAAAAAAAYZNIGPkAAAAAAAAAAAAAAAAAAAA//tQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAWGluZwAAAA8AAAACAAABhgC7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7//////////////////////////////////////////////////////////////////8AAAAATGF2YzU4LjEzAAAAAAAAAAAAAAAAJAAAAAAAAAAAAYZNIGPkAAAAAAAAAAAAAAAAAAAA');
        silent.play().then(() => {
            audioUnlocked = true;
            console.log('[jarvis] Audio unlocked');
        }).catch(() => {});
    }
}

document.addEventListener('click', unlockAudio, { once: false });
document.addEventListener('touchstart', unlockAudio, { once: false });
document.addEventListener('keydown', unlockAudio, { once: false });

// ═══════════════════════════════════════════════════════════════════════════════
// WEBSOCKET & COMMUNICATION
// ═══════════════════════════════════════════════════════════════════════════════

function connect() {
    ws = new WebSocket(`ws://${location.host}/ws`);

    ws.onopen = () => {
        console.log('[jarvis] WebSocket connected');
        updateStatus('Bereit', 'connecting');
        setOrbState('thinking');
        ws.send(JSON.stringify({ text: 'Jarvis activate' }));
    };

    ws.onmessage = (event) => {
        const data = JSON.parse(event.data);

        if (data.type === 'response') {
            addTranscript('jarvis', data.text);
            window.lastJarvisResponse = data.text;

            // Prüfe ob es eine Informations-Anfrage ist
            // (später: komplexere Logik für verschiedene Antworttypen)
            if (data.type === 'response') {
                speakWithBrowserAPI(data.text);
            }
        } else if (data.type === 'tasks_updated' || data.type === 'task_deleted') {
            loadTasks();
        } else if (data.type === 'status') {
            status.textContent = data.text;
        }
    };

    ws.onclose = () => {
        updateStatus('Verbindung verloren', 'error');
        setTimeout(connect, 3000);
    };

    ws.onerror = (error) => {
        console.error('[jarvis] WebSocket error:', error);
        updateStatus('Fehler', 'error');
    };
}

function sendMessage(text) {
    if (!text.trim() || !ws || ws.readyState !== WebSocket.OPEN) return;

    addTranscript('user', text);
    textInput.value = '';
    setOrbState('thinking');
    updateStatus('Denke...', 'thinking');

    ws.send(JSON.stringify({ text }));
}

// ═══════════════════════════════════════════════════════════════════════════════
// TRANSCRIPT MANAGEMENT
// ═══════════════════════════════════════════════════════════════════════════════

function addTranscript(role, text) {
    const item = document.createElement('div');
    item.className = `transcript-item ${role}`;
    item.textContent = text;
    transcript.appendChild(item);
    transcript.scrollTop = transcript.scrollHeight;
}

// ═══════════════════════════════════════════════════════════════════════════════
// ORB & STATUS MANAGEMENT
// ═══════════════════════════════════════════════════════════════════════════════

function setOrbState(state) {
    orb.className = state;

    if (state === 'listening' && !isListening) {
        isListening = true;
        startListening();
    } else if (state !== 'listening' && isListening) {
        shouldKeepListening = false;
        isListening = false;
    }
}

function updateStatus(message, type = 'idle') {
    status.textContent = message;
    if (statusBadge) {
        statusBadge.textContent = message;
    }
}

// ═══════════════════════════════════════════════════════════════════════════════
// SPEECH SYNTHESIS & AUDIO
// ═══════════════════════════════════════════════════════════════════════════════

function speakWithBrowserAPI(text) {
    if (!('speechSynthesis' in window)) {
        console.warn('[jarvis] Browser Speech Synthesis not available');
        setOrbState('idle');
        return;
    }

    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = 'de-DE';
    utterance.rate = 1.0;
    utterance.pitch = 1.0;
    utterance.volume = 1.0;

    utterance.onstart = () => {
        isPlaying = true;
        setOrbState('speaking');
        updateStatus('Spricht...', 'speaking');
    };

    utterance.onend = () => {
        isPlaying = false;
        setOrbState('listening');
        updateStatus('Höre...', 'listening');
    };

    utterance.onerror = (event) => {
        console.error('[jarvis] Speech synthesis error:', event.error);
        isPlaying = false;
        setOrbState('idle');
        updateStatus('Fehler', 'error');
    };

    speechSynthesis.cancel();
    speechSynthesis.speak(utterance);
}

// ═══════════════════════════════════════════════════════════════════════════════
// SPEECH RECOGNITION
// ═══════════════════════════════════════════════════════════════════════════════

let recognition;
let isRecognizing = false;
let shouldKeepListening = false;

function startListening() {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

    if (!SpeechRecognition) {
        console.warn('[jarvis] Speech Recognition not available');
        return;
    }

    if (isRecognizing) return;

    shouldKeepListening = true;

    recognition = new SpeechRecognition();
    recognition.lang = 'de-DE';
    recognition.continuous = false;
    recognition.interimResults = true;

    recognition.onstart = () => {
        isRecognizing = true;
        updateStatus('Hört zu...', 'listening');
    };

    recognition.onresult = (event) => {
        let finalTranscript = '';
        let interimTranscript = '';

        for (let i = event.resultIndex; i < event.results.length; i++) {
            const result = event.results[i];
            if (result.isFinal) {
                finalTranscript += result[0].transcript;
            } else {
                interimTranscript += result[0].transcript;
            }
        }

        if (interimTranscript) {
            updateStatus(`"${interimTranscript}..."`, 'listening');
        }

        if (finalTranscript.trim()) {
            shouldKeepListening = false;
            isRecognizing = false;
            sendMessage(finalTranscript.trim());
        }
    };

    recognition.onend = () => {
        isRecognizing = false;
        if (shouldKeepListening && isListening && ws && ws.readyState === WebSocket.OPEN) {
            setTimeout(() => {
                if (shouldKeepListening && isListening) {
                    try { recognition.start(); } catch (e) {}
                }
            }, 100);
        } else if (!isPlaying) {
            setOrbState('idle');
        }
    };

    recognition.onerror = (event) => {
        isRecognizing = false;
        if (event.error === 'no-speech' && shouldKeepListening && isListening) {
            setTimeout(() => {
                if (shouldKeepListening && isListening) {
                    try { recognition.start(); } catch (e) {}
                }
            }, 100);
            return;
        }
        if (event.error !== 'aborted') {
            console.error('[jarvis] Speech recognition error:', event.error);
        }
    };

    try {
        recognition.start();
    } catch (e) {
        console.warn('[jarvis] Recognition already started:', e);
    }
}

function stopListening() {
    shouldKeepListening = false;
    isListening = false;
    isRecognizing = false;
    if (recognition) {
        try { recognition.stop(); } catch (e) {}
    }
}

// ═══════════════════════════════════════════════════════════════════════════════
// INFO PANEL MANAGEMENT
// ═══════════════════════════════════════════════════════════════════════════════

function showInfoPanel(title, content) {
    infoPanelTitle.textContent = title;
    infoPanelBody.innerHTML = content;
    infoPanel.classList.remove('hidden');
    overlay.classList.remove('hidden');
}

function hideInfoPanel() {
    infoPanel.classList.add('hidden');
    overlay.classList.add('hidden');
}

closeInfoBtn.addEventListener('click', hideInfoPanel);
infoCloseActionBtn.addEventListener('click', hideInfoPanel);
overlay.addEventListener('click', hideInfoPanel);

// Prevent click inside panel from closing it
infoPanel.addEventListener('click', (e) => {
    e.stopPropagation();
});

// ═══════════════════════════════════════════════════════════════════════════════
// INPUT HANDLING
// ═══════════════════════════════════════════════════════════════════════════════

orb.addEventListener('click', () => {
    if (isPlaying) {
        speechSynthesis.cancel();
        isPlaying = false;
        stopListening();
        setOrbState('idle');
    } else if (isListening || isRecognizing) {
        stopListening();
        setOrbState('idle');
    } else {
        setOrbState('listening');
        startListening();
    }
});

sendBtn.addEventListener('click', () => {
    const text = textInput.value.trim();
    if (text) {
        sendMessage(text);
    }
});

textInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') {
        const text = textInput.value.trim();
        if (text) {
            sendMessage(text);
        }
    }
});

textInput.addEventListener('focus', () => {
    if (isRecognizing) {
        if (recognition) {
            recognition.stop();
        }
        isRecognizing = false;
    }
});

// ═══════════════════════════════════════════════════════════════════════════════
// INITIALIZATION
// ═══════════════════════════════════════════════════════════════════════════════

window.addEventListener('load', () => {
    setOrbState('idle');
    updateStatus('Initialisiere...', 'idle');
    connect();
    loadTasks();
});

// ═══════════════════════════════════════════════════════════════════════════════
// TASK PANEL
// ═══════════════════════════════════════════════════════════════════════════════

const taskPanel = document.getElementById('task-panel');
const taskList = document.getElementById('task-list');
const taskInput = document.getElementById('task-input');
const taskAddBtn = document.getElementById('task-add-btn');
const taskPanelToggle = document.getElementById('task-panel-toggle');

let taskPanelOpen = true;

function toggleTaskPanel() {
    taskPanelOpen = !taskPanelOpen;
    taskPanel.classList.toggle('collapsed', !taskPanelOpen);
}

taskPanelToggle.addEventListener('click', toggleTaskPanel);

async function loadTasks() {
    try {
        const resp = await fetch('/api/tasks');
        const data = await resp.json();
        renderTasks(data.tasks || []);
    } catch (e) {
        taskList.innerHTML = '<div class="task-empty">Tasks konnten nicht geladen werden.</div>';
    }
}

function renderTasks(tasks) {
    if (!tasks.length) {
        taskList.innerHTML = '<div class="task-empty">Keine Aufgaben vorhanden.</div>';
        return;
    }

    taskList.innerHTML = '';
    const open = tasks.filter(t => t.status === 'open');
    const done = tasks.filter(t => t.status === 'completed');

    open.forEach(t => taskList.appendChild(createTaskEl(t)));

    if (done.length) {
        const divider = document.createElement('div');
        divider.className = 'task-divider';
        divider.textContent = `Erledigt (${done.length})`;
        taskList.appendChild(divider);
        done.forEach(t => taskList.appendChild(createTaskEl(t)));
    }
}

function createTaskEl(task) {
    const el = document.createElement('div');
    el.className = `task-item ${task.status === 'completed' ? 'done' : ''}`;

    const checkbox = document.createElement('button');
    checkbox.className = 'task-checkbox';
    checkbox.innerHTML = task.status === 'completed' ? '&#10003;' : '';
    checkbox.addEventListener('click', () => toggleTask(task.id, task.status));

    const title = document.createElement('span');
    title.className = 'task-title';
    title.textContent = task.title;

    const del = document.createElement('button');
    del.className = 'task-delete';
    del.textContent = '×';
    del.addEventListener('click', () => deleteTask(task.id));

    el.appendChild(checkbox);
    el.appendChild(title);
    el.appendChild(del);
    return el;
}

async function toggleTask(id, currentStatus) {
    const newStatus = currentStatus === 'open' ? 'completed' : 'open';
    try {
        await fetch(`/api/tasks/${id}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ status: newStatus }),
        });
        loadTasks();
    } catch (e) {}
}

async function deleteTask(id) {
    try {
        await fetch(`/api/tasks/${id}`, { method: 'DELETE' });
        loadTasks();
    } catch (e) {}
}

async function addTask() {
    const title = taskInput.value.trim();
    if (!title) return;
    try {
        await fetch('/api/tasks', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ title }),
        });
        taskInput.value = '';
        loadTasks();
    } catch (e) {}
}

taskAddBtn.addEventListener('click', addTask);
taskInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') addTask();
});

// ═══════════════════════════════════════════════════════════════════════════════
// EXPORT FUNCTIONS FOR EXTERNAL USE
// ═══════════════════════════════════════════════════════════════════════════════

window.jarvisAPI = {
    showInfo: showInfoPanel,
    hideInfo: hideInfoPanel,
    sendMessage: sendMessage,
    speak: speakWithBrowserAPI,
    loadTasks: loadTasks,
};
