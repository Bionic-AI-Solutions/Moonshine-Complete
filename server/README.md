# Moonshine Streaming-Medium — Local ASR Server

A FastAPI server that loads the `moonshine-streaming-medium` speech-to-text model and exposes a simple transcription API.

## What it does

You send an audio file (WAV, MP3, FLAC, OGG) → server transcribes it → returns text.

## Quick start (Windows PowerShell)

```powershell
cd server
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app.py
```

Server starts at `http://127.0.0.1:8000`.

## API

### `POST /v1/transcribe`

Upload an audio file and receive the transcription.

```bash
curl -X POST http://127.0.0.1:8000/v1/transcribe \
  -F "file=@recording.wav"
```

Response:
```json
{
  "text": "hello world this is a test",
  "duration_s": 3.2,
  "processing_time_s": 1.45
}
```

### `GET /health`

```bash
curl http://127.0.0.1:8000/health
```

Response:
```json
{
  "status": "ok",
  "model_loaded": true,
  "model_dir": "..."
}
```

## Notes

- First request triggers model loading (~1 GB into RAM). Subsequent requests are fast.
- Audio is automatically resampled to 16 kHz mono (model requirement).
- The model runs on CPU by default. For GPU, ensure `torch` is installed with CUDA support.
- Server binds to `127.0.0.1` (localhost only) for security.
