"""Trim the Snowflake screenshot store down to the newest MAX_SCREENSHOTS (files and rows).

The app already does this every few uploads; run this by hand to clean up right away or with a different limit.

Usage (from the project root):
    python -m scripts.cleanup               # keep MAX_SCREENSHOTS from .env
    python -m scripts.cleanup --max 100     # keep the newest 100
    python -m scripts.cleanup --dry-run     # only report how many would be deleted
"""
import argparse
import sys

from app.config import CONFIG
from app.storage import SnowflakeStore


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max", type=int, default=CONFIG.max_screenshots,
                        help=f"screenshots to keep (default MAX_SCREENSHOTS={CONFIG.max_screenshots})")
    parser.add_argument("--dry-run", action="store_true", help="report without deleting")
    args = parser.parse_args()

    keep = max(args.max, CONFIG.recent_image_count)
    store = SnowflakeStore(session_id="cleanup")
    try:
        count = store.cleanup(keep, dry_run=args.dry_run)
    finally:
        store.close()

    verb = "Would delete" if args.dry_run else "Deleted"
    print(f"{verb} {count} screenshot(s); keeping the newest {keep}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
