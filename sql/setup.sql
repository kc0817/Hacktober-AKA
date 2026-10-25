-- One-time Snowflake setup. Run in a worksheet as a role that can create databases.

CREATE DATABASE IF NOT EXISTS SCREEN_COACH;
USE DATABASE SCREEN_COACH;
USE SCHEMA PUBLIC;

-- PNG files live here. SNOWFLAKE_SSE lets us hand out presigned URLs later if we want.
CREATE STAGE IF NOT EXISTS SCREENSHOTS
  ENCRYPTION = (TYPE = 'SNOWFLAKE_SSE')
  DIRECTORY = (ENABLE = TRUE);

-- One row per screenshot; the image itself is the file at STAGE_PATH.
CREATE TABLE IF NOT EXISTS SCREENSHOT_LOG (
    ID            STRING        DEFAULT UUID_STRING(),
    SESSION_ID    STRING        NOT NULL,   -- one per app launch
    USER_NAME     STRING,
    CAPTURED_AT   TIMESTAMP_TZ  NOT NULL,
    WINDOW_TITLE  STRING,                   -- e.g. "MyBoard.PcbDoc - Altium Designer"
    STAGE_PATH    STRING        NOT NULL,   -- path inside @SCREENSHOTS
    WIDTH         INT,
    HEIGHT        INT
);

-- Optional: keep Q&A for later analysis / demo.
CREATE TABLE IF NOT EXISTS QUESTION_LOG (
    ID            STRING        DEFAULT UUID_STRING(),
    SESSION_ID    STRING        NOT NULL,
    ASKED_AT      TIMESTAMP_TZ  NOT NULL,
    QUESTION      STRING,
    ANSWER        STRING,
    SCREENSHOT_IDS ARRAY
);
