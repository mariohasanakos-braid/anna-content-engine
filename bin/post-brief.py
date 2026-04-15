#!/usr/bin/env python3
"""Post the daily brief for a given date to Slack.

Relies on output/{date}/brief.blockkit.json existing (create it first with
bin/generate-brief.py).

Usage:
  python bin/post-brief.py --date tomorrow
  python bin/post-brief.py --date 2026-04-16
"""
from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

import click

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.slack_client import SlackClient  # noqa: E402


ROOT = Path(__file__).parent.parent


def parse_date(raw: str) -> date:
    raw = (raw or "").strip().lower()
    if raw in ("", "tomorrow"):
        return date.today() + timedelta(days=1)
    if raw == "today":
        return date.today()
    return date.fromisoformat(raw)


@click.command()
@click.option("--date", "date_arg", default="tomorrow")
def main(date_arg: str) -> None:
    target = parse_date(date_arg)
    day_dir = ROOT / "output" / target.isoformat()
    blockkit_path = day_dir / "brief.blockkit.json"
    json_path = day_dir / "brief.json"

    if not blockkit_path.exists():
        click.secho(
            f"❌ {blockkit_path} not found. Run bin/generate-brief.py --date {target} first.",
            fg="red",
        )
        sys.exit(1)

    blocks = json.loads(blockkit_path.read_text())
    brief = json.loads(json_path.read_text())
    fallback = f"Anna content brief — {brief['weekday'].title()} {brief['date']} ({len(brief['clips'])} clips)"

    client = SlackClient()
    client.smoke_test()
    ts = client.post_brief(target.isoformat(), blocks, fallback)

    # Persist the ts so the upload watcher knows which thread to follow.
    state_path = day_dir / "state.json"
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    state["parent_ts"] = ts
    state["channel_id"] = client.channel_id
    state["mode"] = client.mode
    state_path.write_text(json.dumps(state, indent=2))

    click.secho(f"\n✅ Brief posted. parent_ts={ts} (saved to state.json)", fg="green")


if __name__ == "__main__":
    main()
