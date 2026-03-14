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
