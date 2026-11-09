# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for 3lit3 Interview Assistant (onedir).

Layout contract (the whole reason onedir + a datas tree, not onefile):
  <root>/main.py, <root>/core/..., <root>/actions/..., <root>/config/...  on DISK
  <root>/3lit3.exe                                                       the frozen entry

Every module resolves its assets with `Path(sys.executable).parent` when frozen,
so shipping the real source tree next to the exe keeps every path valid WITHOUT
rewriting the app. Actions and plugins are discovered by scanning the filesystem
(core/action_loader.py, core/plugin_loader.py glob `*.py`), so those directories
MUST be real files on disk — they cannot live inside the PYZ archive.

Secrets are never bundled: config/api_keys.json is NOT in `datas`. On first run the
app finds no config and the UI asks for the Gemini key, writing it to the user's
own <root>/config/api_keys.json (the exe dir is per-user under LocalAppData).

playwright and openwakeword are excluded on purpose — both are multi-hundred-MB and
opt-in. Excluding playwright makes core/action_loader.py skip browser_control with a
logged ImportError instead of crashing; openwakeword is imported only inside a
function, so it is absent until the user installs it.
"""
import sys
from pathlib import Path

from PyInstaller.building.build_main import Analysis, PYZ, EXE, COLLECT

HERE = Path(SPECPATH).resolve()          # shipping/3lit3
SRC = HERE / "_build" / "app"            # pristine copy of jarvis/ made by build.bat
MAIN = SRC / "main.py"
ICON = SRC / "config" / "jarvis.ico"

# Data files the app reads off disk at runtime. Destinations are relative to the
# exe root, mirroring the source tree so `Path(sys.executable).parent / "core" / ...`
# keeps working. config/api_keys.json is deliberately absent (secret).
datas = [
    (str(SRC / "core" / "prompt.txt"), "core"),
    (str(SRC / "core" / "face_model.obj"), "core"),
    (str(SRC / "config" / "jarvis.ico"), "config"),
    (str(SRC / "dashboard" / "static"), "dashboard/static"),
]

# The action/plugin loaders glob the filesystem, so ship the real .py files.
# "client" holds licensing.py — main.py's _license_gate() inserts
# <dir of __file__>/client into sys.path, which frozen resolves under _internal.
for pkg in ("actions", "plugins", "core", "memory", "dashboard", "client"):
    pkg_dir = SRC / pkg
    if pkg_dir.is_dir():
        for py in pkg_dir.rglob("*.py"):
            rel = py.relative_to(SRC).parent
            datas.append((str(py), str(rel) if str(rel) != "." else pkg))

# The license server URL (public, one line) — client/licensing.py reads it from
# next to itself first; without it the gate falls back to 127.0.0.1:8000.
_lic_txt = SRC / "client" / "license_server.txt"
if _lic_txt.is_file():
    datas.append((str(_lic_txt), "client"))

hiddenimports = [
    # uvicorn's standard auto-selected submodules are resolved by string at
    # runtime and are invisible to static analysis.
    "uvicorn.logging",
    "uvicorn.loops.auto",
    "uvicorn.loops.asyncio",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan.on",
    "uvicorn.lifespan.off",
    # soundcard picks its backend (WASAPI/CoreAudio/ALSA) by import at call time.
    "soundcard",
    "soundcard._alsa",
    "soundcard._coreaudio",
    "soundcard._pulseaudio",
    "soundcard._win_api",
    # Windows-only modules imported lazily inside actions.
    "win32api",
    "win32gui",
    "win32con",
    "win32process",
    "pythoncom",
    "pywintypes",
    "comtypes",
    "comtypes.stream",
    "wmi",
]

excludes = [
    "playwright",
    "openwakeword",
    "torch",
    "IPython",
    "pytest",
    "setuptools",
    "tkinter",
]

a = Analysis(
    [str(MAIN)],
    pathex=[str(SRC)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="3lit3",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,                 # the [JARVIS] console transcript is part of the UX
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ICON),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="3lit3",
)
