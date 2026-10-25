import argparse
import base64
import ctypes
import io
import platform
import re
import threading
import time
import uuid
import webbrowser
from datetime import datetime, timezone

import mss
import snowflake.connector
from flask import Flask, jsonify, render_template_string, request
from PIL import Image
from werkzeug.serving import make_server

try:
    import webview
except ImportError:
    webview = None


app = Flask(__name__)
CAPTURE_INTERVAL_SECONDS = 3
MAX_INITIAL_RECORDS = 50
MAX_IMAGE_BYTES = 7 * 1024 * 1024
IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_$]{0,254}$")

PAGE_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Image Archive</title>
    <style>
        * { box-sizing: border-box; }
        body { margin: 0; color: #222; background: #fff; font: 15px/1.5 Arial, Helvetica, sans-serif; }
        a { color: #00e; }
        .page { width: min(100% - 32px, 1050px); margin: 0 auto; }
        header { padding: 24px 0 14px; border-bottom: 1px solid #999; }
        h1 { margin: 0; font-size: 28px; font-weight: normal; }
        header p { margin: 4px 0 0; color: #555; }
        nav { padding: 9px 0; border-bottom: 1px solid #ccc; }
        nav a { margin-right: 18px; }
        main { padding: 20px 0 36px; }
        h2 { margin: 0 0 10px; font-size: 20px; font-weight: normal; }
        p { margin: 8px 0 14px; }
        .section { margin-bottom: 24px; }
        .notice { padding: 10px 12px; margin: 12px 0; border: 1px solid #aaa; background: #f7f7f7; }
        .notice.error { border-color: #a00; color: #800; }
        .setup { max-width: 620px; }
        .field { margin: 12px 0; }
        label { display: block; margin-bottom: 4px; }
        input[type="text"], input[type="password"] {
            width: 100%; padding: 7px; border: 1px solid #888; font: inherit;
        }
        details { margin: 16px 0; }
        summary { cursor: pointer; }
        button {
            padding: 7px 12px; border: 1px solid #888; background: #eee;
            color: #222; font: inherit; cursor: pointer;
        }
        button:hover { background: #ddd; }
        button:disabled { cursor: wait; color: #666; }
        .consent { display: flex; gap: 8px; align-items: flex-start; margin: 18px 0; }
        .consent input { margin-top: 5px; }
        .consent label { margin: 0; }
        .controls { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
        #captureStatus { margin-left: 4px; color: #555; }
        table { width: 100%; border-collapse: collapse; border-top: 1px solid #999; }
        th, td { padding: 9px 8px; border-bottom: 1px solid #ccc; text-align: left; vertical-align: top; }
        th { background: #f2f2f2; }
        .preview { display: block; max-width: 220px; max-height: 160px; border: 1px solid #ccc; }
        footer { padding: 12px 0; border-top: 1px solid #ccc; color: #666; font-size: 13px; }
        @media (max-width: 700px) { table { font-size: 13px; } .preview { max-width: 130px; } }
    </style>
</head>
<body>
    <div class="page">
        <header>
            <h1>Image Archive</h1>
            <p>Screenshots go directly to your Snowflake table.</p>
        </header>
        {% if configured %}
        <nav aria-label="Main navigation"><a href="#archive">Recent images</a></nav>
        <main>
            <section class="section">
                <h2>Capture</h2>
                <p>When you start, a screenshot and its timestamp, active app, device, and operating system are uploaded every three seconds. That is about 1,200 rows per hour; Snowflake usage charges may apply.</p>
                <div class="controls">
                    <button id="captureButton" type="button">Start capture</button>
                    <button id="settingsButton" type="button">Sign out</button>
                    <span id="captureStatus" role="status">Capture is off.</span>
                </div>
                <p id="captureError" class="notice error" hidden></p>
            </section>
            <section class="section" id="archive">
                <h2>Recent images</h2>
                <p id="emptyMessage">No screenshots found in this Snowflake table.</p>
                <table id="captureTable" hidden>
                    <thead>
                        <tr><th>Capture ID</th><th>Timestamp</th><th>Active app</th><th>Device</th><th>System</th><th>Screenshot</th></tr>
                    </thead>
                    <tbody id="captureRows"></tbody>
                </table>
            </section>
        </main>
        {% else %}
        <nav aria-label="Main navigation"><a href="#setup">Snowflake sign in</a></nav>
        <main>
            <section class="section setup" id="setup">
                <h2>Sign in to Snowflake</h2>
                <p>Enter your account and login. Database and schema can be left blank if they are already set as defaults for your Snowflake user.</p>
                <form id="setupForm">
                    <div class="field">
                        <label for="account">Account identifier</label>
                        <input id="account" name="account" type="text" placeholder="e.g. organization-account" autocomplete="organization" required>
                    </div>
                    <div class="field">
                        <label for="username">Username</label>
                        <input id="username" name="username" type="text" autocomplete="username" required>
                    </div>
                    <div class="field">
                        <label for="password">Password</label>
                        <input id="password" name="password" type="password" autocomplete="current-password" required>
                    </div>
                    <details>
                        <summary>Advanced settings (optional)</summary>
                        <p>Leave database and schema blank to use your Snowflake user defaults. The table name defaults to SCREENSHOTS.</p>
                        <div class="field">
                            <label for="database">Database</label>
                            <input id="database" name="database" type="text" autocomplete="off">
                        </div>
                        <div class="field">
                            <label for="schema">Schema</label>
                            <input id="schema" name="schema" type="text" autocomplete="off">
                        </div>
                        <div class="field">
                            <label for="table">Table name</label>
                            <input id="table" name="table" type="text" value="SCREENSHOTS" autocomplete="off">
                        </div>
                    </details>
                    <div class="consent">
                        <input id="consent" name="consent" type="checkbox" required>
                        <label for="consent">I understand that when I start capture, full-screen screenshots and the app/device details listed above will be uploaded to Snowflake every three seconds until I stop.</label>
                    </div>
                    <button id="setupButton" type="submit">Sign in and start capture</button>
                    <p id="setupError" class="notice error" hidden></p>
                </form>
            </section>
        </main>
        {% endif %}
        <footer>Screenshots are held in memory for upload and are not saved as files on this device. Login details are cleared when the app closes or you sign out.</footer>
    </div>
    {% if configured %}
    <script>
        const captureButton = document.getElementById('captureButton');
        const settingsButton = document.getElementById('settingsButton');
        const statusText = document.getElementById('captureStatus');
        const errorBox = document.getElementById('captureError');
        const rows = document.getElementById('captureRows');
        const table = document.getElementById('captureTable');
        const emptyMessage = document.getElementById('emptyMessage');
        let lastTimestamp = null;
        let busy = false;

        function addCapture(record) {
            const row = document.createElement('tr');
            const values = [
                record.capture_id, record.timestamp, record.application,
                record.device, record.system
            ];
            for (const value of values) {
                const cell = document.createElement('td');
                cell.textContent = value;
                row.appendChild(cell);
            }
            const imageCell = document.createElement('td');
            const image = document.createElement('img');
            image.className = 'preview';
            image.alt = `Screenshot from ${record.application}`;
            image.src = `data:image/jpeg;base64,${record.image}`;
            imageCell.appendChild(image);
            row.appendChild(imageCell);
            rows.appendChild(row);
            table.hidden = false;
            emptyMessage.hidden = true;
            lastTimestamp = record.timestamp;
        }

        async function refreshCaptures() {
            if (busy) return;
            busy = true;
            try {
                const query = lastTimestamp ? `?after=${encodeURIComponent(lastTimestamp)}` : '';
                const response = await fetch(`/api/captures${query}`);
                const data = await response.json();
                if (!response.ok) throw new Error(data.error || 'Could not load captures.');
                for (const record of data.captures) addCapture(record);
                errorBox.hidden = true;
            } catch (error) {
                errorBox.textContent = error.message;
                errorBox.hidden = false;
            } finally {
                busy = false;
            }
        }

        async function refreshStatus() {
            const response = await fetch('/api/status');
            const data = await response.json();
            statusText.textContent = data.stopping
                ? 'Stopping after the current upload...'
                : data.active ? 'Capture is on.' : 'Capture is off.';
            captureButton.textContent = data.stopping
                ? 'Stopping...'
                : data.active ? 'Stop capture' : 'Start capture';
            captureButton.disabled = data.stopping;
            settingsButton.disabled = data.active || data.stopping;
            if (data.error) {
                errorBox.textContent = data.error;
                errorBox.hidden = false;
            }
        }

        captureButton.addEventListener('click', async () => {
            captureButton.disabled = true;
            errorBox.hidden = true;
            const endpoint = captureButton.textContent === 'Stop capture'
                ? '/api/stop'
                : '/api/start';
            try {
                const response = await fetch(endpoint, {method: 'POST'});
                const data = await response.json();
                if (!response.ok) throw new Error(data.error || 'Could not change capture state.');
                await refreshStatus();
                if (endpoint === '/api/start') await refreshCaptures();
            } catch (error) {
                errorBox.textContent = error.message;
                errorBox.hidden = false;
                captureButton.disabled = false;
            }
        });

        settingsButton.addEventListener('click', async () => {
            const response = await fetch('/api/settings', {method: 'DELETE'});
            if (response.ok) {
                window.location.reload();
            } else {
                const data = await response.json();
                errorBox.textContent = data.error || 'Could not sign out.';
                errorBox.hidden = false;
            }
        });

        refreshCaptures();
        refreshStatus();
        window.setInterval(refreshCaptures, 3000);
        window.setInterval(refreshStatus, 1000);
    </script>
    {% else %}
    <script>
        document.getElementById('setupForm').addEventListener('submit', async (event) => {
            event.preventDefault();
            const form = event.currentTarget;
            const button = document.getElementById('setupButton');
            const error = document.getElementById('setupError');
            button.disabled = true;
            error.hidden = true;
            const settings = Object.fromEntries(new FormData(form).entries());
            settings.consent = document.getElementById('consent').checked;
            try {
                const response = await fetch('/api/start', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(settings)
                });
                const data = await response.json();
                if (!response.ok) throw new Error(data.error || 'Could not sign in to Snowflake.');
                window.location.reload();
            } catch (err) {
                error.textContent = err.message;
                error.hidden = false;
                button.disabled = false;
            }
        });
    </script>
    {% endif %}
</body>
</html>
"""


def _validated_settings(values):
    if not isinstance(values, dict):
        raise ValueError("Submit the Snowflake sign-in form to continue.")

    required = {
        "account": "Account identifier",
        "username": "Username",
        "password": "Password",
    }
    missing = [
        label for key, label in required.items()
        if not isinstance(values.get(key), str) or not values[key].strip()
    ]
    if missing:
        raise ValueError("Fill in the required sign-in fields: " + ", ".join(missing))

    database = values.get("database", "").strip()
    schema = values.get("schema", "").strip()
    table = values.get("table", "").strip() or "SCREENSHOTS"
    if bool(database) != bool(schema):
        raise ValueError("Enter both database and schema under Advanced settings, or leave both blank.")
    for label, value in (("Database", database), ("Schema", schema), ("Table name", table)):
        if value and not IDENTIFIER_PATTERN.fullmatch(value):
            raise ValueError(
                f"{label} must start with a letter or underscore and contain "
                "only letters, numbers, underscores, or dollar signs."
            )
    if values.get("consent") not in (True, "true", "on", "1"):
        raise ValueError("Accept the screenshot and Snowflake upload notice before starting.")

    return {
        "account": values["account"].strip(),
        "username": values["username"].strip(),
        "password": values["password"],
        "database": database.upper(),
        "schema": schema.upper(),
        "table": table.upper(),
    }


def _connect(settings):
    options = {
        "account": settings["account"],
        "user": settings["username"],
        "password": settings["password"],
    }
    if settings["database"]:
        options["database"] = settings["database"]
        options["schema"] = settings["schema"]
    return snowflake.connector.connect(**options)


def _qualified_table(settings):
    table = f'"{settings["table"]}"'
    if not settings["database"]:
        return table
    return f'"{settings["database"]}"."{settings["schema"]}".{table}'


def _create_capture_table(settings):
    connection = _connect(settings)
    cursor = connection.cursor()
    try:
        cursor.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {_qualified_table(settings)} (
                CAPTURE_ID VARCHAR(36) NOT NULL,
                CAPTURED_AT TIMESTAMP_TZ(9) NOT NULL,
                APPLICATION VARCHAR(512),
                DEVICE VARCHAR(512),
                OPERATING_SYSTEM VARCHAR(128),
                IMAGE BINARY
            )
            """
        )
    finally:
        cursor.close()
        connection.close()


def _active_application():
    operating_system = platform.system()
    if operating_system == "Darwin":
        from AppKit import NSWorkspace

        running_app = NSWorkspace.sharedWorkspace().frontmostApplication()
        return running_app.localizedName() if running_app else "Unknown"

    if operating_system == "Windows":
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        foreground_window = user32.GetForegroundWindow
        foreground_window.restype = ctypes.c_void_p
        window = foreground_window()
        process_id = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(window, ctypes.byref(process_id))
        open_process = kernel32.OpenProcess
        open_process.argtypes = (ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong)
        open_process.restype = ctypes.c_void_p
        process = open_process(0x1000, False, process_id.value)
        if process:
            try:
                path = ctypes.create_unicode_buffer(32768)
                path_size = ctypes.c_ulong(len(path))
                if kernel32.QueryFullProcessImageNameW(
                    process, 0, path, ctypes.byref(path_size)
                ):
                    return path.value.rsplit("\\", 1)[-1].rsplit(".", 1)[0]
            finally:
                kernel32.CloseHandle(process)

        title = ctypes.create_unicode_buffer(512)
        user32.GetWindowTextW(window, title, len(title))
        return title.value or "Unknown"

    return "Unknown"


def _screenshot_jpeg():
    with mss.mss() as screen:
        shot = screen.grab(screen.monitors[0])
    image = Image.frombytes("RGB", shot.size, shot.rgb)

    def encode_jpeg(source, quality):
        output = io.BytesIO()
        source.save(output, format="JPEG", quality=quality, optimize=True)
        return output.getvalue()

    image_bytes = encode_jpeg(image, 82)
    if len(image_bytes) > MAX_IMAGE_BYTES:
        image.thumbnail((2560, 1600), Image.Resampling.LANCZOS)
        image_bytes = encode_jpeg(image, 75)
    if len(image_bytes) > MAX_IMAGE_BYTES:
        image.thumbnail((1920, 1200), Image.Resampling.LANCZOS)
        image_bytes = encode_jpeg(image, 68)
    if len(image_bytes) > MAX_IMAGE_BYTES:
        raise RuntimeError("Screenshot is too large to store in the Snowflake row.")
    return image_bytes


class CaptureManager:
    def __init__(self):
        self._lock = threading.RLock()
        self._settings = None
        self._stop_event = threading.Event()
        self._thread = None
        self._error = None

    def status(self):
        with self._lock:
            alive = self._thread is not None and self._thread.is_alive()
            return {
                "configured": self._settings is not None,
                "active": alive and not self._stop_event.is_set(),
                "stopping": alive and self._stop_event.is_set(),
                "error": self._error,
            }

    def settings(self):
        with self._lock:
            return dict(self._settings) if self._settings else None

    def start(self, values=None):
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                raise RuntimeError("Capture is already running or stopping.")

            if values is None:
                if self._settings is None:
                    raise ValueError("Sign in to Snowflake before starting capture.")
                settings = dict(self._settings)
            else:
                settings = _validated_settings(values)

            _create_capture_table(settings)
            self._settings = settings
            self._error = None
            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._capture_loop,
                args=(settings,),
                daemon=True,
                name="snowflake-screen-capture",
            )
            self._thread.start()

    def stop(self):
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                self._stop_event.set()

    def clear_settings(self):
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                raise RuntimeError("Stop capture before signing out.")
            self._settings = None
            self._error = None

    def _capture_loop(self, settings):
        connection = None
        cursor = None
        try:
            connection = _connect(settings)
            cursor = connection.cursor()
            insert_sql = f"""
                INSERT INTO {_qualified_table(settings)}
                    (CAPTURE_ID, CAPTURED_AT, APPLICATION, DEVICE,
                     OPERATING_SYSTEM, IMAGE)
                VALUES (%s, %s, %s, %s, %s, %s)
            """
            while not self._stop_event.is_set():
                started = time.monotonic()
                cursor.execute(
                    insert_sql,
                    (
                        str(uuid.uuid4()),
                        datetime.now(timezone.utc),
                        _active_application(),
                        platform.node() or "Unknown",
                        platform.platform(),
                        _screenshot_jpeg(),
                    ),
                )
                self._stop_event.wait(
                    max(0, CAPTURE_INTERVAL_SECONDS - (time.monotonic() - started))
                )
        except Exception:
            app.logger.exception("Screenshot capture or Snowflake upload failed")
            with self._lock:
                self._error = (
                    "Capture stopped because a screenshot or Snowflake upload failed. "
                    "Check the app log and screen-recording permission."
                )
            self._stop_event.set()
        finally:
            for resource in (cursor, connection):
                if resource is not None:
                    try:
                        resource.close()
                    except Exception:
                        app.logger.exception("Could not close a Snowflake capture resource")


capture_manager = CaptureManager()


def _serialize_capture(row):
    timestamp = row[1]
    if isinstance(timestamp, datetime):
        timestamp = timestamp.isoformat()
    return {
        "capture_id": row[0],
        "timestamp": str(timestamp),
        "application": row[2] or "Unknown",
        "device": row[3] or "Unknown",
        "system": row[4] or "Unknown",
        "image": base64.b64encode(bytes(row[5])).decode("ascii"),
    }


def _read_captures(settings, after):
    connection = _connect(settings)
    cursor = connection.cursor()
    try:
        table = _qualified_table(settings)
        if after:
            try:
                after_time = datetime.fromisoformat(after)
            except ValueError as error:
                raise ValueError("Invalid capture timestamp.") from error
            cursor.execute(
                f"""
                SELECT CAPTURE_ID, CAPTURED_AT, APPLICATION, DEVICE, OPERATING_SYSTEM, IMAGE
                FROM {table}
                WHERE CAPTURED_AT > %s
                ORDER BY CAPTURED_AT ASC
                LIMIT 100
                """,
                (after_time,),
            )
            records = cursor.fetchall()
        else:
            cursor.execute(
                f"""
                SELECT CAPTURE_ID, CAPTURED_AT, APPLICATION, DEVICE, OPERATING_SYSTEM, IMAGE
                FROM {table}
                ORDER BY CAPTURED_AT DESC
                LIMIT {MAX_INITIAL_RECORDS}
                """
            )
            records = list(reversed(cursor.fetchall()))
        return [_serialize_capture(row) for row in records]
    finally:
        cursor.close()
        connection.close()


@app.route("/")
def home():
    return render_template_string(
        PAGE_TEMPLATE,
        configured=capture_manager.settings() is not None,
    )


@app.route("/api/start", methods=["POST"])
def start_capture():
    values = request.get_json(silent=True)
    try:
        capture_manager.start(values)
    except ValueError as error:
        return jsonify({"error": str(error)}), 400
    except RuntimeError as error:
        return jsonify({"error": str(error)}), 409
    except Exception:
        app.logger.exception("Could not connect or prepare the Snowflake table")
        return jsonify(
            {
                "error": (
                    "Could not sign in or prepare the table. Check your credentials "
                    "and Snowflake permissions. If your user has no default database "
                    "and schema, enter them under Advanced settings."
                )
            }
        ), 502
    return jsonify({"active": True}), 200


@app.route("/api/stop", methods=["POST"])
def stop_capture():
    capture_manager.stop()
    return jsonify({"active": False}), 200


@app.route("/api/status")
def capture_status():
    return jsonify(capture_manager.status())


@app.route("/api/settings", methods=["DELETE"])
def clear_settings():
    try:
        capture_manager.clear_settings()
    except RuntimeError as error:
        return jsonify({"error": str(error)}), 409
    return jsonify({"configured": False}), 200


@app.route("/api/captures")
def recent_captures():
    settings = capture_manager.settings()
    if settings is None:
        return jsonify({"error": "Sign in to Snowflake to load screenshots."}), 409
    try:
        records = _read_captures(settings, request.args.get("after"))
    except ValueError as error:
        return jsonify({"error": str(error)}), 400
    except Exception:
        app.logger.exception("Could not read screenshots from Snowflake")
        return jsonify({"error": "Could not read screenshots from Snowflake."}), 502
    return jsonify({"captures": records}), 200


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Launch the Image Archive desktop app.")
    parser.add_argument(
        "--browser",
        action="store_true",
        help="Open the app in your browser instead of a desktop window.",
    )
    args = parser.parse_args()

    server = make_server("127.0.0.1", 0, app, threaded=True)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    url = f"http://127.0.0.1:{server.server_port}"

    try:
        if args.browser:
            webbrowser.open(url)
            server_thread.join()
        elif webview is None:
            raise SystemExit(
                "Desktop window support is missing. Install dependencies with "
                "'python -m pip install -r requirements.txt'."
            )
        else:
            webview.create_window(
                "Image Archive",
                url,
                width=1100,
                height=760,
                min_size=(760, 540),
            )
            webview.start()
    finally:
        capture_manager.stop()
        server.shutdown()
