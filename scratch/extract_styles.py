import requests
import re
import json

resp = requests.get("https://reelipse.com/", headers={"User-Agent": "Mozilla/5.0"})
html = resp.text

# Extract CSS links
css_links = re.findall(r'<link[^>]+rel="stylesheet"[^>]+href="([^"]+)"', html)
print("CSS links:", css_links)

# Extract scripts
scripts = re.findall(r'<script[^>]+src="([^"]+)"', html)
print("Scripts:", scripts[:5])

# Extract inline styles
styles = re.findall(r'<style[^>]*>(.*?)</style>', html, re.DOTALL)
print(f"Inline style tags count: {len(styles)}")
combined_css = "\n".join(styles)

# Fetch linked CSS if any
for c in css_links:
    try:
        c_url = c if c.startswith("http") else "https://reelipse.com" + c
        c_resp = requests.get(c_url, headers={"User-Agent": "Mozilla/5.0"})
        combined_css += "\n" + c_resp.text
        print(f"Fetched CSS {c} (len: {len(c_resp.text)})")
    except Exception as e:
        print("CSS fetch error:", e)

# Extract color variables, hex codes, font families
colors = re.findall(r'#(?:[0-9a-fA-F]{3,8})\b', combined_css)
var_colors = re.findall(r'--[\w-]+:\s*[^;]+;', combined_css)
font_families = re.findall(r'font-family:\s*([^;]+);', combined_css)

print("Unique hex colors (top 20):", list(dict.fromkeys(colors))[:20])
print("CSS Variables (top 25):", list(dict.fromkeys(var_colors))[:25])
print("Font families:", list(dict.fromkeys(font_families))[:10])

with open("scratch/reelipse_styles.css", "w", encoding="utf-8") as f:
    f.write(combined_css[:200000]) # write sample

print("Done extracting styles.")
