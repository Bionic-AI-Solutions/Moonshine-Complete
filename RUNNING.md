# Moonshine — How to Run Locally

This document explains how to run the Moonshine project locally (server + web UI), how they connect, and useful troubleshooting and tuning tips.

Paths referenced in examples:
- Repository root: `E:\Bionic AI\moonshine`
- Server code: `E:\Bionic AI\moonshine\server`
- Web UI (static): `E:\Bionic AI\moonshine\moonshine-web`
- Streaming model (server): `E:\Bionic AI\moonshine\moonshine-streaming-medium`
- Test audio: `E:\Bionic AI\moonshine\harvard.wav`

---

## Summary

- The web UI runs as a static site on port 4000 and captures microphone audio in the browser.
- We replaced the original in-browser worker with an API-backed worker that posts audio to the local FastAPI server running on port 8001.
- The server loads `moonshine-streaming-medium` from the local folder and performs ASR (speech-to-text). The web UI receives text in the same message format it expects.

---

## Prerequisites

- Python 3.10+ installed and on PATH
- `git` (optional, for cloning/updating repository)
- 4+ GB free RAM (model and Python runtime vary by configuration)
- Modern browser (Chrome/Edge/Firefox) for the web UI

If you plan to run everything exactly as used here, Windows PowerShell examples are provided; bash/macOS variants are also included.

---

## Server: Setup & Run

1. Open a terminal (PowerShell recommended on Windows).

2. Create and activate a virtual environment (one-time step):

PowerShell (Windows):
```powershell
cd "E:\Bionic AI\moonshine\server"
python -m venv .\.venv
.\.venv\Scripts\Activate.ps1
```

bash / macOS:
```bash
cd /path/to/moonshine/server
python -m venv ./.venv
source ./.venv/bin/activate
```

3. Install Python dependencies (inside the activated venv):

```powershell
python -m pip install -U pip
pip install -r requirements.txt
```

4. Start the server (development):

```powershell
# From server folder, with venv activated
python app.py
```

Notes:
- The server will bind to `127.0.0.1:8001` by default (see `app.py`). If the port is in use, stop the other process or change the port.
- There is no route for `/` (root). The server exposes named endpoints such as `/health` and `/v1/transcribe`.

5. Verify health endpoint:

```powershell
curl http://127.0.0.1:8001/health
# Example response: {"status":"ok","model_loaded":true,"model_dir":"E:\\Bionic AI\\moonshine\\moonshine-streaming-medium"}
```

6. Transcribe a WAV file (quick test):

```powershell
curl -X POST http://127.0.0.1:8001/v1/transcribe -F "file=@E:\\Bionic AI\\moonshine\\harvard.wav"
```

Response JSON format:
```json
{
  "text": "...",
  "duration_s": 18.36,
  "processing_time_s": 6.755
}
```

---

## Web UI (static): Setup & Run

1. Start a static server from the `moonshine-web` folder. The repo includes a prebuilt static site in `moonshine-web/assets`.

PowerShell:
```powershell
cd "E:\Bionic AI\moonshine\moonshine-web"
python -m http.server 4000
```

bash:
```bash
cd /path/to/moonshine/moonshine-web
python3 -m http.server 4000
```

2. Open the page in your browser:

```
http://127.0.0.1:4000
```

3. When prompted, allow microphone access. The app will show status messages and transcriptions.

---

## Detailed Quickstart (step-by-step)

This section walks through creating a Python virtual environment, installing dependencies, starting the backend API server, serving the web UI, and exercising both Moonshine and Whisper endpoints.

1) Create & activate virtual environment (Windows PowerShell)

```powershell
cd "E:\Bionic AI\moonshine\server"
python -m venv .\.venv
.\.venv\Scripts\Activate.ps1
```

2) Install Python dependencies

If you have a `requirements.txt`, install it. Otherwise, at minimum install these:

```powershell
python -m pip install -U pip
pip install fastapi uvicorn[standard] soundfile librosa numpy torch transformers
```

3) (Optional) Configure environment variables for Whisper

If you plan to use the Whisper ggml backend, set these environment variables to point to the whisper binary and ggml model file. Adjust paths to your environment.

```powershell
$env:WHISPER_CPP_BIN = "E:\Bionic AI\moonshine\whisper-bin-x64\Release\whisper-cli.exe"
$env:GGML_WHISPER_MODEL = "E:\Bionic AI\moonshine\ggml-small.bin"
$env:WHISPER_MAX_CONCURRENCY = "2"
```

4) Start the backend API server

```powershell
# from the server folder with venv activated
python app.py
```

