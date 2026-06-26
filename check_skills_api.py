import urllib.request, json

# Fetch the API spec
url = "https://xiaping.coze.com/skill.md"
try:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as r:
        text = r.read().decode("utf-8", errors="replace")
    print(f"=== skill.md ({len(text)}b) ===")
    print(text[:2000])
except Exception as e:
    print(f"Error: {e}")

print()

# Also try the download endpoint to see the API structure
for skill_id in ["87941273-65cf-46d4-a3df-c18e9c2db1dc", "8ccc5b0c-3a5f-4a3b-9158-8c822927b7dd"]:
    url = f"https://xiaping.coze.com/api/skills/{skill_id}/download"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read().decode("utf-8"))
        print(f"\n=== Skill {skill_id[:8]}... download ===")
        print(json.dumps(data, ensure_ascii=False, indent=2)[:1000])
    except Exception as e:
        print(f"\n=== Skill {skill_id[:8]}... download: {e} ===")