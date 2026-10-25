"""Entry point: chat window + background screenshot loop."""
import html
import queue
import sys
import threading
import uuid

from PySide6.QtCore import QObject, Qt, QThread, QTimer, Signal
from PySide6.QtWidgets import (
    QApplication, QHBoxLayout, QLabel, QLineEdit, QPushButton, QTextBrowser, QVBoxLayout, QWidget,
)

from .assistant import Assistant
from .capture import WindowCapturer
from .config import CONFIG
from .storage import LocalStore, SnowflakeStore


class Uploader(threading.Thread):
    """Drains captured screenshots to Snowflake so the UI never blocks on network I/O."""

    def __init__(self, store: SnowflakeStore):
        super().__init__(daemon=True)
        self.store = store
        self.queue: queue.Queue = queue.Queue(maxsize=20)

    def run(self):
        while True:
            shot = self.queue.get()
            try:
                self.store.upload(shot)
            except Exception as e:  # keep capturing even if one upload fails
                print(f"upload failed: {e}", file=sys.stderr)


class AskWorker(QObject):
    finished = Signal(str)

    def __init__(self, assistant: Assistant, store: SnowflakeStore, question: str):
        super().__init__()
        self.assistant, self.store, self.question = assistant, store, question

    def run(self):
        try:
            shots = self.store.recent(CONFIG.recent_image_count)
            answer = self.assistant.ask(self.question, shots)
            self.store.log_question(self.question, answer, [s.id for s in shots])
        except Exception as e:
            answer = f"Error: {e}"
        self.finished.emit(answer)


class MainWindow(QWidget):
    def __init__(self, store: SnowflakeStore, uploader: Uploader):
        super().__init__()
        self.store, self.uploader = store, uploader
        self.assistant = Assistant()
        self.capturer = WindowCapturer()
        self.paused = False

        self.setWindowTitle("Screen Coach")
        self.setWindowFlag(Qt.WindowStaysOnTopHint)
        self.resize(420, 560)

        self.status = QLabel()
        self.pause_btn = QPushButton("Pause capture")
        self.pause_btn.clicked.connect(self.toggle_pause)
        new_btn = QPushButton("New chat")
        new_btn.clicked.connect(self.new_chat)

        self.transcript = QTextBrowser()
        self.input = QLineEdit(placeholderText="Ask about what you're doing…")
        self.input.returnPressed.connect(self.send)
        self.send_btn = QPushButton("Ask")
        self.send_btn.clicked.connect(self.send)

        top = QHBoxLayout()
        top.addWidget(self.status, 1)
        top.addWidget(self.pause_btn)
        top.addWidget(new_btn)
        bottom = QHBoxLayout()
        bottom.addWidget(self.input, 1)
        bottom.addWidget(self.send_btn)
        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addWidget(self.transcript, 1)
        layout.addLayout(bottom)

        self.timer = QTimer(self, interval=CONFIG.capture_interval_sec * 1000, timeout=self.tick)
        self.timer.start()
        self._update_status()

    def tick(self):
        if self.paused:
            return
        shot = self.capturer.capture()
        if shot is None:
            return
        try:
            self.uploader.queue.put_nowait(shot)
            self.status.setText(f"Captured {shot.window_title[:40] or 'screen'}")
        except queue.Full:
            self.status.setText("Upload backlog — skipping frame")

    def toggle_pause(self):
        self.paused = not self.paused
        self.pause_btn.setText("Resume capture" if self.paused else "Pause capture")
        self._update_status()

    def new_chat(self):
        self.assistant.reset()
        self.transcript.clear()

    def _update_status(self):
        self.status.setText("Capture paused" if self.paused else f"Capturing every {CONFIG.capture_interval_sec}s")

    def send(self):
        question = self.input.text().strip()
        if not question:
            return
        self.input.clear()
        self.transcript.append(f"<p><b>You:</b> {html.escape(question)}</p>")
        self.send_btn.setEnabled(False)
        self.input.setEnabled(False)
        self.transcript.append("<p><i>Looking at your screen…</i></p>")

        self._thread = QThread()
        self._worker = AskWorker(self.assistant, self.store, question)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self.show_answer)
        self._worker.finished.connect(self._thread.quit)
        self._thread.start()

    def show_answer(self, answer: str):
        body = html.escape(answer).replace("\n", "<br>")
        self.transcript.append(f"<p><b>Coach:</b><br>{body}</p>")
        self.send_btn.setEnabled(True)
        self.input.setEnabled(True)
        self.input.setFocus()


def main():
    app = QApplication(sys.argv)
    session_id = uuid.uuid4().hex
    store = LocalStore(session_id) if "--local" in sys.argv else SnowflakeStore(session_id)
    uploader = Uploader(store)
    uploader.start()
    win = MainWindow(store, uploader)
    win.show()
    code = app.exec()
    store.close()
    sys.exit(code)


if __name__ == "__main__":
    main()