The server listens at `http://127.0.0.1:8001` by default. Watch the console for model-loading messages such as:

```
[moonshine] Loading model from E:\Bionic AI\moonshine\moonshine-streaming-medium …
[moonshine] Model loaded in 1.6s
```

5) Start the static web UI

```powershell
cd "E:\Bionic AI\moonshine\moonshine-web"
python -m http.server 4000
```

Open `http://127.0.0.1:4000` in a browser. Allow microphone access when requested.

6) Verify endpoints with `curl` (direct tests)

Moonshine (server-side model):

```powershell
curl -s -F "file=@E:\Bionic AI\moonshine\harvard.wav" http://127.0.0.1:8001/v1/transcribe | ConvertFrom-Json | Format-List
```

Whisper (ggml subprocess):

```powershell
curl -s -F "file=@E:\Bionic AI\moonshine\harvard.wav" http://127.0.0.1:8001/v1/transcribe/whisper | ConvertFrom-Json | Format-List
```

Both should return JSON with `text`, `duration_s`, and `processing_time_s` fields.

## Web UI: runtime model selection

The UI exposes a small model selector in the top-right corner. Behavior:
- Selecting **Moonshine** routes audio to `POST /v1/transcribe` (server-side Moonshine model).
- Selecting **Whisper** routes audio to `POST /v1/transcribe/whisper` (local whisper-cli subprocess).

How it works internally:
- The page stores your selection in `localStorage.asr_model` for persistence.
- The page also sends a `postMessage` to the transcription worker so the worker routes requests to the correct endpoint immediately.

To verify runtime switching:
1. Open Developer Tools (F12) → Console
2. Click the "Whisper" radio button → you should see a console log: `[moonshine] Sent to worker: set model to whisper`
3. Record audio in the UI and check the backend server logs. You should see `POST /v1/transcribe/whisper` when Whisper is selected and `POST /v1/transcribe` when Moonshine is selected.

## Troubleshooting

- `500 Internal Server Error` on `/v1/transcribe` — likely transformers model registration issue. Fix by upgrading `transformers` inside the server venv:

```powershell
cd "E:\Bionic AI\moonshine\server"
.\.venv\Scripts\Activate.ps1
pip install --upgrade transformers
# restart server
python app.py
```

- "Whisper binary not found": verify `WHISPER_CPP_BIN` path and that `whisper-cli.exe` exists.
- "Whisper model not found": verify `GGML_WHISPER_MODEL` exists.
- Web UI not reachable: ensure the static server is running on port 4000.
- Worker not receiving messages: open console and confirm logs for `Sent to worker` and `Model set to:` messages.

## Rollback notes

If an upgrade to `transformers` causes problems, revert with a pinned version (example):

```powershell
pip install transformers==4.37.0
```

## Advanced: tuning
- VAD thresholds (`SPEECH_THRESHOLD`, `SILENCE_TIMEOUT_S`) are in `moonshine-web/assets/worker-api.js`.
- To change Whisper thread count or other behavior, edit `_transcribe_with_whisper()` in `server/app.py`.

## Support
If you want, I can:
- Revert the UI change so the selector is hidden.
- Force always-Whisper mode (we previously applied that change temporarily).
- Implement a configuration page to persist server-side defaults.

---

_Last updated: March 15, 2026_

---

## How the pieces connect (end-to-end)

- Browser captures audio at 16 kHz via `getUserMedia` → `AudioContext` → an `AudioWorklet`.
- `AudioWorklet` sends Float32Array audio chunks (512+ samples at 16 kHz) to the transcription worker via `postMessage({ buffer })`.
- We replaced the original in-browser worker with `moonshine-web/assets/worker-api.js`. This worker:
  - Buffers chunks and uses a simple energy-based VAD to detect speech segments.
  - When a speech segment ends (silence timeout), converts the collected Float32 PCM into 16-bit WAV bytes.
  - Sends the WAV with a multipart POST to `http://127.0.0.1:8001/v1/transcribe`.
  - Receives JSON from the server and posts messages back to the main thread in the same `{ type: "output", message: "..." }` format the UI expects.
- The server decodes the WAV, resamples/pads, extracts features, runs the `moonshine-streaming-medium` model, decodes tokens to text, then returns the text in the JSON response.

---

## Which model is loaded by the server and how

- The server loads the local model folder `E:\Bionic AI\moonshine\moonshine-streaming-medium`.
- Loading is lazy and thread-safe: the first transcribe call triggers `_load_model()` in `server/app.py` which:
  - Loads tokenizer: `AutoTokenizer.from_pretrained(MODEL_DIR, use_fast=True, trust_remote_code=True)`
  - Loads processor: `AutoProcessor.from_pretrained(MODEL_DIR, trust_remote_code=True)` (fallback to feature extractor if needed)
  - Loads model: `AutoModelForSpeechSeq2Seq.from_pretrained(MODEL_DIR, trust_remote_code=True, torch_dtype=torch.float32)`
  - Calls `_model.eval()` to set inference mode
