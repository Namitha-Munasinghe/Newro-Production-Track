# Building the Windows desktop app

PyInstaller can't cross-compile — it has to run on an actual Windows machine
to produce a Windows `.exe`. Everything else (the Flask app, the pywebview
wrapper, the offline-vendored JS/CSS) is already done and was verified
working locally; this is just the packaging step.

## 1. Prerequisites (on the Windows machine)

- Python 3.11+ installed (check "Add python.exe to PATH" during install)
- A copy of this whole project folder
- **Microsoft Edge WebView2 Runtime.** This is the actual rendering engine
  the app runs in — without it, the app still opens but silently falls back
  to the ancient Internet Explorer engine, which can't run this app's JS/CSS
  at all (looks like faded/broken styling, dead buttons, a calendar that
  won't open). Most Windows 10/11 PCs already have it (it ships with
  Windows 11 and is pushed via Windows Update on most Windows 10 machines),
  but **don't assume the client's PC has it** — some locked-down or older
  machines don't. Install it from
  https://developer.microsoft.com/microsoft-edge/webview2/ (small download,
  no restart needed) on **every** machine this app will run on, including
  the client's — this needs doing once per PC, not just once per build.

## 2. Set up and smoke-test first

```powershell
cd path\to\Newro-Production-Track
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt

python desktop_app.py
```

A window titled "Newro Operations" should open with the PIN login screen
(default PIN: `1234`, unless it's been changed in Settings). Confirm the
whole app works end to end here — log in, view the log sheet, open the
calendar, add a batch — before bundling, since that's much faster to debug
than a built `.exe`.

## 3. Build the .exe

```powershell
pyinstaller --name "NewroOperations" --onefile --windowed --add-data "templates;templates" --add-data "static;static" desktop_app.py
```

- `--onefile` — a single `.exe` the client can double-click, no install step
- `--windowed` — suppresses the black console window behind the app
- `--add-data "templates;templates"` / `"static;static"` — bundles the Jinja
  templates and CSS/JS/images into the executable (Windows uses `;` as the
  separator here; on macOS/Linux it's `:`, but this command is Windows-only)

The result is `dist\NewroOperations.exe`. Copy that one file to the client's
machine and run it — no Python install needed on their end.

## What happens on first run

- The app creates its database at `%APPDATA%\NewroOperations\newro_poultry.db`
  the first time it's launched, and reuses it on every launch after that —
  it survives replacing the `.exe` with a newer build.
- It finds a free local port automatically and opens the window once the
  server responds, so there's no fixed port to conflict with.

## Known gaps in this first pass (deliberately deferred)

- **No app icon** — uses the default PyInstaller icon. Add one later with
  `--icon=path\to\icon.ico`.
- **No installer** — it's a bare `.exe`, not a "Setup.exe" / MSI with Start
  Menu shortcuts. Fine for testing; worth doing properly before wider rollout.
- **Unsigned** — Windows SmartScreen will likely show an "Unknown publisher"
  warning the first time the client runs it. That's expected for an unsigned
  binary, not a bug. Proper distribution would need a code-signing
  certificate.

## Troubleshooting

**App opens but looks faded, calendar doesn't open, buttons seem missing or
dead, clicking into a product does nothing.** This is the WebView2 Runtime
issue described above — that PC is missing it, so the app fell back to a
rendering engine that can't run modern JS/CSS. Install the runtime from the
link above and relaunch the app; no rebuild needed. `desktop_app.py` now
forces the modern engine explicitly, so on any build made after this note
was added, this failure instead shows a clear popup telling you exactly
this, rather than silently rendering broken.

**Antivirus/Defender flags or deletes the `.exe`, or it won't launch at
all.** Common false-positive with PyInstaller `--onefile` builds — the
self-extracting technique looks similar to real malware droppers. Check
Windows Defender's "Protection history" and restore/allow it from there.

**"Download PDF" says "Generating…" and never produces a file.** Browser-style
downloads (`pdf.save()`) work by clicking a hidden link to a `blob:` URL —
that mechanism isn't reliably supported inside an embedded WebView2 control,
so it can complete successfully with no error and no file. Fixed by routing
PDF saves through a native Save dialog (`Api.save_pdf_file` in
`desktop_app.py`) instead, on any build made after this note was added. If
you still see this on a current build, check whether the Save dialog opened
*behind* the app window rather than not opening at all.
