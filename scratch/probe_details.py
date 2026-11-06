import requests
import json
import re

BASE_URL = "https://reelipse.com"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
}

extra_routes = [
    "/movie/891621-wild-horse-nine",
    "/movie/157336-interstellar",
    "/tv/225385-black-doves",
    "/mood/feel-good",
    "/best/best-movies-under-2-hours",
    "/tv/225385-black-doves/season-1",
    "/tv/225385-black-doves/season/1",
    "/tv/225385-black-doves/season-1/episode-1"
]

for r in extra_routes:
    resp = requests.get(BASE_URL + r, headers=headers)
    title = re.search(r"<title>(.*?)</title>", resp.text, re.IGNORECASE)
    title_str = title.group(1) if title else "No title"
    print(f"[{resp.status_code}] {r} -> {title_str} (len: {len(resp.text)})")
    if resp.status_code == 200 and "/tv/" in r:
        # Check season/episode links in TV page
        ep_links = re.findall(r'href="(/tv/[^"]+)"', resp.text)
        print(f"   TV page has internal links: {set(ep_links[:6])}")
