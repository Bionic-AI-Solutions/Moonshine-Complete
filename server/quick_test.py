#!/usr/bin/env python3
"""Quick transcription test for harvard.wav"""

import time
import subprocess
import sys

# Use curl to send the file
cmd = [
    'curl', '-s', '-X', 'POST',
    'http://127.0.0.1:8001/v1/transcribe',
    '-F', 'file=@E:\\Bionic AI\\moonshine\\harvard.wav'
]

print("[*] Starting transcription of harvard.wav...")
print(f"[*] Command: {' '.join(cmd)}", flush=True)

t0 = time.time()
try:
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    elapsed = time.time() - t0
    
    print(f"\n[+] Finished in {elapsed:.1f} seconds\n")
    
    if result.returncode == 0:
        print("[✓] Response:")
        print(result.stdout)
    else:
        print(f"[!] Error (code {result.returncode}):")
        print(result.stderr)
except subprocess.TimeoutExpired:
    print("[!] Transcription timed out after 600 seconds")
except Exception as e:
    print(f"[!] Exception: {e}")
