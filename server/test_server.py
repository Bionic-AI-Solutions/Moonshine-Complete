"""
Quick smoke-test for the Moonshine ASR server.

Generates a short sine-wave WAV file and sends it to POST /v1/transcribe.
The model will likely return silence/noise transcription, but this validates
the full pipeline (upload → feature extraction → inference → response).

Usage:
    python test_server.py              # default: http://127.0.0.1:8000
    python test_server.py <base_url>   # custom server URL
"""

import io
import sys
import struct
import math
import urllib.request
import json


def make_wav_bytes(duration_s: float = 2.0, sr: int = 16000, freq: float = 440.0) -> bytes:
    """Generate a mono 16-bit PCM WAV with a sine wave."""
    n_samples = int(sr * duration_s)
    buf = io.BytesIO()
    # data
    samples = []
    for i in range(n_samples):
        val = int(32767 * 0.5 * math.sin(2 * math.pi * freq * i / sr))
        samples.append(struct.pack("<h", val))
    raw = b"".join(samples)
    # WAV header
    buf.write(b"RIFF")
    buf.write(struct.pack("<I", 36 + len(raw)))
    buf.write(b"WAVE")
    buf.write(b"fmt ")
    buf.write(struct.pack("<IHHIIHH", 16, 1, 1, sr, sr * 2, 2, 16))
    buf.write(b"data")
    buf.write(struct.pack("<I", len(raw)))
    buf.write(raw)
    return buf.getvalue()


def test_health(base: str) -> None:
    url = f"{base}/health"
    print(f"GET {url}")
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req) as resp:
        body = json.loads(resp.read())
        print(f"  → {resp.status}: {json.dumps(body, indent=2)}")


def test_transcribe(base: str) -> None:
    url = f"{base}/v1/transcribe"
    wav = make_wav_bytes(duration_s=2.0)

    boundary = "----PythonTestBoundary"
    body_parts = []
    body_parts.append(f"--{boundary}\r\n".encode())
    body_parts.append(
        b'Content-Disposition: form-data; name="file"; filename="test.wav"\r\n'
    )
    body_parts.append(b"Content-Type: audio/wav\r\n\r\n")
    body_parts.append(wav)
    body_parts.append(f"\r\n--{boundary}--\r\n".encode())
    body = b"".join(body_parts)

    print(f"\nPOST {url}  (2s sine wave)")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    with urllib.request.urlopen(req) as resp:
        result = json.loads(resp.read())
        print(f"  → {resp.status}: {json.dumps(result, indent=2)}")


if __name__ == "__main__":
    base = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
    test_health(base)
    test_transcribe(base)
    print("\nAll tests passed!")
