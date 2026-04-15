"""
Upload watcher — polls a brief's Slack thread for new file uploads,
downloads them, and triggers the clip processor.

Operates in both mock and real modes (via SlackClient).

A reply "qualifies" if:
  - it has at least one file attachment
  - the text starts with or contains one of the clip ids (b1, b2, b3)
  OR the file's name contains the clip id

We dedupe by reply ts so re-runs of the watcher pick up only new stuff.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict
from pathlib import Path
from typing import Iterable, Optional

from src.slack_client import SlackClient, ThreadReply


ROOT = Path(__file__).parent.parent


def _load_state(date_str: str) -> dict:
    p = ROOT / "output" / date_str / "state.json"
    return json.loads(p.read_text()) if p.exists() else {}


def _save_state(date_str: str, state: dict) -> None:
    p = ROOT / "output" / date_str / "state.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(state, indent=2))


def _clip_id_from_reply(reply: ThreadReply, valid_ids: set[str]) -> Optional[str]:
    """Detect a clip id (b1/b2/b3) from reply text or file name."""
    # Prefer explicit text marker
    m = re.search(r"\bb[1-9]\b", reply.text, re.IGNORECASE)
    if m:
        cid = m.group(0).lower()
        if cid in valid_ids:
            return cid
    # Fall back to file name
    for f in reply.files:
        name = (f.get("name") or "").lower()
        m = re.search(r"b[1-9]", name)
        if m and m.group(0) in valid_ids:
            return m.group(0)
    # Heuristic: position in the thread (1st reply → b1, etc)
    return None


def _download_clip(
    slack: SlackClient,
    reply: ThreadReply,
    clip_id: str,
    date_str: str,
) -> Optional[Path]:
    if not reply.files:
        return None
    f = reply.files[0]  # take the first file attached
    mime = f.get("mimetype", "")
    name = (f.get("name") or "").lower()
    looks_like_video = mime.startswith("video/") or name.endswith(
        (".mp4", ".mov", ".m4v", ".webm")
    )
    if not looks_like_video:
        print(f"   (skipping non-video file: {name})")
        return None

    staging_dir = ROOT / "staging" / date_str
    staging_dir.mkdir(parents=True, exist_ok=True)
    dest = staging_dir / f"{clip_id}.mp4"
    return slack.download_file(f, dest)


def poll_once(date_str: str) -> list[dict]:
    """Single poll pass: fetches replies, downloads new clips, returns a summary.

    Returns a list of {clip_id, source_path, reply_ts, new}.
    """
    state = _load_state(date_str)
    parent_ts = state.get("parent_ts")
    if not parent_ts:
        raise RuntimeError(
            f"No parent_ts in output/{date_str}/state.json — run bin/post-brief.py first."
        )

    slack = SlackClient(channel_id=state.get("channel_id"))

    # brief.json to know the valid clip ids
    brief_path = ROOT / "output" / date_str / "brief.json"
    if not brief_path.exists():
        raise RuntimeError(f"No brief.json at {brief_path}")
    brief = json.loads(brief_path.read_text())
    valid_ids = {c["id"] for c in brief["clips"]}

    seen = set(state.get("seen_reply_ts", []))
    already_downloaded = set(state.get("downloaded_clip_ids", []))

    replies = slack.list_thread_replies(parent_ts)
    replies.sort(key=lambda r: float(r.ts) if r.ts else 0.0)

    summary: list[dict] = []
    # Assign fallback clip_id by reply order excluding already-seen
    unassigned = [c for c in valid_ids if c not in already_downloaded]
    unassigned.sort()

    for reply in replies:
        if reply.ts in seen:
            continue
        if not reply.files:
            seen.add(reply.ts)
            continue

        clip_id = _clip_id_from_reply(reply, valid_ids)
        if clip_id is None and unassigned:
            clip_id = unassigned.pop(0)
            print(f"   No clip id detected in reply {reply.ts}; assigning {clip_id} by position.")
        if clip_id is None:
            print(f"   ⚠️  Could not assign a clip id for reply {reply.ts} — skipping.")
            seen.add(reply.ts)
            continue
        if clip_id in already_downloaded:
            print(f"   (dup) clip {clip_id} already downloaded; skipping reply {reply.ts}")
            seen.add(reply.ts)
            continue

        dest = _download_clip(slack, reply, clip_id, date_str)
        seen.add(reply.ts)
        if dest is None:
            continue
        already_downloaded.add(clip_id)
        print(f"   ⬇️  {clip_id} ← {reply.ts}  ({dest})")

        summary.append(
            {
                "clip_id": clip_id,
                "source_path": str(dest),
                "reply_ts": reply.ts,
                "new": True,
            }
        )

    state["seen_reply_ts"] = sorted(seen)
    state["downloaded_clip_ids"] = sorted(already_downloaded)
    _save_state(date_str, state)
    return summary
