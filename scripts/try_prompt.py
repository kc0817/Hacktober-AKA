"""Run saved screenshot + question test cases through the real Assistant, without the UI or Snowflake.

Usage (from the project root):
    python -m scripts.try_prompt                 # every case in test_cases/
    python -m scripts.try_prompt --case NAME     # one case
    python -m scripts.try_prompt --images 1      # only send each case's newest N screenshots

Each case is a folder in test_cases/ — see test_cases/README.md. Results are printed and saved to results/.
"""
import argparse
import io
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from PIL import Image

from app.assistant import Assistant
from app.config import CONFIG
from app.storage import StoredScreenshot

ROOT = Path(__file__).resolve().parent.parent
CASES_DIR = ROOT / "test_cases"
RESULTS_DIR = ROOT / "results"
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}

# claude-sonnet-5-5, USD per million tokens
PRICE_INPUT, PRICE_OUTPUT = 2.00, 10.00
PRICE_CACHE_WRITE, PRICE_CACHE_READ = 2.50, 0.20


def load_case(case_dir: Path, max_images: int) -> tuple[str, list[StoredScreenshot], str]:
    question = (case_dir / "question.txt").read_text(encoding="utf-8").strip()
    title_file = case_dir / "title.txt"
    title = title_file.read_text(encoding="utf-8").strip() if title_file.exists() else ""
    expect_file = case_dir / "expect.txt"
    expect = expect_file.read_text(encoding="utf-8").strip() if expect_file.exists() else ""

    images = sorted(p for p in case_dir.iterdir() if p.suffix.lower() in IMAGE_EXTS)[-max_images:]
    # Pretend they were captured CAPTURE_INTERVAL_SEC apart, ending now, like the real app.
    now = datetime.now(timezone.utc)
    shots = []
    for i, path in enumerate(images):
        img = Image.open(path).convert("RGB")
        img.thumbnail((CONFIG.max_image_edge, CONFIG.max_image_edge))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        captured_at = now - timedelta(seconds=CONFIG.capture_interval_sec * (len(images) - 1 - i))
        shots.append(StoredScreenshot(path.name, captured_at, title, buf.getvalue()))
    return question, shots, expect


def cost_usd(usage) -> float:
    return (
        usage.input_tokens * PRICE_INPUT
        + usage.output_tokens * PRICE_OUTPUT
        + (usage.cache_creation_input_tokens or 0) * PRICE_CACHE_WRITE
        + (usage.cache_read_input_tokens or 0) * PRICE_CACHE_READ
    ) / 1_000_000


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", help="run only this case folder name")
    parser.add_argument("--images", type=int, default=CONFIG.recent_image_count,
                        help=f"newest N screenshots per case (default {CONFIG.recent_image_count})")
    args = parser.parse_args()
    # Windows consoles default to cp1252, which can't print symbols Claude often uses (▶, →, ✓).
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    case_dirs = sorted(d for d in CASES_DIR.iterdir() if d.is_dir() and (d / "question.txt").exists())
    if args.case:
        case_dirs = [d for d in case_dirs if d.name == args.case]
    if not case_dirs:
        print(f"No cases found in {CASES_DIR}. See test_cases/README.md.")
        return 1

    RESULTS_DIR.mkdir(exist_ok=True)
    report_path = RESULTS_DIR / f"{datetime.now():%Y%m%d-%H%M%S}.md"
    lines = [f"# Prompt test run — {CONFIG.model}, effort {CONFIG.effort}, {args.images} image(s)\n"]
    total_cost = total_time = 0.0

    for case_dir in case_dirs:
        question, shots, expect = load_case(case_dir, args.images)
        if not shots:
            print(f"[skip] {case_dir.name}: no screenshots")
            continue

        print(f"\n=== {case_dir.name} ({len(shots)} image(s)) ===\nQ: {question}")
        assistant = Assistant()  # fresh conversation per case
        start = time.perf_counter()
        try:
            answer = assistant.ask(question, shots)
        except Exception as e:
            answer = f"ERROR: {e}"
        elapsed = time.perf_counter() - start

        resp = assistant.last_response
        stats = f"{elapsed:.1f}s"
        if resp is not None:
            cost = cost_usd(resp.usage)
            total_cost += cost
            u = resp.usage
            tokens_in = u.input_tokens + (u.cache_creation_input_tokens or 0) + (u.cache_read_input_tokens or 0)
            stats += f", {tokens_in} in / {u.output_tokens} out tokens, ~${cost:.4f}"
            if resp.model != CONFIG.model:
                stats += f", served by {resp.model} (fallback)"
        total_time += elapsed

        print(f"A: {answer}\n[{stats}]")
        if expect:
            print(f"Expected: {expect}")

        lines += [
            f"\n## {case_dir.name}\n",
            f"**Question:** {question}\n",
            f"**Screenshots:** {', '.join(s.id for s in shots)}  \n**Stats:** {stats}\n",
            f"**Answer:**\n\n{answer}\n",
        ]
        if expect:
            lines.append(f"**Should mention:** {expect}\n")

    lines.append(f"\n---\nTotal: {len(case_dirs)} case(s), {total_time:.1f}s, ~${total_cost:.4f}\n")
    report_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nTotal ~${total_cost:.4f}, {total_time:.1f}s. Report: {report_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
