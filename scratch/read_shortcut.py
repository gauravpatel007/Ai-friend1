import win32com.client

shell = win32com.client.Dispatch("WScript.Shell")
shortcut_path = r"C:\Users\Gaurav Patel\OneDrive\Desktop\AI Desktop Friend.lnk"
shortcut = shell.CreateShortCut(shortcut_path)

print(f"Target: {shortcut.TargetPath}")
print(f"Arguments: {shortcut.Arguments}")
print(f"Working Directory: {shortcut.WorkingDirectory}")
print(f"Icon Location: {shortcut.IconLocation}")
