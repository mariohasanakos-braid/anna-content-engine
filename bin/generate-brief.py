#!/usr/bin/env python3
"""Generate the daily brief for a given date.

Usage:
  python bin/generate-brief.py                    # tomorrow
  python bin/generate-brief.py --date 2026-04-16
  python bin/generate-brief.py --date today
  python bin/generate-brief.py --date tomorrow
"""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

import click

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.brief_generator import generate_brief  # noqa: E402


def parse_date(raw: str) -> date:
    raw = (raw or "").strip().lower()
    if raw in ("", "tomorrow"):
        return date.today() + timedelta(days=1)
    if raw == "today":
        return date.today()
    return date.fromisoformat(raw)


@click.command()
@click.option(
    "--date",
    "date_arg",
    default="tomorrow",
    help="Date to generate brief for (YYYY-MM-DD, 'today', or 'tomorrow').",
)
@click.option(
    "--print/--no-print",
    "do_print",
    default=True,
    help="Print the generated brief to stdout.",
)
def main(date_arg: str, do_print: bool) -> None:
    target = parse_date(date_arg)

    click.echo(f"📝 Generating brief for {target} ({target.strftime('%A')})...")
    try:
        brief = generate_brief(target)
    except ValueError as e:
        click.secho(f"❌ {e}", fg="red")
        sys.exit(1)

    click.secho(f"✅ Brief written to output/{target}/brief.json", fg="green")
    click.secho(f"✅ Block Kit written to output/{target}/brief.blockkit.json", fg="green")

    if do_print:
        click.echo()
        click.echo("─" * 60)
        click.echo(f"Brief for {brief.weekday.title()} {brief.date}")
        click.echo("─" * 60)
        for i, clip in enumerate(brief.clips, 1):
            click.echo(f"\nClip {i} [{clip.type}] — {clip.theme}")
            click.echo(f"  Hook:          {clip.hook}")
            click.echo(f"  Purpose:       {clip.purpose}")
            click.echo(f"  Target length: {clip.target_length_sec}s")
            click.echo(f"  Delivery:      {clip.delivery_notes}")
            if clip.b_roll_brief:
                click.echo(f"  B-roll:        {clip.b_roll_brief}")
            click.echo(f"  Platforms:     {', '.join(clip.platforms)}")


if __name__ == "__main__":
    main()
