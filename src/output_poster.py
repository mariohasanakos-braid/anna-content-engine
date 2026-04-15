"""
Output poster — given a ProcessedClip, posts the platform outputs back to
the brief's Slack thread with emoji approval instructions.

For each processed clip, we create ONE approval message and attach the
platform files. The ts of the approval message is persisted in state.json
so the approval poller can monitor reactions.
"""

from __future__ import annotations

import json
from pathlib import Path

from src.clip_processor import ProcessedClip
from src.slack_client import SlackClient


ROOT = Path(__file__).parent.parent


def _load_state(date_str: str) -> dict:
    p = ROOT / "output" / date_str / "state.json"
    return json.loads(p.read_text()) if p.exists() else {}


def _save_state(date_str: str, state: dict) -> None:
    p = ROOT / "output" / date_str / "state.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(state, indent=2))


def post_clip_outputs(date_str: str, processed: ProcessedClip, total_clips: int = 3) -> str:
    state = _load_state(date_str)
    parent_ts = state.get("parent_ts")
    if not parent_ts:
        raise RuntimeError(f"No parent_ts in output/{date_str}/state.json")

    # Resolve numeric index from the clip_id for "x of 3" formatting
    try:
        idx = int(processed.clip_id.lstrip("b"))
    except ValueError:
        idx = 1

    slack = SlackClient(channel_id=state.get("channel_id"))
    notes = "\n".join(processed.notes) if processed.notes else ""
    if processed.caption_pending:
        notes = "_Captions pending._ " + notes

    file_paths = {platform: Path(path) for platform, path in processed.outputs.items()}
    approval_ts = slack.post_processed_output(
        parent_ts=parent_ts,
        clip_id=processed.clip_id,
        variant_index=idx,
        total_variants=total_clips,
        file_paths=file_paths,
        notes=notes,
    )

    # Record approval anchor in state
    approvals = state.setdefault("approvals", {})
    approvals[processed.clip_id] = {
        "approval_ts": approval_ts,
        "status": "awaiting",
        "outputs": processed.outputs,
    }
    _save_state(date_str, state)
    return approval_ts
