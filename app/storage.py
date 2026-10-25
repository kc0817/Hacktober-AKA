"""Snowflake: upload screenshots to a stage, log metadata, fetch the most recent ones."""
import getpass
import json
import tempfile
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .capture import Screenshot
from .config import CONFIG


@dataclass
class StoredScreenshot:
    id: str
    captured_at: datetime
    window_title: str
    png_bytes: bytes


class SnowflakeStore:
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.user_name = getpass.getuser()
        # The connector isn't safe to share across threads mid-query.
        self._lock = threading.Lock()
        import snowflake.connector
        self._conn = snowflake.connector.connect(
            account=CONFIG.sf_account,
            user=CONFIG.sf_user,
            password=CONFIG.sf_password,
            warehouse=CONFIG.sf_warehouse,
            database=CONFIG.sf_database,
            schema=CONFIG.sf_schema,
            role=CONFIG.sf_role or None,
        )

    def upload(self, shot: Screenshot) -> None:
        stamp = shot.captured_at.strftime("%Y%m%dT%H%M%S%f")
        filename = f"{stamp}.png"
        stage_dir = f"{self.session_id}"

        with tempfile.TemporaryDirectory() as tmp:
            local = Path(tmp) / filename
            local.write_bytes(shot.png_bytes)
            with self._lock, self._conn.cursor() as cur:
                cur.execute(
                    f"PUT 'file://{local.as_posix()}' @{CONFIG.sf_stage}/{stage_dir} "
                    "AUTO_COMPRESS=FALSE OVERWRITE=TRUE"
                )
                cur.execute(
                    "INSERT INTO SCREENSHOT_LOG "
                    "(SESSION_ID, USER_NAME, CAPTURED_AT, WINDOW_TITLE, STAGE_PATH, WIDTH, HEIGHT) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                    (self.session_id, self.user_name, shot.captured_at, shot.window_title,
                     f"{stage_dir}/{filename}", shot.width, shot.height),
                )

    def recent(self, n: int) -> list[StoredScreenshot]:
        """Most recent n screenshots for this session, oldest first."""
        with self._lock, self._conn.cursor() as cur:
            cur.execute(
                "SELECT ID, CAPTURED_AT, WINDOW_TITLE, STAGE_PATH FROM SCREENSHOT_LOG "
                "WHERE SESSION_ID = %s ORDER BY CAPTURED_AT DESC LIMIT %s",
                (self.session_id, n),
            )
            rows = cur.fetchall()

            shots = []
            with tempfile.TemporaryDirectory() as tmp:
                for row_id, captured_at, title, stage_path in rows:
                    cur.execute(f"GET @{CONFIG.sf_stage}/{stage_path} 'file://{Path(tmp).as_posix()}/'")
                    png = (Path(tmp) / Path(stage_path).name).read_bytes()
                    shots.append(StoredScreenshot(row_id, captured_at, title or "", png))
        return list(reversed(shots))

    def log_question(self, question: str, answer: str, screenshot_ids: list[str]) -> None:
        with self._lock, self._conn.cursor() as cur:
            cur.execute(
                "INSERT INTO QUESTION_LOG (SESSION_ID, ASKED_AT, QUESTION, ANSWER, SCREENSHOT_IDS) "
                "SELECT %s, CURRENT_TIMESTAMP(), %s, %s, PARSE_JSON(%s)",
                (self.session_id, question, answer, json.dumps(screenshot_ids)),
            )

    def close(self) -> None:
        self._conn.close()


class LocalStore:
    """In-memory stand-in for SnowflakeStore (`--local`), for trying the app without Snowflake."""

    def __init__(self, session_id: str, keep: int = 50):
        self.session_id = session_id
        self._lock = threading.Lock()
        self._shots: list[StoredScreenshot] = []
        self._keep = keep

    def upload(self, shot: Screenshot) -> None:
        with self._lock:
            self._shots.append(StoredScreenshot(uuid.uuid4().hex, shot.captured_at, shot.window_title, shot.png_bytes))
            del self._shots[:-self._keep]

    def recent(self, n: int) -> list[StoredScreenshot]:
        with self._lock:
            return self._shots[-n:]

    def log_question(self, question: str, answer: str, screenshot_ids: list[str]) -> None:
        pass

    def close(self) -> None:
        pass