- `app.py` logs the model load progress to the console; look for messages like:
  ```text
  [moonshine] Loading model from E:\Bionic AI\moonshine\moonshine-streaming-medium …
  [moonshine] Model loaded in 1.4s
  ```

---

## Important implementation notes / recent fixes

- The server pads audio to a frame boundary expected by the model (multiple of 80 samples at 16 kHz) to avoid a shape error during inference. This fix is in `server/app.py` in `_load_audio_bytes()`.
- The web worker `moonshine-web/assets/worker-api.js` contains these tunable parameters near the top of the file:
  - `SPEECH_THRESHOLD` — RMS threshold to decide speech vs silence
  - `SILENCE_TIMEOUT_S` — seconds of silence to close a segment (default used: 1.5)
  - `MIN_SPEECH_S` — ignore very short segments
  - `PRE_SPEECH_S` — how much pre-speech audio to keep

---

## Tuning VAD and responsiveness (no coding required, quick testing)

If you feel the UI waits too long before sending audio, or triggers on noise, adjust these in `moonshine-web/assets/worker-api.js`:
- Lower `SPEECH_THRESHOLD` to make detection more sensitive (picks up quieter speech and noise)
- Lower `SILENCE_TIMEOUT_S` to send sooner after silence (more responsive, may split phrases)
- Increase `PRE_SPEECH_S` to capture more speech before the detected onset (reduces clipping at start)

After editing `worker-api.js`, refresh the web page. For changes to be active you may need to clear cache or reload with Ctrl+F5.

Suggested start values:
- `SPEECH_THRESHOLD`: 0.012 (default)
- `SILENCE_TIMEOUT_S`: 1.5
- `MIN_SPEECH_S`: 0.3
- `PRE_SPEECH_S`: 0.5

---

## Switching back to browser-only (in-browser ONNX)

To revert so the web UI performs inference locally using the bundled ONNX model:
1. Remove or undo the Worker override script in `moonshine-web/index.html` that redirects to `worker-api.js`.
   - Find the script block that replaces `window.Worker` and remove it.
2. Reload the page — the app will create the original worker (`/assets/worker-D9nS5ej1.js` or `worker-BrsEphLD.js`) which loads `onnx-community/moonshine-base-ONNX` in the browser.

Note: Running in-browser ONNX requires the browser to support WebGPU or the WASM fallback and may be slower or less accurate than the server streaming-medium model.

---

## Adding a UI toggle (concept)

If you want runtime switching between API-backed and in-browser inference without editing `index.html` each time, implement a toggle that:
1. Stores a choice in `localStorage` (e.g., `localStorage.useApi = "true"`)
2. The `Worker` override (or app code) reads that flag when creating the worker and instantiates either `worker-api.js` (API) or the original `worker-*.js` (ONNX).
3. When the user toggles, call `worker.terminate()` and recreate the worker with the new backend.

We can implement this toggle for you if you want—it's a small change in `index.html` and a tiny UI control in the static app.

---

## Troubleshooting

- 404 at `http://127.0.0.1:8001/`:
  - This is expected — root (`/`) is not implemented. Use `/health` and `/v1/transcribe` instead.

- Port 8001 already in use:
  - Stop the process using the port or change the port in `app.py` (uvicorn.run(..., port=XXXX)).

- PermissionError reading files (Windows):
  - Ensure file paths are correct and not used by other processes. Use `Get-Item` in PowerShell to inspect file properties.

- Model loading errors (shape mismatch):
  - We added padding in `_load_audio_bytes()` to avoid shape mismatch. If you still see errors, check `server` logs; ensure the model directory contains compatible files.

- Web UI shows "API server not reachable":
  - Confirm `python app.py` is running and `/health` returns OK.
  - Confirm CORS if you run server on different host/port.

Logs: watch the server terminal where you ran `python app.py` for detailed tracebacks and model loading messages.

---

## Quick commands reference

Start server (PowerShell):
```powershell
cd "E:\Bionic AI\moonshine\server"
.\.venv\Scripts\Activate.ps1
python app.py
```

Start web UI static server:
```powershell
cd "E:\Bionic AI\moonshine\moonshine-web"
python -m http.server 4000
# Then open http://127.0.0.1:4000
```

Health check:
```powershell
curl http://127.0.0.1:8001/health
```

