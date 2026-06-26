import urllib.request, json

# Step 1: Register (one-step)
url = "https://xiaping.coze.com/api/auth/register"
data = json.dumps({"name": "etf-platform"}).encode("utf-8")
req = urllib.request.Request(url, data=data, headers={
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0",
})
try:
    with urllib.request.urlopen(req, timeout=15) as r:
        resp = json.loads(r.read().decode("utf-8"))
    print("Register response:")
    print(json.dumps(resp, ensure_ascii=False, indent=2))
except Exception as e:
    print(f"Register error: {e}")
    # Try reading error body
    if hasattr(e, "read"):
        print(e.read().decode("utf-8", errors="replace")[:500])