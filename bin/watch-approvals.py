#!/usr/bin/env python3
"""Poll reactions on approval messages, transition state, optionally schedule."""
from __future__ import annotations

import sys
import time
from datetime import date, timedelta
from pathlib import Path

import click

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.approval_poller import poll_once  # noqa: E402
from src.scheduler import schedule_all_approved  # noqa: E402


def parse_date(raw: str) -> date:
    raw = (raw or "").strip().lower()
    if raw in ("", "tomorrow"):
        return date.today() + timedelta(days=1)
    if raw == "today":
        return date.today()
    return date.fromisoformat(raw)


@click.command()
@click.option("--date", "date_arg", default="tomorrow")
@click.option("--loop", is_flag=True)
@click.option("--interval", default=30)
@click.option("--schedule/--no-schedule", default=True, help="Also run scheduler on approved clips.")
def main(date_arg: str, loop: bool, interval: int, schedule: bool) -> None:
    target = parse_date(date_arg).isoformat()

    def _tick() -> None:
        result = poll_once(target)
        for u in result.get("updated", []):
            fg = {"approved": "green", "regenerate": "yellow", "killed": "red"}.get(u["status"], "white")
            click.secho(f"   {u['clip_id']} → {u['status']}", fg=fg)
        if schedule:
            plan = schedule_all_approved(target)
            if plan:
                click.secho(f"🗓  Schedule plan written ({len(plan)} entries):", fg="cyan")
                for row in plan:
                    click.echo(f"   {row['clip_id']} · {row['platform']:<14} · {row['scheduled_for']}")

    if loop:
        click.secho(f"🔄 Watching approvals for {target} every {interval}s. Ctrl-C to stop.", fg="cyan")
        while True:
            try:
                _tick()
            except Exception as e:
                click.secho(f"⚠️  poll error: {e}", fg="yellow")
            time.sleep(interval)
    else:
        _tick()
        click.secho("✅ Pass complete.", fg="green")


if __name__ == "__main__":
    main()
