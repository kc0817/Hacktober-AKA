import argparse
import platform
import threading
import time
import uuid
import webbrowser
from datetime import datetime, timezone

import mss
from flask import Flask, jsonify, render_template_string, request
from werkzeug.serving import make_server

try:
    import webview
except ImportError:
    webview = None


app = Flask(__name__)
CAPTURE_INTERVAL_SECONDS = 3

PAGE_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Image Archive</title>
    <style>
        * { box-sizing: border-box; }
        body { margin: 0; color: #222; background: #fff; font: 15px/1.5 Arial, Helvetica, sans-serif; }
        .page { width: min(100% - 32px, 1050px); margin: 0 auto; }
        header { padding: 24px 0 14px; border-bottom: 1px solid #999; }
        h1 { margin: 0; font-size: 28px; font-weight: normal; }
        main { padding: 20px 0 36px; }
        .notice { padding: 10px 12px; margin: 12px 0; border: 1px solid #aaa; background: #f7f7f7; }
        .notice.error { border-color: #a00; color: #800; }
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
        #captureStatus { margin: 16px 0; font-size: 18px; }
        .workspace {
            display: grid;
            grid-template-columns: minmax(0, 1.2fr) minmax(280px, 0.8fr);
            gap: 24px;
            margin-top: 28px;
        }
        .tableWrap { overflow-x: auto; }
        table { width: 100%; border-collapse: collapse; text-align: left; }
        th, td { padding: 8px; border-bottom: 1px solid #ccc; white-space: nowrap; }
        .chatMessages {
            display: flex;
            min-height: 240px;
            align-items: center;
            justify-content: center;
            padding: 16px;
            border: 1px solid #ccc;
            background: #f7f7f7;
            color: #555;
            text-align: center;
        }
        .chatForm { display: flex; gap: 8px; margin-top: 12px; }
        .chatForm input { min-width: 0; flex: 1; padding: 8px; font: inherit; }
        @media (max-width: 760px) {
            .workspace { grid-template-columns: 1fr; }
        }
        footer { padding: 12px 0; border-top: 1px solid #ccc; color: #666; font-size: 13px; }
    </style>
</head>
<body>
    <div class="page">
        <header>
            <h1>Image Archive</h1>
            <p>Local screenshot archive</p>
        </header>
        <main>
            <p class="notice">When enabled, this app captures the full screen every three seconds. Image pixels are discarded after capture; the timestamp, active app, device, system, and image dimensions appear in this session's local history. Nothing is saved to disk or uploaded. Start only on a device and screen you are authorized to capture.</p>
            <div class="consent">
                <input id="consent" type="checkbox">
                <label for="consent">I understand and want to start local screenshot capture and history.</label>
            </div>
            <div class="controls">
                <button id="captureButton" type="button" disabled>Start capture</button>
                <span id="captureStatus" role="status" aria-live="polite">Screenshots taken: 0. Capture is off.</span>
            </div>
            <p id="captureError" class="notice error" role="alert" hidden></p>
            <div class="workspace">
                <section class="archive" aria-labelledby="archiveHeading">
                    <h2 id="archiveHeading">Screenshot history</h2>
                    <p id="emptyMessage">No screenshots captured in this session.</p>
                    <div class="tableWrap">
                        <table id="captureTable" hidden>
                            <thead>
                                <tr>
                                    <th>Capture ID</th><th>Timestamp</th><th>Active app</th>
                                    <th>Device</th><th>System</th><th>Dimensions</th>
                                </tr>
                            </thead>
                            <tbody id="captureRows"></tbody>
                        </table>
                    </div>
                </section>
                <section aria-labelledby="chatHeading">
                    <h2 id="chatHeading">Claude chat</h2>
                    <div class="chatMessages" role="log" aria-live="polite">
                        <p>Claude chat is not connected in this build. No messages are sent.</p>
                    </div>
                    <form class="chatForm" aria-label="Claude chat">
                        <input type="text" aria-label="Message" placeholder="Chat unavailable" disabled>
                        <button type="button" disabled>Send</button>
                    </form>
                </section>
            </div>
        </main>
        <footer>Screenshot images are not saved or uploaded. History stays in memory and is cleared when the app closes. Stop capture at any time.</footer>
    </div>
    <script>
        const captureButton = document.getElementById('captureButton');
        const consent = document.getElementById('consent');
        const statusText = document.getElementById('captureStatus');
        const errorBox = document.getElementById('captureError');
        const rows = document.getElementById('captureRows');
        const table = document.getElementById('captureTable');
        const emptyMessage = document.getElementById('emptyMessage');
        let busy = false;
        let isActive = false;
        let lastSequence = 0;

        function addCapture(record) {
            const row = document.createElement('tr');
            const values = [
                record.capture_id,
                record.timestamp,
                record.application,
                record.device,
                record.system,
                `${record.width} × ${record.height}`
            ];
            for (const value of values) {
                const cell = document.createElement('td');
                cell.textContent = value;
                row.appendChild(cell);
            }
            rows.appendChild(row);
            table.hidden = false;
            emptyMessage.hidden = true;
            lastSequence = record.sequence;
        }

        async function refreshCaptures() {
            const response = await fetch(`/api/captures?after=${lastSequence}`);
            const data = await response.json();
            if (!response.ok) throw new Error(data.error || 'Could not load screenshot history.');
            for (const record of data.captures) addCapture(record);
        }

        async function refreshStatus() {
            const response = await fetch('/api/status');
            const data = await response.json();
            isActive = data.active;
            statusText.textContent = `Screenshots taken: ${data.count}. Capture is ${data.active ? 'on' : 'off'}.`;
            captureButton.textContent = data.active ? 'Stop capture' : 'Start capture';
            captureButton.disabled = busy || (!data.active && !consent.checked);
            if (data.error) {
                errorBox.textContent = data.error;
                errorBox.hidden = false;
            } else {
                errorBox.hidden = true;
            }
        }

        consent.addEventListener('change', () => {
            captureButton.disabled = busy || (!isActive && !consent.checked);
        });

        captureButton.addEventListener('click', async () => {
            if (busy) return;
            busy = true;
            captureButton.disabled = true;
            errorBox.hidden = true;
            const endpoint = isActive ? '/api/stop' : '/api/start';
            try {
                const response = await fetch(endpoint, {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({consent: consent.checked})
                });
                const data = await response.json();
                if (!response.ok) throw new Error(data.error || 'Could not change capture state.');
            } catch (error) {
                errorBox.textContent = error.message;
                errorBox.hidden = false;
            } finally {
                busy = false;
                await refreshStatus();
                await refreshCaptures();
            }
        });

        refreshStatus();
        refreshCaptures();
        window.setInterval(() => {
            refreshStatus().catch((error) => {
                errorBox.textContent = error.message;
                errorBox.hidden = false;
            });
            refreshCaptures().catch((error) => {
                errorBox.textContent = error.message;
                errorBox.hidden = false;
            });
        }, 1000);
    </script>
</body>
</html>
"""

def _capture_screenshot():
    with mss.mss() as screen:
        screenshot = screen.grab(screen.monitors[0])
    return screenshot.size


def _active_application():
    if platform.system() == "Darwin":
        from AppKit import NSWorkspace

        running_app = NSWorkspace.sharedWorkspace().frontmostApplication()
        return running_app.localizedName() if running_app else "Unknown"
    return "Unknown"


class CaptureManager:
    def __init__(self):
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._thread = None
        self._error = None
        self._count = 0
        self._captures = []

    def status(self):
        with self._lock:
            alive = self._thread is not None and self._thread.is_alive()
            return {
                "active": alive and not self._stop_event.is_set(),
                "count": self._count,
                "error": self._error,
            }

    def captures_after(self, sequence):
        with self._lock:
            return [
                capture for capture in self._captures
                if capture["sequence"] > sequence
            ]

    def start(self, values):
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                raise RuntimeError("Capture is already running.")
            if not isinstance(values, dict) or values.get("consent") is not True:
                raise ValueError("Accept the local screenshot notice before starting.")
            self._error = None
            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._capture_loop,
                daemon=True,
                name="local-screen-capture",
            )
            self._thread.start()

    def stop(self):
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                self._stop_event.set()

    def _capture_loop(self):
        try:
            while not self._stop_event.is_set():
                started = time.monotonic()
                width, height = _capture_screenshot()
                application = _active_application()
                timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
                device = platform.node() or "Unknown"
                operating_system = platform.system() or "Unknown"
                with self._lock:
                    self._count += 1
                    self._captures.append(
                        {
                            "sequence": self._count,
                            "capture_id": str(uuid.uuid4()),
                            "timestamp": timestamp,
                            "application": application,
                            "device": device,
                            "system": operating_system,
                            "width": width,
                            "height": height,
                        }
                    )
                self._stop_event.wait(
                    max(0, CAPTURE_INTERVAL_SECONDS - (time.monotonic() - started))
                )
        except Exception:
            app.logger.exception("Screenshot capture failed")
            with self._lock:
                self._error = (
                "Capture stopped because a screenshot or its metadata could "
                "not be collected. Check Screen Recording permission and the app log."
                )
            self._stop_event.set()


capture_manager = CaptureManager()


@app.route("/")
def home():
    return render_template_string(PAGE_TEMPLATE)

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
        app.logger.exception("Could not start screenshot capture")
        return jsonify({"error": "Could not start screenshot capture."}), 500
    return jsonify({"active": True}), 200


@app.route("/api/stop", methods=["POST"])
def stop_capture():
    capture_manager.stop()
    return jsonify({"active": False}), 200


@app.route("/api/status")
def capture_status():
    return jsonify(capture_manager.status())


@app.route("/api/captures")
def recent_captures():
    try:
        after = int(request.args.get("after", "0"))
        if after < 0:
            raise ValueError
    except ValueError:
        return jsonify({"error": "Capture cursor must be a non-negative integer."}), 400
    return jsonify({"captures": capture_manager.captures_after(after)}), 200


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
