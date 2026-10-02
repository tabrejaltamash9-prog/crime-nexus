import requests
import json

url = "http://localhost:8000/evidence/upload"
files = {'file': ('blob', b'hello world', 'application/octet-stream')}
data = {
    'case_id': 'case-123',
    'original_filename': 'undefined',
    'original_mime_type': 'undefined',
    'original_sha256': 'a591a6d40bf420404a011733cfb7b190d62c65bf0bcda32b57b277d9ad9f146e',
    'encryption_algorithm': 'NONE',
    'iv': '',
    'wrapped_deks': '[]',
    'uploader': 'system'
}

response = requests.post(url, files=files, data=data)
print(f"Status Code: {response.status_code}")
print(f"Response: {response.text}")
