# Snaptcha ©

A desktop app that captures the full screen after you accept the notice and
press **Start capture**, then repeats at your chosen interval. The UI shows
the screenshot count and a session history with the capture time, active app,
device, operating system, and image dimensions.
The app-frequency chart and activity summary are calculated from capture metadata
only; hovering over or keyboard-focusing a chart point shows that app's capture
count, session share, and first/last capture times. Screenshot image content is
not analyzed. The chart scales to the available panel width, so it does not need
horizontal scrolling.
The page also includes a Claude chat panel, but chat is currently a disabled UI
placeholder; it does not call Claude or access screenshot images.
Choose a capture interval from 1 to 3,600 seconds before starting; the default
is three seconds.

## Privacy and storage

- Capture does not start on launch. Accept the notice and press **Start capture**
  to begin; press **Stop capture** to end it.
- Image pixels are discarded after each capture. They are not saved to disk,
  displayed, or uploaded. Capture metadata is kept in memory and shown in the
  history; it is cleared when the app closes.
- The capture interval is used only for the current run and is not saved.
- The active app is reported on macOS. Other platforms show `Unknown`.
- macOS may ask you to grant Screen Recording permission the first time a
  screenshot is taken.

## Run from source

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
python agent.py
```

The window opens to the local screenshot archive. `python agent.py --browser`
opens the same app in your default browser instead.

## Build a desktop app

Build on the operating system where the app will run; PyInstaller does not
cross-build macOS and Windows apps:

```text
python -m pip install -r requirements.txt
python build_app.py
```

The macOS app is `dist/ImageArchive.app`. The Windows app is
`dist/ImageArchive.exe`. Windows may require the Microsoft Edge WebView2
runtime.
