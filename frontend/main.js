// J.A.R.V.I.S. — Frontend HUD logic
const orb = document.getElementById('orb');
const statusEl = document.getElementById('status');
const transcript = document.getElementById('transcript');
const visualizer = document.getElementById('visualizer');
const hudTime = document.getElementById('hud-time');
const hudStatus = document.getElementById('hud-status');

let ws;
let audioQueue = [];
let isPlaying = false;
let audioUnlocked = false;
let audioCtx = null;
let analyser = null;
let currentSourceNode = null;
let currentAudioEl = null;     // the <audio> currently playing — used to interrupt
let currentAudioUrl = null;    // matching object URL so we can revoke on stop

/* ==========================================================
   HUD clock
   ========================================================== */
function tickClock() {
    const d = new Date();
    const hh = String(d.getHours()).padStart(2, '0');
    const mm = String(d.getMinutes()).padStart(2, '0');
    const ss = String(d.getSeconds()).padStart(2, '0');
    hudTime.textContent = `${hh}:${mm}:${ss}`;
}
setInterval(tickClock, 1000); tickClock();

/* ==========================================================
   Audio unlock (Chrome autoplay policy)
   ========================================================== */
function unlockAudio() {
    if (!audioUnlocked) {
        const silent = new Audio('data:audio/mp3;base64,SUQzBAAAAAAAI1RTU0UAAAAPAAADTGF2ZjU4Ljc2LjEwMAAAAAAAAAAAAAAA//tQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAWGluZwAAAA8AAAACAAABhgC7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7//////////////////////////////////////////////////////////////////8AAAAATGF2YzU4LjEzAAAAAAAAAAAAAAAAJAAAAAAAAAAAAYZNIGPkAAAAAAAAAAAAAAAAAAAA//tQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAWGluZwAAAA8AAAACAAABhgC7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7//////////////////////////////////////////////////////////////////8AAAAATGF2YzU4LjEzAAAAAAAAAAAAAAAAJAAAAAAAAAAAAYZNIGPkAAAAAAAAAAAAAAAAAAAA');
        silent.play().then(() => {
            audioUnlocked = true;
            try { audioCtx = new (window.AudioContext || window.webkitAudioContext)(); } catch(e) {}
            console.log('[jarvis] Audio unlocked');
        }).catch(() => {});
    }
}
document.addEventListener('click', unlockAudio, { once: false });
document.addEventListener('touchstart', unlockAudio, { once: false });
document.addEventListener('keydown', unlockAudio, { once: false });

/* ==========================================================
   WebSocket
   ========================================================== */
function connect() {
    ws = new WebSocket(`ws://${location.host}/ws`);
    ws.onopen = () => {
        console.log('[jarvis] WS connected');
        setStatus('Klicken Sie irgendwo, dann begrüßt Sie Jarvis.');
        setOrbState('thinking');
        hudStatus.textContent = 'CONNECTED';
        wsSend({ text: 'Jarvis activate' });
    };
    ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        if (data.type === 'response') {
            addTranscript('jarvis', data.text);
            if (data.audio && data.audio.length > 0) {
                queueAudio(data.audio, data.mime || 'audio/mpeg');
            } else {
                setOrbState('idle');
                setTimeout(startListening, 500);
            }
        } else if (data.type === 'status') {
            setStatus(data.text);
        }
    };
    ws.onerror = (e) => {
        console.warn('[jarvis] WebSocket error', e);
    };
    ws.onclose = () => {
        setStatus('Verbindung verloren — verbinde neu …');
        hudStatus.textContent = 'OFFLINE';
        setOrbState('idle');
        setTimeout(connect, 3000);
    };
}

function wsSend(payload) {
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify(payload));
        return true;
    }
    return false;
}

/* ==========================================================
   Audio queue + visualizer
   ========================================================== */
function queueAudio(base64Audio, mime) {
    audioQueue.push({ b64: base64Audio, mime: mime || 'audio/mpeg' });
    if (!isPlaying) playNext();
}

