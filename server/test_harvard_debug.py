#!/usr/bin/env python3
"""
Test ASR server with harvard_audio.wav - capture full error response.
"""

import json
import http.client
import sys

# Read audio file
with open('harvard_audio.wav', 'rb') as f:
    wav_data = f.read()

print(f"[*] File size: {len(wav_data)} bytes")
print(f"[*] Sending to server...")

# Build multipart with explicit boundary
boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"
body = (
    f"--{boundary}\r\n"
    f"Content-Disposition: form-data; name=\"file\"; filename=\"harvard_audio.wav\"\r\n"
    f"Content-Type: audio/wav\r\n"
    f"\r\n"
).encode() + wav_data + f"\r\n--{boundary}--\r\n".encode()

conn = http.client.HTTPConnection("127.0.0.1", 8001)
headers = {"Content-Type": f"multipart/form-data; boundary={boundary}"}
conn.request("POST", "/v1/transcribe", body, headers)

resp = conn.getresponse()
response_text = resp.read().decode('utf-8', errors='ignore')

print(f"\n[+] {resp.status} ({resp.reason})")
print(f"\n{response_text}\n")

# Try to parse as JSON
try:
    data = json.loads(response_text)
    print(json.dumps(data, indent=2))
except json.JSONDecodeError as e:
    print(f"[!] Could not parse JSON: {e}")
    print(f"[!] Raw response:\n{response_text}")

conn.close()
