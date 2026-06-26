import urllib.request, json, re

for name, url in [
    ("Skill 1", "https://xiaping.coze.com/skill/87941273-65cf-46d4-a3df-c18e9c2db1dc"),
    ("Skill 2", "https://xiaping.coze.com/skill/8ccc5b0c-3a5f-4a3b-9158-8c822927b7dd"),
]:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            t = r.read().decode("utf-8", errors="replace")
        print(f"{name}: {r.status}, {len(t)}b")
        m = re.search(r"<title>(.*?)</title>", t)
        if m: print(f"  Title: {m.group(1)}")
        m = re.search(r'<meta[^>]*description[^>]*content="([^"]+)"', t)
        if m: print(f"  Desc: {m.group(1)[:300]}")
        # Check for JSON-LD
        m = re.search(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', t, re.DOTALL)
        if m: print(f"  JSON-LD: {m.group(1)[:200]}")
        # Get visible text
        body = re.search(r"<body[^>]*>(.*?)</body>", t, re.DOTALL)
        if body:
            clean = re.sub(r"<[^>]+>", " ", body.group(1))
            clean = re.sub(r"\s+", " ", clean).strip()[:500]
            print(f"  Body: {clean}")
        print()
    except Exception as e:
        print(f"{name}: {type(e).__name__}: {str(e)[:80]}\n")