function playNext() {
    if (audioQueue.length === 0) {
        isPlaying = false;
        stopVisualizer();
        setOrbState('listening');
        setStatus('');
        setTimeout(startListening, 400);
        return;
    }
    isPlaying = true;
    setOrbState('speaking');
    setStatus('Jarvis spricht …');
    if (isListening) {
        try { recognition.stop(); } catch(e) {}
        isListening = false;
    }

    const item = audioQueue.shift();
    const b64 = item.b64;
    const mime = item.mime;
    const bytes = Uint8Array.from(atob(b64), c => c.charCodeAt(0));
    const blob = new Blob([bytes], { type: mime });
    const url = URL.createObjectURL(blob);
    const audio = new Audio(url);

    currentAudioEl = audio;
    currentAudioUrl = url;

    audio.onplay = () => attachVisualizer(audio);
    audio.onended = () => {
        if (currentAudioUrl === url) { URL.revokeObjectURL(url); currentAudioEl = null; currentAudioUrl = null; }
        playNext();
    };
    audio.onerror = () => {
        if (currentAudioUrl === url) { URL.revokeObjectURL(url); currentAudioEl = null; currentAudioUrl = null; }
        playNext();
    };
    audio.play().catch(() => {
        console.warn('[jarvis] Autoplay blocked');
        setStatus('Klicken Sie, damit Jarvis sprechen kann.');
        setOrbState('idle');
        document.addEventListener('click', function retry() {
            document.removeEventListener('click', retry);
            audio.play().then(() => { setOrbState('speaking'); setStatus(''); }).catch(() => playNext());
        });
    });
}

/* Stop Jarvis mid-speech: clear the queue, halt current audio, return to listening. */
function interruptJarvis() {
    if (!isPlaying && audioQueue.length === 0) return;
    audioQueue = [];
    if (currentAudioEl) {
        try { currentAudioEl.pause(); } catch(e) {}
        try { currentAudioEl.src = ''; } catch(e) {}
        if (currentAudioUrl) { try { URL.revokeObjectURL(currentAudioUrl); } catch(e) {} }
        currentAudioEl = null;
        currentAudioUrl = null;
    }
    isPlaying = false;
    stopVisualizer();
    setOrbState('listening');
    setStatus('— gestoppt —');
    setTimeout(() => { setStatus(''); startListening(); }, 200);
}

function attachVisualizer(audioEl) {
    // WebAudio's createMediaElementSource() can be called only ONCE per element,
    // and throws on a second attach — we mark the element to skip re-wiring.
    if (audioEl.__jarvisVizAttached) {
        return;
    }
    if (!audioCtx) {
        try { audioCtx = new (window.AudioContext || window.webkitAudioContext)(); } catch(e) { return; }
    }
    try {
        if (currentSourceNode) try { currentSourceNode.disconnect(); } catch(e) {}
        currentSourceNode = audioCtx.createMediaElementSource(audioEl);
        audioEl.__jarvisVizAttached = true;
        analyser = audioCtx.createAnalyser();
        analyser.fftSize = 128;
        currentSourceNode.connect(analyser);
        analyser.connect(audioCtx.destination);
        drawVisualizer();
    } catch(e) {
        // Don't crash audio playback if visualizer fails — just log.
        console.warn('[jarvis] Visualizer attach failed:', e);
    }
}

function stopVisualizer() {
    analyser = null;
    const ctx = visualizer.getContext('2d');
    ctx.clearRect(0, 0, visualizer.width, visualizer.height);
}

function drawVisualizer() {
    const ctx = visualizer.getContext('2d');
    const W = visualizer.width;
    const H = visualizer.height;
    const cx = W / 2;
    const cy = H / 2;

    function frame() {
        if (!analyser) return;
        const data = new Uint8Array(analyser.frequencyBinCount);
        analyser.getByteFrequencyData(data);

        ctx.clearRect(0, 0, W, H);

        // Energy-based outer ring — desaturated emerald, no glow
        const bars = data.length;
        const baseRadius = 168;
        const maxBar = 56;

        ctx.lineWidth = 1.2;
        ctx.strokeStyle = 'rgba(58, 163, 126, 0.7)';
        ctx.shadowBlur = 0;

        for (let i = 0; i < bars; i++) {
            const v = data[i] / 255;
            const angle = (i / bars) * Math.PI * 2 - Math.PI / 2;
            const r1 = baseRadius;
            const r2 = baseRadius + v * maxBar;
            const x1 = cx + Math.cos(angle) * r1;
            const y1 = cy + Math.sin(angle) * r1;
            const x2 = cx + Math.cos(angle) * r2;
            const y2 = cy + Math.sin(angle) * r2;
            ctx.beginPath();
            ctx.moveTo(x1, y1);
            ctx.lineTo(x2, y2);
            ctx.stroke();
        }

        ctx.shadowBlur = 0;
        requestAnimationFrame(frame);
    }
    frame();
}

