import os
from pathlib import Path

p = Path("G:/Languages/Projects/Pet/A2")
print("A2 exists:", p.exists())
if p.exists():
    files = list(p.glob("*"))
    print("A2 top-level:", [f.name for f in files[:15]])
