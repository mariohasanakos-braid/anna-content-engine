"""
Approval poller — reads emoji reactions on processed-clip messages and transitions
state awaiting → approved | regenerate | killed.

Approval rules (MVP):
  :+1:                      → approved (one 👍 is enough for demo; tighten to 2+ later)
  :arrows_counterclockwise: → regenerate
  :x:                       → killed

The scheduler picks up anything with status=approved and queues it.
"""

from __future__ import annotations

import json
from pathlib import Path

from src.slack_client import SlackClient


ROOT = Path(__file__).parent.parent


def _load_state(date_str: str) -> dict:
    p = ROOT / "output" / date_str / "state.json"
    return json.loads(p.read_text()) if p.exists() else {}


def _save_state(date_str: str, state: dict) -> None:
    p = ROOT / "output" / date_str / "state.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(state, indent=2))


APPROVE_EMOJI = "+1"
REGEN_EMOJI = "arrows_counterclockwise"
KILL_EMOJI = "x"


def poll_once(date_str: str) -> dict:
    """Check each awaiting approval once. Mutates state.json. Returns summary."""
    state = _load_state(date_str)
    approvals = state.get("approvals", {})
    if not approvals:
        return {"updated": [], "note": "no approvals yet (run process + post-outputs first)"}

    slack = SlackClient(channel_id=state.get("channel_id"))
    updated: list[dict] = []

    for clip_id, entry in approvals.items():
        if entry.get("status") != "awaiting":
            continue
        ts = entry["approval_ts"]
        reactions = slack.get_reactions(ts)

        if reactions.get(KILL_EMOJI):
            entry["status"] = "killed"
            updated.append({"clip_id": clip_id, "status": "killed"})
            continue
        if reactions.get(REGEN_EMOJI):
            entry["status"] = "regenerate"
            updated.append({"clip_id": clip_id, "status": "regenerate"})
            continue
        if reactions.get(APPROVE_EMOJI):
            entry["status"] = "approved"
            updated.append({"clip_id": clip_id, "status": "approved"})
            continue

    state["approvals"] = approvals
    _save_state(date_str, state)
    return {"updated": updated}
