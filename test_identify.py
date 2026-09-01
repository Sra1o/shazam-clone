import urllib.request
import urllib.parse
import urllib.error
import os
import json
import uuid
import wave
import struct

# Create a short dummy WAV file
test_file = 'test.wav'
with wave.open(test_file, 'w') as w:
    w.setnchannels(1)
    w.setsampwidth(2)
    w.setframerate(22050)
    for i in range(22050): # 1 second of silence
        w.writeframes(struct.pack('h', 0))

# Send to API
boundary = uuid.uuid4().hex
with open(test_file, 'rb') as f:
    audio_data = f.read()

body = (
    f"--{boundary}\r\n"
    f"Content-Disposition: form-data; name=\"file\"; filename=\"test.wav\"\r\n"
    f"Content-Type: audio/wav\r\n\r\n"
).encode('utf-8') + audio_data + f"\r\n--{boundary}--\r\n".encode('utf-8')

req = urllib.request.Request("http://localhost:8000/identify", data=body)
req.add_header('Content-Type', f'multipart/form-data; boundary={boundary}')
try:
    with urllib.request.urlopen(req, timeout=10) as response:
        print("Success:", response.read().decode())
except urllib.error.HTTPError as e:
    print("HTTP Error:", e.code, e.read().decode())
except Exception as e:
    print("Error:", e)
