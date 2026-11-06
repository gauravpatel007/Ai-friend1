import psutil
for p in psutil.process_iter(['pid', 'name', 'exe']):
    try:
        name = p.info['name'] or ''
        exe = p.info['exe'] or ''
        if any(x in name.lower() or x in exe.lower() for x in ['spider', 'pet', 'shimeji', 'desktop', 'companion', 'buddy']):
            print(f"PID: {p.info['pid']} | Name: {name} | Exe: {exe}")
    except Exception:
        pass
