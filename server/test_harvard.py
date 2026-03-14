import http.client
import json
import time

# Read the WAV file
with open('harvard_audio.wav', 'rb') as f:
    wav_data = f.read()

print(f"[*] File size: {len(wav_data)} bytes")
print(f"[*] Sending to server...")
t0 = time.time()

# Build multipart form data
boundary = '----PythonBoundary'
body = []
body.append(f'--{boundary}\r\n'.encode())
body.append(b'Content-Disposition: form-data; name="file"; filename="harvard.wav"\r\n')
body.append(b'Content-Type: audio/wav\r\n\r\n')
body.append(wav_data)
body.append(f'\r\n--{boundary}--\r\n'.encode())

form_data = b''.join(body)

# Send request
try:
    conn = http.client.HTTPConnection('127.0.0.1', 8001, timeout=600)
    conn.request('POST', '/v1/transcribe',
        form_data,
        {'Content-Type': f'multipart/form-data; boundary={boundary}'}
    )

    response = conn.getresponse()
    response_data = response.read().decode('utf-8')
    elapsed = time.time() - t0

    print(f"\n[+] {response.status} (received in {elapsed:.1f}s)\n")
    
    # Pretty-print JSON if possible
    try:
        result = json.loads(response_data)
        print(json.dumps(result, indent=2))
    except:
        print(response_data)

    conn.close()
except Exception as e:
    print(f"[!] Error: {e}")
