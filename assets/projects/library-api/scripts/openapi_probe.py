import json

import httpx

response = httpx.get("http://127.0.0.1:8000/openapi.json")
document = response.json()
print(response.status_code)
print(json.dumps(document["info"], ensure_ascii=False, indent=2))
print(sorted(document["paths"]))
