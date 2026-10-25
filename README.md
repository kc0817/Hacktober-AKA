# Image Archive

A desktop app that captures the screen only after you sign in, accept the notice,
and press **Sign in and start capture**.
While it is running, it sends one full-screen JPEG to Snowflake every three
seconds, with the capture time, foreground application, device name, and
operating system.

## Privacy and storage

- The app opens to an empty Snowflake setup form. Capture does not start on launch.
- You must sign in and accept the capture notice before starting.
- At three-second intervals, the app can create about 1,200 Snowflake rows per
  hour; Snowflake storage and usage charges may apply.
- Screenshots are captured in memory, compressed as JPEG, and inserted directly
  into a Snowflake `BINARY` column. The app does not write screenshot files to
  your device.
- Snowflake settings are held in memory only and cleared when the app closes.
- Press **Stop capture** to end uploads. macOS may ask you to grant Screen
  Recording permission the first time a screenshot is taken.

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

The window opens to the blank setup form. `python agent.py --browser` opens the
same app in your default browser instead.

## Snowflake setup

Enter your Snowflake account identifier, username, and password in the app.
Database and schema are optional under **Advanced settings**: leave both blank
to use the defaults configured for your Snowflake user. The table defaults to
`SCREENSHOTS`. The app creates it if it does not exist. The Snowflake role must
be allowed to create the table and insert and select rows in it. If your user
does not have default database and schema values, fill in both under Advanced
settings.

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
