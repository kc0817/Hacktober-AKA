import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Config:
    sf_account: str = os.environ.get("SNOWFLAKE_ACCOUNT", "")
    sf_user: str = os.environ.get("SNOWFLAKE_USER", "")
    sf_password: str = os.environ.get("SNOWFLAKE_PASSWORD", "")
    sf_warehouse: str = os.environ.get("SNOWFLAKE_WAREHOUSE", "COMPUTE_WH")
    sf_database: str = os.environ.get("SNOWFLAKE_DATABASE", "SCREEN_COACH")
    sf_schema: str = os.environ.get("SNOWFLAKE_SCHEMA", "PUBLIC")
    sf_role: str = os.environ.get("SNOWFLAKE_ROLE", "")
    sf_stage: str = "SCREENSHOTS"

    capture_interval_sec: int = int(os.environ.get("CAPTURE_INTERVAL_SEC", "15"))
    recent_image_count: int = int(os.environ.get("RECENT_IMAGE_COUNT", "3"))
    # Cap on screenshots kept in the database (all users and sessions); the oldest are deleted first.
    max_screenshots: int = int(os.environ.get("MAX_SCREENSHOTS", "500"))
    cleanup_every_uploads: int = 10
    # Claude downsizes anything bigger than this anyway, so don't store/upload more.
    max_image_edge: int = 1568

    model: str = "claude-sonnet-5-5"
    effort: str = "medium"


CONFIG = Config()
