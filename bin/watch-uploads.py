#!/usr/bin/env python3
"""Poll the brief thread for new clip uploads and run them through the processor.

Usage:
  python bin/watch-uploads.py --date tomorrow           # one pass
  python bin/watch-uploads.py --date tomorrow --loop    # poll forever (30s interval)
"""
from __future__ import annotations

import json
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import click

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.slack_watcher import poll_once  # noqa: E402
from src.clip_processor import process_clip  # noqa: E402
from src.output_poster import post_clip_outputs  # noqa: E402


ROOT = Path(__file__).parent.parent


def parse_date(raw: str) -> date:
    raw = (raw or "").strip().lower()
    if raw in ("", "tomorrow"):
        return date.today() + timedelta(days=1)
    if raw == "today":
        return date.today()
    return date.fromisoformat(raw)


def process_and_post(date_str: str, summary: list[dict]) -> None:
    if not summary:
        return
    brief = json.loads((ROOT / "output" / date_str / "brief.json").read_text())
    type_by_id = {c["id"]: c["type"] for c in brief["clips"]}
    total = len(brief["clips"])

    for item in summary:
        cid = item["clip_id"]
        src = Path(item["source_path"])
        click.secho(f"   🎬 processing {cid}...", fg="cyan")
        processed = process_clip(src, cid, type_by_id.get(cid, "pure-dilani"), date_str)
        click.secho(f"   ✅ processed {cid} — {len(processed.outputs)} platform outputs", fg="green")
        approval_ts = post_clip_outputs(date_str, processed, total_clips=total)
        click.secho(f"   📤 posted approval message (ts={approval_ts})", fg="green")


@click.command()
@click.option("--date", "date_arg", default="tomorrow")
@click.option("--loop", is_flag=True, help="Poll forever every 30s.")
@click.option("--interval", default=30, help="Seconds between polls (with --loop).")
def main(date_arg: str, loop: bool, interval: int) -> None:
    target = parse_date(date_arg).isoformat()

    def _tick() -> list[dict]:
        try:
            summary = poll_once(target)
        except RuntimeError as e:
            click.secho(f"❌ {e}", fg="red")
            sys.exit(1)
        process_and_post(target, summary)
        return summary

    if loop:
        click.secho(f"🔄 Watching uploads for {target} every {interval}s. Ctrl-C to stop.", fg="cyan")
        while True:
            try:
                _tick()
            except Exception as e:  # keep loop alive
                click.secho(f"⚠️  poll error: {e}", fg="yellow")
            time.sleep(interval)
    else:
        summary = _tick()
        click.secho(f"\n✅ Pass complete — processed {len(summary)} new upload(s).", fg="green")


if __name__ == "__main__":
    main()
