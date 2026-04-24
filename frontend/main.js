// Jarvis V2 — Frontend
const orb = document.getElementById('orb');
const status = document.getElementById('status');
const transcript = document.getElementById('transcript');
const pauseBtn = document.getElementById('pauseBtn');

let ws;
let audioQueue = [];
let isPlaying = false;
let audioUnlocked = false;
let isPaused = false;

// Unlock audio on ANY user interaction
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

function connect() {
    ws = new WebSocket(`ws://${location.host}/ws`);
    ws.onopen = () => {
        console.log('[jarvis] WebSocket connected');
        status.textContent = 'Kattints egyszer, majd szólj Jarvishoz.';
        setOrbState('thinking');
        ws.send(JSON.stringify({ text: 'Jarvis aktiválás' }));
    };
    ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        if (data.type === 'response') {
            addTranscript('jarvis', data.text);
            if (data.audio && data.audio.length > 0) {
                queueAudio(data.audio);
            } else {
                setOrbState('idle');
                setTimeout(startListening, 500);
            }
        } else if (data.type === 'status') {
            status.textContent = data.text;
        }
    };
    ws.onclose = () => {
        status.textContent = 'Kapcsolat megszakadt...';
        setTimeout(connect, 3000);
    };
}

function queueAudio(base64Audio) {
    audioQueue.push(base64Audio);
    if (!isPlaying) playNext();
}

function playNext() {
    if (audioQueue.length === 0) {
        isPlaying = false;
        if (isPaused) {
            setOrbState('paused');
            status.textContent = 'Szüneteltetve';
            return;
        }
        setOrbState('listening');
        status.textContent = '';
        setTimeout(startListening, 500);
        return;
    }
    isPlaying = true;
    setOrbState('speaking');
    status.textContent = '';
    if (isListening) {
        recognition.stop();
        isListening = false;
    }

    const b64 = audioQueue.shift();
    const bytes = Uint8Array.from(atob(b64), c => c.charCodeAt(0));
    const blob = new Blob([bytes], { type: 'audio/mpeg' });
    const url = URL.createObjectURL(blob);
    const audio = new Audio(url);
    audio.onended = () => { URL.revokeObjectURL(url); playNext(); };
    audio.onerror = () => { URL.revokeObjectURL(url); playNext(); };
    audio.play().catch(err => {
        console.warn('[jarvis] Autoplay blocked, waiting for click...');
        status.textContent = 'Kattints valahova hogy Jarvis tudjon beszélni.';
        setOrbState('idle');
        // Wait for click then retry
        document.addEventListener('click', function retry() {
            document.removeEventListener('click', retry);
            audio.play().then(() => {
                setOrbState('speaking');
                status.textContent = '';
            }).catch(() => playNext());
        });
    });
}

// Speech Recognition
const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
let recognition;
let isListening = false;

if (SpeechRecognition) {
    recognition = new SpeechRecognition();
    recognition.lang = 'hu-HU';
    recognition.continuous = true;
    recognition.interimResults = false;

    recognition.onresult = (event) => {
        const last = event.results[event.results.length - 1];
        if (last.isFinal) {
            const text = last[0].transcript.trim();
            if (text) {
                addTranscript('user', text);
                setOrbState('thinking');
                status.textContent = 'Jarvis gondolkodik...';
                ws.send(JSON.stringify({ text }));
            }
        }
    };

    recognition.onend = () => {
        isListening = false;
        if (!isPlaying && !isPaused) setTimeout(startListening, 300);
    };

    recognition.onerror = (event) => {
        isListening = false;
        if (isPaused) return;
        if (event.error === 'no-speech' || event.error === 'aborted') {
            if (!isPlaying) setTimeout(startListening, 300);
        } else {
            setTimeout(startListening, 1000);
        }
    };
}

function startListening() {
    if (isPlaying || isPaused) return;
    try {
        recognition.start();
        isListening = true;
        setOrbState('listening');
        status.textContent = '';
    } catch(e) {}
}

function togglePause() {
    isPaused = !isPaused;

    if (isPaused) {
        // Stop everything
        if (isListening) {
            recognition.stop();
            isListening = false;
        }
        audioQueue = [];
        isPlaying = false;
        setOrbState('paused');
        pauseBtn.textContent = '▶';
        pauseBtn.classList.add('paused');
        pauseBtn.title = 'Folytatás';
        status.textContent = 'Szüneteltetve';
    } else {
        // Resume listening (no greeting, just start)
        pauseBtn.textContent = '⏸';
        pauseBtn.classList.remove('paused');
        pauseBtn.title = 'Szünet';
        status.textContent = '';
        startListening();
    }
}

pauseBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    togglePause();
});

orb.addEventListener('click', () => {
    if (isPaused) {
        togglePause();
        return;
    }
    if (isPlaying) return;
    if (isListening) {
        recognition.stop();
        isListening = false;
        setOrbState('idle');
    } else {
        startListening();
    }
});

function setOrbState(state) { orb.className = state; }

function addTranscript(role, text) {
    const div = document.createElement('div');
    div.className = role;
    div.textContent = role === 'user' ? `Te: ${text}` : `Jarvis: ${text}`;
    transcript.appendChild(div);
    transcript.scrollTop = transcript.scrollHeight;
}

connect();
