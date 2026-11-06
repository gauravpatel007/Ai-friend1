import sys
print("Python:", sys.version)

for mod in ['httpx', 'requests', 'urllib.request', 'bs4', 'playwright', 'selenium']:
    try:
        __import__(mod)
        print(f"  {mod}: available")
    except ImportError:
        print(f"  {mod}: not available")
