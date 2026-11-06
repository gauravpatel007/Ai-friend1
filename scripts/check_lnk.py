import tempfile
import subprocess
import os

lnk_path = r"C:\Users\Gaurav Patel\OneDrive\Desktop\AI Desktop Friend.lnk"
vbs = f"""
Set WshShell = CreateObject("WScript.Shell")
Set oShortcut = WshShell.CreateShortcut("{lnk_path}")
WScript.Echo "TargetPath: " & oShortcut.TargetPath
WScript.Echo "Arguments: " & oShortcut.Arguments
WScript.Echo "WorkingDirectory: " & oShortcut.WorkingDirectory
WScript.Echo "IconLocation: " & oShortcut.IconLocation
"""

tf = tempfile.NamedTemporaryFile("w", suffix=".vbs", delete=False)
tf.write(vbs)
tf.close()

res = subprocess.run(["cscript", "//nologo", tf.name], capture_output=True, text=True)
print(res.stdout)
os.remove(tf.name)
