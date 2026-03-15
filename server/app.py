"""
Moonshine Streaming-Medium — Local ASR (Speech-to-Text) Server

Accepts audio uploads and returns transcribed text.
Uses the moonshine-streaming-medium model via HuggingFace transformers.

Endpoints
---------
POST /v1/transcribe       multipart audio file  → {"text": "..."}
GET  /health              server & model status
"""

from __future__ import annotations

import io
import os
import time
import threading
import subprocess
import tempfile
import json
from pathlib import Path

import numpy as np
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
_HERE = Path(__file__).resolve().parent
MODEL_DIR = str(_HERE.parent / "moonshine-streaming-medium")
TARGET_SR = 16_000  # model expects 16 kHz mono

# Whisper ggml configuration
WHISPER_CPP_BIN = os.getenv(
    "WHISPER_CPP_BIN",
    str(_HERE.parent / "whisper-bin-x64" / "Release" / "whisper-cli.exe")
)
GGML_WHISPER_MODEL = os.getenv(
    "GGML_WHISPER_MODEL",
    str(_HERE.parent / "ggml-small.bin")
)
WHISPER_MAX_CONCURRENCY = int(os.getenv("WHISPER_MAX_CONCURRENCY", "2"))

# Semaphore to limit concurrent whisper subprocess invocations
_whisper_semaphore = threading.Semaphore(WHISPER_MAX_CONCURRENCY)

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(title="Moonshine ASR API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # tighten in production
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Lazy-loaded model state
# ---------------------------------------------------------------------------
_lock = threading.Lock()
_model_loaded = False
_processor = None
_model = None
_tokenizer = None


def _load_model() -> None:
    """Load processor + model once, thread-safe."""
    global _model_loaded, _processor, _model, _tokenizer
    if _model_loaded:
        return
    with _lock:
        if _model_loaded:
            return

        import torch
        from transformers import (
            AutoProcessor,
            AutoModelForSpeechSeq2Seq,
            AutoTokenizer,
        )

        print(f"[moonshine] Loading model from {MODEL_DIR} …")
        t0 = time.perf_counter()

        _tokenizer = AutoTokenizer.from_pretrained(
            MODEL_DIR, use_fast=True, trust_remote_code=True
        )
        try:
            _processor = AutoProcessor.from_pretrained(
                MODEL_DIR, trust_remote_code=True
            )
        except Exception:
            # Fallback: build processor from feature extractor + tokenizer
            from transformers import Wav2Vec2FeatureExtractor
            _processor = Wav2Vec2FeatureExtractor.from_pretrained(MODEL_DIR)

        _model = AutoModelForSpeechSeq2Seq.from_pretrained(
            MODEL_DIR,
            trust_remote_code=True,
            torch_dtype=torch.float32,
        )
        _model.eval()

        elapsed = time.perf_counter() - t0
        print(f"[moonshine] Model loaded in {elapsed:.1f}s")
        _model_loaded = True


# ---------------------------------------------------------------------------
# Audio helpers
# ---------------------------------------------------------------------------
def _load_audio_bytes(raw: bytes) -> np.ndarray:
    """Read uploaded audio bytes → float32 numpy array at TARGET_SR."""
    import soundfile as sf
    import librosa

    buf = io.BytesIO(raw)
    try:
        audio, sr = sf.read(buf, dtype="float32")
    except Exception:
        buf.seek(0)
        audio, sr = librosa.load(buf, sr=None, mono=True)

    # mono
    if audio.ndim > 1:
        audio = audio.mean(axis=1)

    # resample to 16 kHz if needed
    if sr != TARGET_SR:
        audio = librosa.resample(audio, orig_sr=sr, target_sr=TARGET_SR)

    audio = audio.astype(np.float32)
    
    # Pad to frame boundary (moonshine-streaming requires
    # audio length to be a multiple of 80 samples at 16 kHz)
    frame_len = 80
    remainder = len(audio) % frame_len
    if remainder != 0:
        pad_amount = frame_len - remainder
        audio = np.pad(audio, (0, pad_amount), mode='constant', constant_values=0)
    
    return audio


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------
class TranscribeResponse(BaseModel):
    text: str
    duration_s: float
    processing_time_s: float


class HealthResponse(BaseModel):
    status: str
    model_loaded: bool
    model_dir: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
def _transcribe_with_whisper(audio_bytes: bytes) -> tuple[str, float, float]:
    """
    Invoke whisper-cli.exe subprocess to transcribe audio.
    Returns: (text, duration_s, processing_time_s)
    """
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as audio_file:
        audio_file.write(audio_bytes)
        audio_path = audio_file.name

    with tempfile.TemporaryDirectory() as tmpdir:
        output_prefix = str(Path(tmpdir) / "whisper_output")
        
        try:
            # Load audio to get duration
            audio_data = _load_audio_bytes(audio_bytes)
            duration_s = len(audio_data) / TARGET_SR

            t0 = time.perf_counter()
            
            # Run whisper-cli.exe with subprocess
            cmd = [
                WHISPER_CPP_BIN,
                "-m", GGML_WHISPER_MODEL,
                "-f", audio_path,
                "-t", "4",  # use 4 threads
                "-otxt",    # output text format
                "-of", output_prefix,  # output file prefix
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120,
            )

            processing_time = time.perf_counter() - t0

            if result.returncode != 0:
                raise HTTPException(
                    status_code=500,
                    detail=f"Whisper transcription failed: {result.stderr}",
                )

            # Read transcribed text from output file
            output_txt_path = Path(output_prefix + ".txt")
            if not output_txt_path.exists():
                raise HTTPException(
                    status_code=500,
                    detail="Whisper did not produce output file",
                )

            text = output_txt_path.read_text(encoding="utf-8").strip()

            return text, round(duration_s, 3), round(processing_time, 3)

        finally:
            # Clean up audio temp file
            if os.path.exists(audio_path):
                os.unlink(audio_path)


@app.post("/v1/transcribe", response_model=TranscribeResponse)
async def transcribe(file: UploadFile = File(...)):
    """Upload a WAV/MP3/FLAC/OGG audio file and get back the transcription."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file uploaded.")

    _load_model()

    raw = await file.read()
    if len(raw) == 0:
        raise HTTPException(status_code=400, detail="Empty audio file.")

    try:
        audio = _load_audio_bytes(raw)
    except Exception as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Could not decode audio: {exc}",
        )

    duration_s = len(audio) / TARGET_SR
    t0 = time.perf_counter()

    import torch

    # Feature extraction
    if hasattr(_processor, "feature_extractor"):
        feats = _processor.feature_extractor(
            audio, sampling_rate=TARGET_SR, return_tensors="pt"
        )
    elif hasattr(_processor, "__call__"):
        feats = _processor(
            audio, sampling_rate=TARGET_SR, return_tensors="pt"
        )
    else:
        raise HTTPException(
            status_code=500,
            detail="Processor does not support audio feature extraction.",
        )

    with torch.no_grad():
        generated_ids = _model.generate(**feats, max_length=512)

    text = _tokenizer.batch_decode(generated_ids, skip_special_tokens=True)[0]
    processing_time = time.perf_counter() - t0

    return TranscribeResponse(
        text=text.strip(),
        duration_s=round(duration_s, 3),
        processing_time_s=round(processing_time, 3),
    )


@app.post("/v1/transcribe/whisper", response_model=TranscribeResponse)
async def transcribe_whisper(file: UploadFile = File(...)):
    """Upload a WAV/MP3/FLAC/OGG audio file and get back transcription using Whisper ggml."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file uploaded.")

    # Verify whisper binary and model exist
    if not os.path.exists(WHISPER_CPP_BIN):
        raise HTTPException(
            status_code=500,
            detail=f"Whisper binary not found: {WHISPER_CPP_BIN}",
        )
    if not os.path.exists(GGML_WHISPER_MODEL):
        raise HTTPException(
            status_code=500,
            detail=f"Whisper model not found: {GGML_WHISPER_MODEL}",
        )

    raw = await file.read()
    if len(raw) == 0:
        raise HTTPException(status_code=400, detail="Empty audio file.")

    try:
        # Convert to WAV if needed
        audio = _load_audio_bytes(raw)
        # Re-encode as WAV for whisper subprocess
        import soundfile as sf
        wav_bytes = io.BytesIO()
        sf.write(wav_bytes, audio, TARGET_SR, format='WAV')
        wav_bytes.seek(0)
        audio_bytes = wav_bytes.read()
    except Exception as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Could not decode audio: {exc}",
        )

    # Limit concurrent whisper invocations
    with _whisper_semaphore:
        try:
            text, duration_s, processing_time = _transcribe_with_whisper(audio_bytes)
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail=f"Transcription error: {exc}",
            )

    return TranscribeResponse(
        text=text,
        duration_s=duration_s,
        processing_time_s=processing_time,
    )


@app.get("/health", response_model=HealthResponse)
def health():
    return HealthResponse(
        status="ok",
        model_loaded=_model_loaded,
        model_dir=MODEL_DIR,
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8001)
