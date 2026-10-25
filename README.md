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
- **Cost:** each question sends 3 images (~1.5k tokens each) plus the chat history so far. "New chat" resets it.
  Prompt caching is on, so earlier turns get cheaper on repeat.
- **Refusals:** server-side fallback (`fallbacks: "default"`) is enabled, so if a safety classifier declines a
  request it's retried on Anthropic's recommended fallback model.
- **Next steps:** stream the answer into the window token-by-token; a global hotkey to focus the box;
  let Claude ask for an older screenshot via a tool; use Snowflake Cortex to search past sessions.
