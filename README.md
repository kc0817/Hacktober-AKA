# Screen Coach

A small desktop window that sits on top of Altium (or any app). Every few seconds it screenshots the
window you're working in and uploads it to Snowflake. When you type a question, Claude Sonnet 5.5
(effort `medium`) looks at your most recent screenshots and answers in the window.

## How it works

```
 ┌──────────────── your PC ─────────────────┐            ┌──────── Snowflake ────────┐
 │                                          │            │                           │
 │  QTimer every N s                        │   PUT      │  @SCREENSHOTS (stage)     │
 │   └─ capture.py: grab active window ─────┼──────────► │    <session>/<ts>.png     │
 │        (skip own window, skip dupes)     │  INSERT    │  SCREENSHOT_LOG (table)   │
 │        └─ Uploader thread (queue) ───────┼──────────► │    time, title, path      │
 │                                          │            │                           │
 │  Chat window (main.py)                   │  SELECT +  │                           │
 │   └─ question ─► AskWorker thread        │   GET      │                           │
 │        ├─ storage.recent(3) ◄────────────┼─────────── │                           │
 │        ├─ assistant.ask(q, images) ──────┼──► Claude API (claude-sonnet-5-5)       │
 │        └─ answer ─► transcript           │  INSERT    │  QUESTION_LOG (table)     │
 │                                          ├──────────► │                           │
 └──────────────────────────────────────────┘            └───────────────────────────┘
```

| File | Role |
|---|---|
| `app/main.py` | PySide6 window (always on top), capture timer, background upload + ask threads |
| `app/capture.py` | Screenshot of the foreground window (pywin32 + mss), downscaled, de-duplicated |
| `app/storage.py` | Snowflake: `PUT` PNG to stage, log metadata, fetch latest N for this session |
| `app/assistant.py` | Builds the Claude request: system prompt + labeled screenshots + question; keeps chat history |
| `app/config.py` | Settings from `.env` (model, effort, interval, image count) |
| `sql/setup.sql` | One-time database / stage / table creation |

## Setup (Windows — Altium is Windows-only)

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env   # fill in Anthropic + Snowflake credentials
```

Run `sql/setup.sql` once in a Snowflake worksheet, then:

```powershell
python -m app.main
```

Package as a double-click app:

```powershell
pip install pyinstaller
pyinstaller --noconsole --onefile --name ScreenCoach app/main.py
```

## Design notes / open decisions

- **Session scoping:** each launch gets a new `SESSION_ID`, and Claude only sees screenshots from that session.
- **Privacy:** only the focused window is captured, never the coach window itself; there's a Pause button.
  Consider adding a window-title allowlist (e.g. only `Altium Designer`) before demoing.
- **Cost:** each question sends `RECENT_IMAGE_COUNT` images (default 1, ~1.5k tokens each) plus the chat history so far. "New chat" resets it.
  Prompt caching is on, so earlier turns get cheaper on repeat.
- **Storage cap:** the database keeps at most `MAX_SCREENSHOTS` (in `.env`, default 500) across all users;
  every 10 uploads the app deletes the oldest files and rows. Run `python -m scripts.cleanup [--max N] [--dry-run]`
  to trim by hand.
- **Refusals:** server-side fallback (`fallbacks: "default"`) is enabled, so if a safety classifier declines a
  request it's retried on Anthropic's recommended fallback model.
- **Next steps:** stream the answer into the window token-by-token; a global hotkey to focus the box;
  let Claude ask for an older screenshot via a tool; use Snowflake Cortex to search past sessions.

## Image Archive (`agent.py`)

The main app: Ash's web-style window (Flask + pywebview) wired to Screen Coach's pipeline.
After you accept the notice and press **Start capture**, it screenshots the focused window every
`CAPTURE_INTERVAL_SEC` seconds (from `.env`) using `app/capture.py`, uploads each one with
`app/storage.py`, and lists it in the session history. The Claude chat panel sends your question plus
the latest screenshots through `app/assistant.py`. `app/main.py` is the older PySide6 window with the
same pipeline.

```
agent.py (UI + Flask routes)
  ├─ capture loop ─► app/capture.py ─► app/storage.py ─► Snowflake (or memory with --local)
  └─ POST /api/ask ─► storage.recent() ─► app/assistant.py ─► Claude
```

### Privacy and storage

- Capture does not start on launch. Accept the notice and press **Start capture**
  to begin; press **Stop capture** to end it.
- The focused window is captured every `CAPTURE_INTERVAL_SEC` seconds; while this app is focused it captures
  the last window you used instead.
- Screenshots are uploaded to Snowflake, or kept in memory only with `--local`.
- When you ask a question, the latest `RECENT_IMAGE_COUNT` screenshot(s) (default 1) and the question are sent to Claude.
- The active app is the window title on Windows; macOS reports the app name and
  may ask for Screen Recording permission the first time a screenshot is taken.

### Run from source

Install Python 3.9 or newer. In Terminal (macOS) or PowerShell (Windows):

```text
python -m venv .venv
```

Activate the environment:

```text
# macOS
source .venv/bin/activate

# Windows PowerShell
.venv\Scripts\Activate.ps1
```

Install dependencies and launch:

```text
python -m pip install -r requirements.txt
python agent.py            # uploads to Snowflake (needs SNOWFLAKE_* in .env)
python agent.py --local    # no Snowflake; screenshots stay in memory
```

`--browser` opens the same app in your default browser instead of a desktop window.
From WSL, use the Windows Python: `wpy agent.py --local`.

### Build a desktop app

Build on the operating system where the app will run; PyInstaller does not
cross-build macOS and Windows apps:

```text
python -m pip install -r requirements.txt
python build_app.py
```

The macOS app is `dist/ImageArchive.app`. The Windows app is
`dist/ImageArchive.exe`. Windows may require the Microsoft Edge WebView2
runtime.
