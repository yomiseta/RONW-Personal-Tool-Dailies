import os
import subprocess

PROCESS_NAME = "Ragnarok The New World.exe"

def is_running():
    """True if the game/launcher process already exists (so no need to open a second one)"""
    out = subprocess.run(
        ["tasklist", "/FI", f"IMAGENAME eq {PROCESS_NAME}", "/NH"],
        capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW,
    ).stdout
    return out.strip() != "" and "no tasks" not in out.lower()

def start(exe_path):
    """Opens the launcher"""
    subprocess.Popen([exe_path], cwd=os.path.dirname(exe_path))