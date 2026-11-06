from pathlib import Path

a2_dir = Path("G:/Languages/Projects/Pet/A2")
for f in a2_dir.rglob("*.py"):
    if ".venv" in str(f):
        continue
    try:
        txt = f.read_text(encoding="utf-8", errors="ignore")
        if "setWindowFlags" in txt or "WA_TranslucentBackground" in txt:
            print(f"File: {f.relative_to(a2_dir)}")
            for idx, line in enumerate(txt.splitlines()):
                if any(k in line for k in ["setWindowFlags", "WA_TranslucentBackground", "WindowStaysOnTopHint", "FramelessWindowHint", "Tool"]):
                    print(f"  Line {idx+1}: {line.strip()}")
    except Exception:
        pass
