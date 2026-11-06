import requests
import re
import json

BASE_URL = "https://reelipse.com"
headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

def inspect_page(route):
    url = BASE_URL + route
    try:
        resp = requests.get(url, headers=headers, timeout=12)
        html = resp.text
        # Extract headings (h1, h2, h3)
        h1s = re.findall(r'<h1[^>]*>(.*?)</h1>', html, re.DOTALL)
        h2s = re.findall(r'<h2[^>]*>(.*?)</h2>', html, re.DOTALL)
        h3s = re.findall(r'<h3[^>]*>(.*?)</h3>', html, re.DOTALL)
        # Clean tags
        clean = lambda lst: [re.sub(r'<[^>]+>', '', x).strip() for x in lst if x.strip()]
        
        # Extract buttons & inputs
        buttons = re.findall(r'<button[^>]*>(.*?)</button>', html, re.DOTALL)
        inputs = re.findall(r'<input[^>]+>', html)
        selects = re.findall(r'<select[^>]*>(.*?)</select>', html, re.DOTALL)
        
        # Extract section tags or main containers
        sections = re.findall(r'<section[^>]*class="([^"]*)"', html)
        
        # Extract client scripts or astro islands
        astro_islands = re.findall(r'<astro-island[^>]+component-url="([^"]+)"', html)
        
        return {
            "route": route,
            "status": resp.status_code,
            "h1": clean(h1s),
            "h2": clean(h2s),
            "h3": clean(h3s)[:10],
            "buttons": clean(buttons)[:15],
            "input_count": len(inputs),
            "select_count": len(selects),
            "sections": sections[:10],
            "astro_islands": list(dict.fromkeys(astro_islands))
        }
    except Exception as e:
        return {"route": route, "error": str(e)}

routes = [
    "/",
    "/discover",
    "/tv",
    "/movies-like",
    "/movie-map",
    "/watch-order",
    "/mood-matcher",
    "/best",
    "/pick",
    "/blend",
    "/watchlist",
    "/browse",
    "/movie/157336-interstellar",
    "/tv/225385-black-doves",
    "/tv/225385-black-doves/season/1",
    "/mood/feel-good"
]

results = {}
for r in routes:
    print(f"Inspecting {r}...")
    results[r] = inspect_page(r)

with open("scratch/page_structures.json", "w", encoding="utf-8") as f:
    json.dump(results, f, indent=2)

print("Saved scratch/page_structures.json")
