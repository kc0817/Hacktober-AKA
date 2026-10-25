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
    <title>Snaptcha ©</title>
    <style>
        :root {
            color-scheme: light;
            --cyan-50: #effbfc;
            --cyan-100: #d9f5f7;
            --cyan-200: #b8e9ed;
            --cyan-500: #10a8ba;
            --cyan-700: #08798a;
            --cyan-800: #075d6a;
            --ink: #17343a;
            --muted: #527078;
            --white: #fff;
            --danger: #a32727;
        }
        * { box-sizing: border-box; }
        body {
            margin: 0;
            color: var(--ink);
            background: linear-gradient(180deg, var(--cyan-50), var(--white) 360px);
            font: 15px/1.5 Arial, Helvetica, sans-serif;
        }
        .page { width: min(100% - 32px, 1050px); margin: 0 auto; }
        header {
            display: flex;
            align-items: baseline;
            justify-content: space-between;
            gap: 16px;
            padding: 24px 0 14px;
            border-bottom: 2px solid var(--cyan-200);
        }
        header p { margin: 0; color: var(--muted); }
        h1 { margin: 0; color: var(--cyan-800); font-size: 30px; letter-spacing: -0.04em; }
        .copyright { color: var(--cyan-500); font-size: 0.7em; vertical-align: top; }
        main { padding: 20px 0 36px; }
        .notice {
            padding: 12px 14px;
            margin: 12px 0;
            border: 1px solid var(--cyan-200);
            border-left: 4px solid var(--cyan-500);
            border-radius: 8px;
            background: var(--cyan-50);
        }
        .notice.error { border-color: #e6b2b2; color: var(--danger); background: #fff5f5; }
        button {
            padding: 8px 14px;
            border: 1px solid var(--cyan-700);
            border-radius: 7px;
            background: var(--cyan-700);
            color: var(--white);
            font: inherit;
            cursor: pointer;
            transition: background-color 120ms ease, border-color 120ms ease;
        }
        button:hover { border-color: var(--cyan-800); background: var(--cyan-800); }
        button:disabled { border-color: var(--cyan-200); background: var(--cyan-100); color: var(--muted); cursor: not-allowed; }
        input { accent-color: var(--cyan-700); }
        input[type="number"], .chatForm input {
            border: 1px solid var(--cyan-200);
            border-radius: 6px;
            color: var(--ink);
            background: var(--white);
        }
        input:focus-visible, button:focus-visible {
            outline: 3px solid var(--cyan-500);
            outline-offset: 2px;
        }
        .consent { display: flex; gap: 8px; align-items: flex-start; margin: 18px 0; }
        .consent input { margin-top: 5px; }
        .consent label { margin: 0; }
        .intervalControl { display: flex; gap: 8px; align-items: center; margin: 18px 0; }
        .intervalControl input { width: 90px; padding: 6px; font: inherit; }
        .controls { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
        #captureStatus { margin: 16px 0; font-size: 18px; }
        .workspace {
            display: grid;
            grid-template-columns: minmax(0, 1.2fr) minmax(280px, 0.8fr);
            gap: 24px;
            margin-top: 28px;
        }
        .workspace > section {
            min-width: 0;
            padding: 20px;
            border: 1px solid var(--cyan-100);
            border-radius: 12px;
            background: var(--white);
            box-shadow: 0 8px 24px rgb(7 93 106 / 6%);
        }
        .workspace h2 { margin-top: 0; color: var(--cyan-800); font-size: 20px; }
        .archive { min-width: 0; }
        .tableWrap {
            max-height: min(42vh, 380px);
            overflow: auto;
            border: 1px solid var(--cyan-100);
            border-radius: 8px;
            scrollbar-color: var(--cyan-200) var(--cyan-50);
        }
        table { width: 100%; border-collapse: collapse; text-align: left; }
        th, td { padding: 9px; border-bottom: 1px solid var(--cyan-100); white-space: nowrap; }
        th { position: sticky; top: 0; background: var(--cyan-50); }
        th button {
            padding: 0;
            border: 0;
            border-radius: 0;
            background: transparent;
            color: var(--cyan-800);
            font: inherit;
            font-weight: bold;
            text-align: left;
        }
        th button:hover { text-decoration: underline; background: transparent; color: var(--cyan-700); }
        tbody tr:nth-child(even) { background: #fbfeff; }
        tbody tr:hover { background: var(--cyan-50); }
        .activitySummary {
            margin: 0 0 14px;
            padding: 12px;
            border: 1px solid var(--cyan-100);
            border-radius: 8px;
            background: var(--cyan-50);
        }
        .activitySummary h3 { margin: 0 0 6px; font-size: 16px; }
        .activitySummary p { margin: 4px 0; }
        #appBreakdown { margin: 8px 0 0; padding-left: 22px; }
        #appBreakdown li { margin: 4px 0; }
        .activityChart { margin-bottom: 24px; }
        .chartScroll { overflow: hidden; border: 1px solid var(--cyan-100); border-radius: 8px; background: var(--white); }
        #appFrequencyChart { display: block; width: 100%; height: auto; }
        #appFrequencyChart text { fill: var(--muted); font: 12px Arial, Helvetica, sans-serif; }
        #appFrequencyChart .gridline { stroke: var(--cyan-100); stroke-width: 1; }
        #appFrequencyChart .axis { stroke: var(--cyan-700); stroke-width: 1; }
        #appFrequencyChart .dataPoint { fill: var(--cyan-500); stroke: var(--white); stroke-width: 2; cursor: pointer; }
        #appFrequencyChart .dataPoint:hover,
        #appFrequencyChart .dataPoint:focus { fill: var(--cyan-800); stroke: var(--cyan-200); outline: none; }
        .chartDetails { min-height: 58px; margin: 8px 0 0; padding: 10px; border: 1px solid var(--cyan-100); border-radius: 8px; background: var(--cyan-50); }
        .chatMessages {
            display: flex;
            min-height: 240px;
            align-items: center;
            justify-content: center;
            padding: 16px;
            border: 1px solid var(--cyan-100);
            border-radius: 8px;
            background: var(--cyan-50);
            color: var(--muted);
            text-align: center;
        }
        .chatForm { display: flex; gap: 8px; margin-top: 12px; }
        .chatForm input { min-width: 0; flex: 1; padding: 8px; font: inherit; }
        @media (max-width: 760px) {
            .workspace { grid-template-columns: 1fr; }
            .workspace > section { padding: 16px; }
        }
        @media (max-width: 480px) {
            header { align-items: flex-start; flex-direction: column; gap: 2px; }
            .intervalControl { align-items: flex-start; flex-direction: column; }
        }
        footer { padding: 12px 0; border-top: 1px solid var(--cyan-200); color: var(--muted); font-size: 13px; }
    </style>
</head>
<body>
    <div class="page">
        <header>
            <h1>Snaptcha <span class="copyright">©</span></h1>
            <p>Local screenshot archive</p>
        </header>
        <main>
            <p class="notice">When enabled, this app captures the full screen at your chosen interval. Image pixels are discarded after capture; the timestamp, active app, device, system, and image dimensions appear in this session's local history. Nothing is saved to disk or uploaded. Start only on a device and screen you are authorized to capture.</p>
            <div class="consent">
                <input id="consent" type="checkbox">
                <label for="consent">I understand and want to start local screenshot capture and history.</label>
            </div>
            <div class="intervalControl">
                <label for="captureInterval">Capture interval (seconds)</label>
                <input id="captureInterval" type="number" min="1" max="3600" step="1" value="3">
                <span>Choose 1–3600 seconds. Default: 3.</span>
            </div>
            <div class="controls">
                <button id="captureButton" type="button" disabled>Start capture</button>
                <span id="captureStatus" role="status" aria-live="polite">Screenshots taken: 0. Capture is off.</span>
            </div>
            <p id="captureError" class="notice error" role="alert" hidden></p>
            <div class="workspace">
                <section class="archive" aria-labelledby="archiveHeading">
                    <h2 id="archiveHeading">Screenshot history</h2>
                    <div class="activitySummary" aria-live="polite">
                        <h3>Activity summary</h3>
                        <p id="activitySummary">No activity recorded yet.</p>
                        <ul id="appBreakdown"></ul>
                        <p>Based only on capture timestamps and active app labels; screenshot image content is not analyzed.</p>
                    </div>
                    <p id="emptyMessage">No screenshots captured in this session.</p>
                    <div class="tableWrap">
                        <table id="captureTable" hidden>
                            <thead>
                                <tr>
                                    <th><button type="button" data-sort="capture_id">Capture ID</button></th>
                                    <th aria-sort="descending"><button type="button" data-sort="timestamp">Timestamp</button></th>
                                    <th><button type="button" data-sort="application">Active app</button></th>
                                    <th><button type="button" data-sort="device">Device</button></th>
                                    <th><button type="button" data-sort="system">System</button></th>
                                    <th><button type="button" data-sort="dimensions">Dimensions</button></th>
                                </tr>
                            </thead>
                            <tbody id="captureRows"></tbody>
                        </table>
                    </div>
                </section>
                <section aria-labelledby="chatHeading">
                    <div class="activityChart" aria-labelledby="chartHeading">
                        <h2 id="chartHeading">Capture frequency by app</h2>
                        <p>Each point represents an app; higher points mean more captures.</p>
                        <div class="chartScroll">
                            <svg id="appFrequencyChart" height="260" role="img" aria-label="Screenshot capture counts for each active app" hidden></svg>
                        </div>
                        <p id="chartEmptyMessage">The chart will appear after the first capture.</p>
                        <p id="chartDetails" class="chartDetails" role="status" aria-live="polite">Hover over a point or focus it with the keyboard to see app activity details.</p>
                    </div>
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
        const intervalInput = document.getElementById('captureInterval');
        const statusText = document.getElementById('captureStatus');
        const errorBox = document.getElementById('captureError');
        const rows = document.getElementById('captureRows');
        const table = document.getElementById('captureTable');
        const emptyMessage = document.getElementById('emptyMessage');
        const activitySummary = document.getElementById('activitySummary');
        const appBreakdown = document.getElementById('appBreakdown');
        const appFrequencyChart = document.getElementById('appFrequencyChart');
        const chartEmptyMessage = document.getElementById('chartEmptyMessage');
        const chartDetails = document.getElementById('chartDetails');
        let busy = false;
        let isActive = false;
        let lastSequence = 0;
        let captures = [];
        let sortKey = 'timestamp';
        let sortDirection = -1;
        let currentAppStats = [];

        function sortValue(record, key) {
            if (key === 'dimensions') return [record.width, record.height];
            return record[key];
        }

        function renderCaptures() {
            const sorted = [...captures].sort((left, right) => {
                const leftValue = sortValue(left, sortKey);
                const rightValue = sortValue(right, sortKey);
                if (Array.isArray(leftValue)) {
                    return (leftValue[0] - rightValue[0] || leftValue[1] - rightValue[1]) * sortDirection;
                }
                if (sortKey === 'timestamp') {
                    return (Date.parse(leftValue) - Date.parse(rightValue)) * sortDirection;
                }
                return String(leftValue).localeCompare(String(rightValue), undefined, {
                    numeric: true,
                    sensitivity: 'base'
                }) * sortDirection;
            });
            rows.replaceChildren();
            for (const record of sorted) {
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
            }
            table.hidden = captures.length === 0;
            emptyMessage.hidden = captures.length > 0;
            renderActivitySummary();
        }

        function renderActivitySummary() {
            if (captures.length === 0) {
                activitySummary.textContent = 'No activity recorded yet.';
                appBreakdown.replaceChildren();
                renderFrequencyChart([]);
                return;
            }
            const apps = new Map();
            for (const record of captures) {
                const name = record.application || 'Unknown';
                if (!apps.has(name)) {
                    apps.set(name, {name, records: []});
                }
                apps.get(name).records.push(record);
            }
            const appStats = [...apps.values()].map((app) => {
                const timestamps = app.records.map(record => Date.parse(record.timestamp)).sort((a, b) => a - b);
                return {
                    ...app,
                    count: app.records.length,
                    first: timestamps[0],
                    last: timestamps[timestamps.length - 1]
                };
            }).sort((left, right) => right.count - left.count || left.name.localeCompare(right.name));
            const timestamps = captures.map(record => Date.parse(record.timestamp)).sort((a, b) => a - b);
            const gaps = timestamps.slice(1).map((timestamp, index) => timestamp - timestamps[index]);
            const averageGap = gaps.length
                ? `${(gaps.reduce((sum, gap) => sum + gap, 0) / gaps.length / 1000).toFixed(1)} seconds`
                : 'not available yet';
            const topApp = appStats[0];
            activitySummary.textContent =
                `${captures.length} captures across ${appStats.length} apps. ` +
                `Most frequent: ${topApp.name} (${topApp.count} ` +
                `${topApp.count === 1 ? 'capture' : 'captures'}, ` +
                `${(topApp.count / captures.length * 100).toFixed(1)}%). ` +
                `Observed from ${new Date(timestamps[0]).toLocaleString()} to ` +
                `${new Date(timestamps[timestamps.length - 1]).toLocaleString()}; ` +
                `average gap between captures: ${averageGap}.`;
            appBreakdown.replaceChildren();
            for (const app of appStats) {
                const item = document.createElement('li');
                item.textContent =
                    `${app.name}: ${app.count} ${app.count === 1 ? 'capture' : 'captures'} ` +
                    `(${(app.count / captures.length * 100).toFixed(1)}%); ` +
                    `first ${new Date(app.first).toLocaleString()}, last ${new Date(app.last).toLocaleString()}.`;
                appBreakdown.appendChild(item);
            }
            renderFrequencyChart(appStats);
        }

        function createSvgElement(name, attributes) {
            const element = document.createElementNS('http://www.w3.org/2000/svg', name);
            for (const [key, value] of Object.entries(attributes)) {
                element.setAttribute(key, value);
            }
            return element;
        }

        function renderFrequencyChart(appStats) {
            currentAppStats = appStats;
            appFrequencyChart.replaceChildren();
            appFrequencyChart.hidden = appStats.length === 0;
            chartEmptyMessage.hidden = appStats.length > 0;
            if (appStats.length === 0) {
                chartDetails.textContent =
                    'Hover over a point or focus it with the keyboard to see app activity details.';
                return;
            }

            const width = Math.max(320, appFrequencyChart.parentElement.clientWidth);
            const height = 260;
            const left = 52;
            const right = width - 24;
            const top = 22;
            const bottom = 190;
            const maxCount = Math.max(...appStats.map(app => app.count));
            const tickCount = Math.min(4, maxCount);
            appFrequencyChart.setAttribute('width', width);
            appFrequencyChart.setAttribute('viewBox', `0 0 ${width} ${height}`);

            for (let tick = 0; tick <= tickCount; tick++) {
                const value = Math.ceil(maxCount * tick / tickCount);
                const y = bottom - (value / maxCount) * (bottom - top);
                appFrequencyChart.appendChild(createSvgElement('line', {
                    x1: left, y1: y, x2: right, y2: y, class: 'gridline'
                }));
                const label = createSvgElement('text', {
                    x: left - 10, y: y + 4, 'text-anchor': 'end'
                });
                label.textContent = String(value);
                appFrequencyChart.appendChild(label);
            }
            appFrequencyChart.appendChild(createSvgElement('line', {
                x1: left, y1: top, x2: left, y2: bottom, class: 'axis'
            }));
            appFrequencyChart.appendChild(createSvgElement('line', {
                x1: left, y1: bottom, x2: right, y2: bottom, class: 'axis'
            }));
            const axisLabel = createSvgElement('text', {
                x: 16, y: (top + bottom) / 2, transform: `rotate(-90 16 ${(top + bottom) / 2})`,
                'text-anchor': 'middle'
            });
            axisLabel.textContent = 'Captures';
            appFrequencyChart.appendChild(axisLabel);

            appStats.forEach((app, index) => {
                const x = appStats.length === 1
                    ? (left + right) / 2
                    : left + 18 + index * ((right - left - 36) / (appStats.length - 1));
                const pointSpacing = appStats.length > 1
                    ? (right - left - 36) / (appStats.length - 1)
                    : right - left;
                const y = bottom - (app.count / maxCount) * (bottom - top);
                const percentage = (app.count / captures.length * 100).toFixed(1);
                const detail =
                    `${app.name}: ${app.count} captures (${percentage}% of the session). ` +
                    `First captured ${new Date(app.first).toLocaleString()}; ` +
                    `last captured ${new Date(app.last).toLocaleString()}.`;
                const point = createSvgElement('circle', {
                    cx: x, cy: y, r: 7, class: 'dataPoint', tabindex: '0', role: 'img',
                    'aria-label': detail
                });
                const title = createSvgElement('title', {});
                title.textContent = detail;
                point.appendChild(title);
                point.addEventListener('pointerenter', () => {
                    chartDetails.textContent = detail;
                });
                point.addEventListener('focus', () => {
                    chartDetails.textContent = detail;
                });
                point.addEventListener('pointerleave', () => {
                    chartDetails.textContent =
                        'Hover over a point or focus it with the keyboard to see app activity details.';
                });
                point.addEventListener('blur', () => {
                    chartDetails.textContent =
                        'Hover over a point or focus it with the keyboard to see app activity details.';
                });
                appFrequencyChart.appendChild(point);
                const countLabel = createSvgElement('text', {
                    x, y: y - 12, 'text-anchor': 'middle'
                });
                countLabel.textContent = String(app.count);
                appFrequencyChart.appendChild(countLabel);
                const label = createSvgElement('text', {
                    x, y: bottom + 20, 'text-anchor': 'middle'
                });
                const maxLabelLength = Math.max(3, Math.floor(pointSpacing / 7));
                label.textContent = app.name.length > maxLabelLength
                    ? `${app.name.slice(0, maxLabelLength - 1)}…`
                    : app.name;
                appFrequencyChart.appendChild(label);
            });
        }

        window.addEventListener('resize', () => {
            if (currentAppStats.length) renderFrequencyChart(currentAppStats);
        });

        async function refreshCaptures() {
            const response = await fetch(`/api/captures?after=${lastSequence}`);
            const data = await response.json();
            if (!response.ok) throw new Error(data.error || 'Could not load screenshot history.');
            if (data.captures.length) {
                captures.push(...data.captures);
                lastSequence = Math.max(lastSequence, ...data.captures.map(record => record.sequence));
                renderCaptures();
            }
        }

        document.querySelectorAll('[data-sort]').forEach((button) => {
            button.addEventListener('click', () => {
                if (sortKey === button.dataset.sort) {
                    sortDirection *= -1;
                } else {
                    sortKey = button.dataset.sort;
                    sortDirection = 1;
                }
                document.querySelectorAll('thead th').forEach((header) => {
                    header.removeAttribute('aria-sort');
                });
                button.closest('th').setAttribute(
                    'aria-sort',
                    sortDirection === 1 ? 'ascending' : 'descending'
                );
                renderCaptures();
            });
        });

        async function refreshStatus() {
            const response = await fetch('/api/status');
            const data = await response.json();
            isActive = data.active;
            statusText.textContent = `Screenshots taken: ${data.count}. Capture is ${data.active ? 'on' : 'off'}.`;
            captureButton.textContent = data.active ? 'Stop capture' : 'Start capture';
            captureButton.disabled = busy || (!data.active && !consent.checked);
            intervalInput.disabled = data.active || busy;
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
                    body: JSON.stringify({
                        consent: consent.checked,
                        interval_seconds: Number(intervalInput.value)
                    })
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
            interval_seconds = values.get("interval_seconds")
            if (
                isinstance(interval_seconds, bool)
                or not isinstance(interval_seconds, int)
                or not 1 <= interval_seconds <= 3600
            ):
                raise ValueError("Capture interval must be a whole number from 1 to 3600 seconds.")
            self._error = None
            self._interval_seconds = interval_seconds
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
                    max(0, self._interval_seconds - (time.monotonic() - started))
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
