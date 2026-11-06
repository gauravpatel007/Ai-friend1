import os
import re
import json
import requests
from urllib.parse import urljoin

BASE_URL = "https://reelipse.com"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
}

routes_to_test = [
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
]

session = requests.Session()
session.headers.update(headers)

results = {}

print("Probing routes...")
for r in routes_to_test:
    target_url = urljoin(BASE_URL, r)
    try:
        resp = session.get(target_url, timeout=12)
        print(f"[{resp.status_code}] {r} (length: {len(resp.text)})")
        results[r] = {
            "status": resp.status_code,
            "length": len(resp.text),
            "final_url": resp.url,
            "title": re.search(r"<title>(.*?)</title>", resp.text, re.IGNORECASE).group(1) if re.search(r"<title>(.*?)</title>", resp.text, re.IGNORECASE) else "No Title",
            "html_sample": resp.text[:1000]
        }
        # Find movie links on homepage
        if r == "/":
            movie_links = re.findall(r'href="(/movie/[^"]+)"', resp.text)
            tv_links = re.findall(r'href="(/tv/[^"]+)"', resp.text)
            mood_links = re.findall(r'href="(/mood[^"]*)"', resp.text)
            list_links = re.findall(r'href="(/best[^"]*)"', resp.text)
            order_links = re.findall(r'href="(/watch-order[^"]*)"', resp.text)
            print(f"  Found {len(movie_links)} movie links: {movie_links[:3]}")
            print(f"  Found {len(tv_links)} TV links: {tv_links[:3]}")
            print(f"  Found {len(mood_links)} mood links: {mood_links[:3]}")
            print(f"  Found {len(list_links)} list links: {list_links[:3]}")
            print(f"  Found {len(order_links)} watch-order links: {order_links[:3]}")
            results["_links"] = {
                "movie": list(dict.fromkeys(movie_links))[:5],
                "tv": list(dict.fromkeys(tv_links))[:5],
                "mood": list(dict.fromkeys(mood_links))[:5],
                "list": list(dict.fromkeys(list_links))[:5],
                "watch_order": list(dict.fromkeys(order_links))[:5]
            }
    except Exception as e:
        print(f"Error on {r}: {e}")
        results[r] = {"error": str(e)}

with open("scratch/routes_probe.json", "w", encoding="utf-8") as f:
    json.dump(results, f, indent=2)

print("Saved scratch/routes_probe.json")
