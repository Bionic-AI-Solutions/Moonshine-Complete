/**
 * worker-api.js — API-backed transcription worker for Moonshine Web
 *
 * Drop-in replacement for the Transformers.js + ONNX worker.
 * Instead of running inference locally, sends audio to the FastAPI
 * server at localhost:8001 and returns transcription results.
 *
 * Message interface (same as original):
 *   Main → Worker:  { buffer: Float32Array }   (audio chunks, 512 samples, 16kHz mono)
 *   Worker → Main:  { type: "status", status: string, message: string }
 *   Worker → Main:  { type: "output", buffer: Float32Array, message: string, start: number, end: number, duration: number }
 */

const API_BASE = "http://127.0.0.1:8001";
const SAMPLE_RATE = 16000;

// ── VAD parameters ──────────────────────────────────────────────────
const SPEECH_THRESHOLD = 0.012;   // RMS energy threshold for speech
const SILENCE_TIMEOUT_S = 1.5;    // seconds of silence to end a segment
const MIN_SPEECH_S = 0.3;         // ignore segments shorter than this
const PRE_SPEECH_S = 0.5;         // keep this much audio before speech onset

// ── State ───────────────────────────────────────────────────────────
let speechChunks = [];             // Float32Array chunks during speech
let preSpeechRing = [];            // circular buffer before speech onset
let isSpeaking = false;
let silenceChunks = 0;
let busy = false;                  // guard against overlapping API calls
let selectedModel = 'moonshine';   // holds the selected ASR model from main thread

// ── Helpers ─────────────────────────────────────────────────────────

function rms(buf) {
  let sum = 0;
  for (let i = 0; i < buf.length; i++) sum += buf[i] * buf[i];
  return Math.sqrt(sum / buf.length);
}

function concat(arrays) {
  const len = arrays.reduce((s, a) => s + a.length, 0);
  const out = new Float32Array(len);
  let off = 0;
  for (const a of arrays) { out.set(a, off); off += a.length; }
  return out;
}

/** Encode Float32 PCM → 16-bit WAV file bytes */
function toWav(samples, sr) {
  const numSamples = samples.length;
  const buf = new ArrayBuffer(44 + numSamples * 2);
  const v = new DataView(buf);
  const w = (o, s) => { for (let i = 0; i < s.length; i++) v.setUint8(o + i, s.charCodeAt(i)); };

  w(0, "RIFF");
  v.setUint32(4, 36 + numSamples * 2, true);
  w(8, "WAVE");
  w(12, "fmt ");
  v.setUint32(16, 16, true);       // chunk size
  v.setUint16(20, 1, true);        // PCM
  v.setUint16(22, 1, true);        // mono
  v.setUint32(24, sr, true);       // sample rate
  v.setUint32(28, sr * 2, true);   // byte rate
  v.setUint16(32, 2, true);        // block align
  v.setUint16(34, 16, true);       // bits per sample
  w(36, "data");
  v.setUint32(40, numSamples * 2, true);

  let off = 44;
  for (let i = 0; i < numSamples; i++) {
    const s = Math.max(-1, Math.min(1, samples[i]));
    v.setInt16(off, s < 0 ? s * 0x8000 : s * 0x7FFF, true);
    off += 2;
  }
  return new Uint8Array(buf);
}

// ── API calls ───────────────────────────────────────────────────────

async function transcribeAudio(pcm) {
  const wav = toWav(pcm, SAMPLE_RATE);
  const fd = new FormData();
  fd.append("file", new Blob([wav], { type: "audio/wav" }), "audio.wav");

  // Route based on selectedModel
  const endpoint = selectedModel === 'whisper'
    ? `${API_BASE}/v1/transcribe/whisper`
    : `${API_BASE}/v1/transcribe`;
  console.log('[worker-api] Routing transcription to:', endpoint, '(model:', selectedModel + ')');

  const res = await fetch(endpoint, {
    method: "POST",
    body: fd,
  });
  if (!res.ok) throw new Error(`Server ${res.status}: ${res.statusText}`);
  return res.json();
}

async function checkHealth() {
  try {
    const r = await fetch(`${API_BASE}/health`);
    return r.ok;
  } catch { return false; }
}

// ── Process a finished speech segment ───────────────────────────────

async function flushSegment() {
  if (speechChunks.length === 0) return;

  const all = concat([...preSpeechRing, ...speechChunks]);
  speechChunks = [];
  preSpeechRing = [];

  const durationS = all.length / SAMPLE_RATE;
  if (durationS < MIN_SPEECH_S) return;

  const end = Date.now();
  const start = end - durationS * 1000;

  self.postMessage({ type: "status", status: "recording_end", message: "Transcribing…" });
  busy = true;

  try {
    const { text } = await transcribeAudio(all);
    if (text && text.trim()) {
      self.postMessage({
        type: "output",
        buffer: all,
        message: text.trim(),
        start,
        end,
        duration: end - start,
      });
    }
  } catch (err) {
    console.error("[worker-api]", err);
    self.postMessage({
      type: "status",
      status: "error",
      message: "Server error: " + err.message,
    });
  } finally {
    busy = false;
  }
}

// ── Incoming audio chunk handler ────────────────────────────────────

self.onmessage = (e) => {
  const data = e.data;
  
  // Handle control messages from main thread
  if (data && data.type === 'set-asr-model') {
    selectedModel = data.model || 'moonshine';
    console.log('[worker-api] Model set to:', selectedModel);
    self.postMessage({
      type: 'status',
      status: 'model_changed',
      message: `Model: ${selectedModel}`
    });
    return;
  }
  
  // Handle audio buffer messages (existing behavior)
  const buffer = data && data.buffer;
  if (!buffer || busy) return;

  const energy = rms(buffer);
  const loud = energy > SPEECH_THRESHOLD;

  if (loud) {
    if (!isSpeaking) {
      isSpeaking = true;
      silenceChunks = 0;
      self.postMessage({ type: "status", status: "recording_start", message: "Listening…" });
    }
    speechChunks.push(new Float32Array(buffer));
    silenceChunks = 0;
  } else if (isSpeaking) {
    // still accumulate silence within a segment
    speechChunks.push(new Float32Array(buffer));
    silenceChunks++;
    const silenceS = (silenceChunks * buffer.length) / SAMPLE_RATE;
    if (silenceS >= SILENCE_TIMEOUT_S) {
      isSpeaking = false;
      silenceChunks = 0;
      flushSegment();
    }
  } else {
    // no speech — maintain pre-speech ring buffer
    preSpeechRing.push(new Float32Array(buffer));
    const maxChunks = Math.ceil((PRE_SPEECH_S * SAMPLE_RATE) / (buffer.length || 512));
    while (preSpeechRing.length > maxChunks) preSpeechRing.shift();
  }
};

// ── Initialization ──────────────────────────────────────────────────

(async () => {
  self.postMessage({ type: "status", status: "loading", message: "Connecting to Moonshine API server…" });

  const ok = await checkHealth();
  if (!ok) {
    self.postMessage({
      type: "status",
      status: "loading",
      message: "⚠ API server not reachable at " + API_BASE + " — start the server first.",
    });
    // Retry a few times
    for (let i = 0; i < 5; i++) {
      await new Promise(r => setTimeout(r, 3000));
      if (await checkHealth()) { break; }
    }
  }

  self.postMessage({ type: "status", status: "ready", message: "Ready!" });
})();
