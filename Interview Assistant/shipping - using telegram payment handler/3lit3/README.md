# 3lit3 Interview Assistant — distribution build

Turns the source in `jarvis/` into a self-contained Windows app plus an optional
installer. **Nothing under `jarvis/` is modified** — the build copies what it needs
into `_build/app/` and works from the copy.

## Prerequisites

- **Windows 10/11 x64**
- **Python 3.11+ on PATH** (`python --version` must work). Store installs are fine.
- ~2 GB free for the build venv + PyInstaller output
- *(optional)* **Inno Setup 6** to also produce the installer:
  ```
  winget install -e --id JRSoftware.InnoSetup
  ```
  Without it the build still succeeds and you get the portable app.

## Build

One command, from this folder:

```
build.bat
```

Clean build (delete `_build` first):

```
build.bat --clean
```

The script: copies source → creates a build venv → installs `requirements.txt` +
PyInstaller → builds an onedir bundle → launches it for 8s as a smoke test →
builds the installer if Inno Setup is present.

## Outputs

| What | Where |
|------|-------|
| Portable app | `_build\dist\3lit3\3lit3.exe` |
| Installer | `_build\installer\3lit3_Interview_Assistant.exe` |

The portable folder (`_build\dist\3lit3\`) is fully self-contained — copy it
anywhere and run `3lit3.exe`. The console window is intentional: it is the
`[JARVIS]` transcript.

## Install (installer)

Run `3lit3_Interview_Assistant.exe`. It installs **per-user, no admin/UAC**, to:

```
%LocalAppData%\Programs\3lit3
```

and offers a Start-menu entry (and optionally a desktop icon). It also registers
the **`myapp://`** URL scheme under `HKCU` (current user only), so a link like
`myapp://anything` launches the assistant. Uninstalling removes the app **and**
its local config, memory, and logs so no key or CV is left on the machine.

## First run — configuration

No API key ships inside the build. On first launch the app finds no
`config\api_keys.json` and the UI asks for your **Gemini API key**, then writes it
to the app's own folder:

```
<install>\config\api_keys.json
```

Other first-run settings (microphone, speakers/system-sound, CV path) are chosen
in the UI and saved next to it. The Gemini key is the only strictly required one;
the rest are optional.

## Secrets

The build **never** bundles credentials. `api_keys.json`, `*.key`, `*.crt`,
`*.pdf` (the CV), and `long_term.json` are excluded from the copy step, so your
personal Gemini key, Telegram token, TLS certs, CV, and long-term memory do not
end up in the exe or the installer.

## What's in the bundle

- `3lit3.exe` — console entry point
- `_internal\` — Python runtime, libraries, and bundled data
  (`core\prompt.txt`, `core\face_model.obj`, `dashboard\static\`)
- `core\`, `actions\`, `plugins\`, `memory\`, `config\` — the on-disk source the
  action/plugin loaders scan at startup (they need real `.py` files on disk)

**Deliberately excluded** to keep the bundle lean:
- `playwright` — browser control is opt-in; excluding it makes the loader skip
  `browser_control` cleanly instead of failing.
- `openwakeword` — local wake word; installed on demand from the app's settings.

## Troubleshooting

- **The exe dies at launch** — the smoke test fails the build and prints the last
  lines of the console log; that transcript names the missing DLL or import.
  Re-run and read `_build\smoke.log`.
- **No system sound during interview** — set Windows default output to the stereo
  `Speakers (VB-Audio Virtual Cable)` device (not the 16-channel endpoint).
- **Installer step skipped** — Inno Setup isn't installed. The portable app is
  still complete; install Inno Setup 6 and re-run `build.bat`.
- ** antivirus false positive** — a freshly built, unsigned PyInstaller exe is
  occasionally flagged. Signing the exe (not done here) resolves it.
