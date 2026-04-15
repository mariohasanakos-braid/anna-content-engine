"""
Scheduler — stub that queues approved clips for posting to each platform.

Tier 1 (demo): writes a schedule.json with the platform × time plan.
Tier 2 (future): wire up Buffer API / Metricool / direct platform APIs to
actually post.

Best-posting-time heuristics used for the stub:
  TikTok:        19:00 local (peak for 28-45 mom demographic, weeknights)
  IG Reels:      12:00 local (lunch-break scroll)
  FB Reels:      12:00 local (same content as IG)
  YT Shorts 13s: 14:00 local (afternoon YouTube browsing)
  YT Shorts 60s: 20:00 local (evening long-form hop-over)

Multiple clips on the same day stagger posting times by 45-min increments
per platform so we don't spam any single feed.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

try:
    from zoneinfo import ZoneInfo  # py>=3.9
except ImportError:  # pragma: no cover
    ZoneInfo = None  # type: ignore

ROOT = Path(__file__).parent.parent

BASE_TIMES = {
    "tiktok": (19, 0),
    "ig-reels": (12, 0),
    "fb-reels": (12, 0),
    "yt-shorts-13s": (14, 0),
    "yt-shorts-60s": (20, 0),
}


def _load_state(date_str: str) -> dict:
    p = ROOT / "output" / date_str / "state.json"
    return json.loads(p.read_text()) if p.exists() else {}


def _save_state(date_str: str, state: dict) -> None:
    p = ROOT / "output" / date_str / "state.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(state, indent=2))


def _local_dt(date_str: str, hour: int, minute: int) -> datetime:
    import os

    tz_name = os.environ.get("TIMEZONE", "UTC")
    base = datetime.fromisoformat(date_str).replace(hour=hour, minute=0)
    dt = base + timedelta(minutes=minute)
    if ZoneInfo is None:
        return dt
    try:
        return dt.replace(tzinfo=ZoneInfo(tz_name))
    except Exception:
        return dt


def schedule_all_approved(date_str: str) -> list[dict]:
    state = _load_state(date_str)
    approvals = state.get("approvals", {})
    if not approvals:
        return []

    plan: list[dict] = []
    staggers: dict[str, int] = {}  # platform -> minute offset

    for clip_id in sorted(approvals):
        entry = approvals[clip_id]
        if entry.get("status") != "approved":
            continue
        outputs = entry.get("outputs", {})
        for platform, path in outputs.items():
            hour, minute = BASE_TIMES.get(platform, (9, 0))
            stagger = staggers.get(platform, 0)
            when = _local_dt(date_str, hour, minute + stagger)
            staggers[platform] = stagger + 45

            plan.append(
                {
                    "clip_id": clip_id,
                    "platform": platform,
                    "file": path,
                    "scheduled_for": when.isoformat(),
                    "action": "would-post",
                    "real_posting_integration": None,
                }
            )

    day_dir = ROOT / "output" / date_str
    day_dir.mkdir(parents=True, exist_ok=True)
    (day_dir / "schedule.json").write_text(json.dumps(plan, indent=2))

    state["scheduled_at"] = datetime.now().isoformat()
    _save_state(date_str, state)
    return plan