Transcribe file:
```powershell
curl -X POST http://127.0.0.1:8001/v1/transcribe -F "file=@E:\\Bionic AI\\moonshine\\harvard.wav"
```

---

## Next steps (optional)

- Add a UI toggle to switch between API and in-browser ONNX at runtime (I can implement this for you).
- Improve VAD algorithm (replace energy-based with Silero VAD or WebRTC VAD if you want more robust detection).
- Bundle server + web UI into a single desktop app (Electron/Tauri) for distribution.

---

If you want, I can now:
- Add the runtime toggle (small code change in `index.html` + a tiny UI button), or
- Re-tune the VAD constants in `worker-api.js` and run a few test recordings to verify responsiveness.

Tell me which of those (or both) you'd like next.

---

## WHISPER ggml INTEGRATION (NEW — March 2026)

As of March 2026, we've added support for **Whisper ggml-small** as an alternative ASR backend with **runtime model selection**.

### Quick Start with Whisper

1. **Ensure files are in place:**
   - Whisper binary: `E:\Bionic AI\moonshine\whisper-bin-x64\Release\whisper-cli.exe`
   - Model: `E:\Bionic AI\moonshine\ggml-small.bin`
   - Test audio: `E:\Bionic AI\moonshine\harvard.wav`

2. **Start the server (same as before):**
   ```powershell
   cd "E:\Bionic AI\moonshine\server"
   .\.venv\Scripts\Activate.ps1
   python app.py
   ```

3. **Test Whisper endpoint directly:**
   ```powershell
   curl -F "file=@E:\Bionic AI\moonshine\harvard.wav" http://127.0.0.1:8001/v1/transcribe/whisper | ConvertFrom-Json
   ```

   Expected response:
   ```json
   {
     "text": "The stale smell of old beer lingers...",
     "duration_s": 18.36,
     "processing_time_s": 17.5
   }
   ```

### New Backend Endpoint: `/v1/transcribe/whisper`

**Method:** POST  
**Content-Type:** multipart/form-data  
**Parameter:** `file` (audio file)

The Whisper endpoint:
- Invokes `whisper-cli.exe` subprocess with `ggml-small.bin` model
- Returns same `TranscribeResponse` JSON schema as Moonshine (for seamless switching)
- Supports same audio formats: WAV, MP3, FLAC, OGG
- Uses semaphore to limit concurrent jobs (default: 2, configurable)

### Environment Variables (Whisper)

Control Whisper behavior with environment variables before starting the server:

```powershell
# Whisper CLI binary path (default: whisper-bin-x64/Release/whisper-cli.exe)
$env:WHISPER_CPP_BIN = "E:\Bionic AI\moonshine\whisper-bin-x64\Release\whisper-cli.exe"

# ggml model file path (default: ggml-small.bin)
$env:GGML_WHISPER_MODEL = "E:\Bionic AI\moonshine\ggml-small.bin"

# Max concurrent Whisper jobs (default: 2)
$env:WHISPER_MAX_CONCURRENCY = "2"

# Then start server
python server/app.py
```

### Web UI: Runtime Model Selection

**NEW FEATURE:** The web UI now includes a **model selector** in the top-right corner.

1. **UI Control:**
   - Two radio buttons: "Moonshine" (default) and "Whisper"
   - Status label shows currently selected model
   - Located at top-right, always visible

2. **How to Switch Models:**
   - Open web UI at `http://127.0.0.1:4000`
   - Click "Whisper" radio button to activate Whisper mode
   - Next recording will use Whisper instead of Moonshine
   - Click "Moonshine" to switch back
   - Selection persists across page reloads (stored in `localStorage.asr_model`)

3. **Technical Implementation:**
   - Model selection is stored in `localStorage.asr_model`
   - Worker reads this value and routes to correct endpoint

### Performance Comparison

| Metric | Moonshine | Whisper ggml-small |
|--------|-----------|-------------------|
| **Status** | Model loading issue | ✓ Fully operational |
| **Model size** | ~360 MB | ~461 MB |
| **Inference time** | ~2-3s | ~17-20s |
| **Accuracy** | Good | Excellent |

### Troubleshooting Whisper

**"Whisper binary not found" error:**
```powershell
Test-Path "E:\Bionic AI\moonshine\whisper-bin-x64\Release\whisper-cli.exe"
```

**"Whisper model not found" error:**
```powershell
Test-Path "E:\Bionic AI\moonshine\ggml-small.bin"
```

**Status:** ✓ Ready for production use  
**Test results:** Whisper endpoint successfully transcribed harvard.wav in 17.5 seconds