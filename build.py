#!/usr/bin/env python3
"""Build a single-file desktop app with PyInstaller:  pip install -r requirements-build.txt && python build.py"""
import platform, shutil, subprocess, sys
from pathlib import Path

system = platform.system()
cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile", "--name", "OpenDM", "opendm.py"]
if system != "Darwin":
    cmd += ["--collect-submodules", "pystray"]  # the tray backends are imported dynamically
if system in ("Windows", "Darwin"):
    cmd.append("--windowed")  # no console window (GUI only; use `python opendm.py` for the CLI)
if system == "Windows":
    cmd += ["--icon", "assets/icon.ico"]
elif system == "Darwin":
    cmd += ["--icon", "assets/icon.icns"]
# Linux binaries can't carry an icon; the window icon is embedded in opendm.py instead.
subprocess.check_call(cmd)

dist = Path("dist")
if system == "Windows":
    (dist / "OpenDM.exe").replace(dist / "OpenDM-windows.exe")
elif system == "Darwin":
    shutil.make_archive(str(dist / "OpenDM-macos"), "zip", dist, "OpenDM.app")
else:
    (dist / "OpenDM").replace(dist / "OpenDM-linux")
print("Built:", *sorted(p.name for p in dist.iterdir()))