/* ==========================================================
   Speech recognition
   ========================================================== */
const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
let recognition;
let isListening = false;

if (SpeechRecognition) {
    recognition = new SpeechRecognition();
    recognition.lang = 'de-DE';
    recognition.continuous = true;
    recognition.interimResults = false;

    fetch('/config').then(r => r.json()).then(cfg => {
        if (cfg.speech_lang) {
            recognition.lang = cfg.speech_lang;
            console.log('[jarvis] Speech recognition language:', cfg.speech_lang);
        }
        // Update HUD footer with the actual live TTS backend so the Boss knows
        // which voice is speaking (ElevenLabs / Edge Neural / macOS say).
        if (cfg.tts_backend) {
            const el = document.getElementById('hud-backend');
            if (el) el.textContent = 'VOICE: ' + cfg.tts_backend;
        }
    }).catch(() => {});

    recognition.onresult = (event) => {
        const last = event.results[event.results.length - 1];
        if (last.isFinal) {
            const text = last[0].transcript.trim();
            if (text) {
                addTranscript('user', text);
                setOrbState('thinking');
                setStatus('Jarvis denkt nach …');
                if (!wsSend({ text })) {
                    setStatus('Verbindung weg — neuversuch …');
                }
            }
        }
    };
    recognition.onend = () => {
        isListening = false;
        if (!isPlaying) setTimeout(startListening, 250);
    };
    recognition.onerror = (event) => {
        isListening = false;
        if (event.error === 'no-speech' || event.error === 'aborted') {
            if (!isPlaying) setTimeout(startListening, 250);
        } else {
            setTimeout(startListening, 800);
        }
    };
}

function startListening() {
    if (isPlaying || isListening) return;
    try {
        recognition.start();
        isListening = true;
        setOrbState('listening');
        setStatus('');
    } catch(e) {
        if (e.name !== 'InvalidStateError') console.warn('[jarvis] recognition.start failed', e);
    }
}

orb.addEventListener('click', (e) => {
    e.stopPropagation();
    // While Jarvis is speaking, click = INTERRUPT
    if (isPlaying) { interruptJarvis(); return; }
    if (isListening) {
        try { recognition.stop(); } catch(e) {}
        isListening = false;
        setOrbState('idle');
        setStatus('Pausiert — klicken zum Fortsetzen');
    } else {
        startListening();
    }
});

/* Keyboard: Space or Escape interrupts Jarvis when he's speaking. */
document.addEventListener('keydown', (e) => {
    if (isPlaying && (e.code === 'Space' || e.code === 'Escape')) {
        e.preventDefault();
        interruptJarvis();
    }
});

/* ==========================================================
   UI helpers
   ========================================================== */
function setOrbState(state) {
    orb.className = state;
    const lbl = document.getElementById('state-current');
    if (lbl) {
        const map = { idle: 'IDLE', listening: 'LISTENING', thinking: 'THINKING', speaking: 'SPEAKING' };
        lbl.textContent = map[state] || state.toUpperCase();
    }
}

function setStatus(t) { statusEl.textContent = t || ''; }

function addTranscript(role, text) {
    const div = document.createElement('div');
    div.className = role;
    div.textContent = text;
    transcript.appendChild(div);
    transcript.scrollTop = transcript.scrollHeight;
}

/* ==========================================================
   Init — wait for first user click before starting audio + WebSocket.
   Chrome's autoplay policy blocks all audio until a real user gesture,
   so doing this gate prevents the silent-Jarvis bug entirely.
   ========================================================== */
function startSession() {
    const overlay = document.getElementById('start-overlay');
    if (overlay) overlay.classList.add('hidden');
    unlockAudio();
    // Slight delay so the unlock audio finishes resuming the AudioContext.
    setTimeout(connect, 200);
}

const startOverlay = document.getElementById('start-overlay');
if (startOverlay) {
    startOverlay.addEventListener('click', startSession, { once: true });
} else {
    // Overlay missing for some reason — fall back to old behavior.
    connect();
}
