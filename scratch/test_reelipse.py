import requests

url = "https://reelipse.com/"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
}

try:
    resp = requests.get(url, headers=headers, timeout=15)
    print(f"Status: {resp.status_code}")
    print(f"Headers: {resp.headers.get('content-type')}")
    print(f"Length: {len(resp.text)}")
    print("Preview:\n", resp.text[:1500])
except Exception as e:
    print("Error:", e)
