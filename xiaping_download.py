import urllib.request, json, os, zipfile, io

API_KEY = "sk_OJw...chC-"  # masked in display

skills = [
    ("stock_analysis", "87941273-65cf-46d4-a3df-c18e9c2db1dc"),
    ("news_aggregator", "8ccc5b0c-3a5f-4a3b-9158-8c822927b7dd"),
]

for name, skill_id in skills:
    print(f"\n=== Downloading {name} ({skill_id[:8]}...) ===")
    url = f"https://xiaping.coze.com/api/skills/{skill_id}/download"
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {API_KEY}",
        "User-Agent": "Mozilla/5.0",
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = r.read()
        print(f"  Size: {len(data)} bytes")
        print(f"  Content-Type: {r.headers.get('Content-Type', '?')}")
        
        # Check if it's a ZIP
        if data[:2] == b"PK":
            print("  Format: ZIP archive")
            z = zipfile.ZipFile(io.BytesIO(data))
            files = z.namelist()
            print(f"  Files ({len(files)}):")
            for fname in files:
                info = z.getinfo(fname)
                print(f"    {fname} ({info.file_size}b)")
            
            # Extract and study key files
            out_dir = os.path.join(r"D:\龙虾\.openclaw\etf-platform", "xiaping_skills", name)
            z.extractall(out_dir)
            print(f"  Extracted to: {out_dir}")
            
            # Read key files
            for fname in files:
                if fname.endswith((".py", ".md", ".json", ".yaml", ".txt")):
                    content = z.read(fname).decode("utf-8", errors="replace")
                    print(f"\n  --- {fname} ({len(content)}b) ---")
                    print(content[:1500])
        else:
            print(f"  Format: raw text/JSON")
            text = data.decode("utf-8", errors="replace")
            print(f"  Content ({len(text)}b):")
            print(text[:1500])
    except Exception as e:
        print(f"  Error: {type(e).__name__}: {str(e)[:100]}")
        if hasattr(e, "read"):
            print(f"  Body: {e.read().decode('utf-8', errors='replace')[:300]}")