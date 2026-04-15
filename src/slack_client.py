"""
Slack client — thin wrapper over slack_sdk with a mock mode.

The engine flows everything through a single channel. This module exposes the
operations we actually need:

  post_brief_message(date, blocks, text)    -> ts of the parent message
  list_thread_replies(channel, thread_ts)   -> replies with files
  download_file(file_info, dest)            -> saves a file's bytes to disk
  post_processed_clip(thread_ts, clip_info, file_paths)  -> uploads processed outputs
  get_reactions(channel, ts)                -> {emoji_name: [user_ids]}
  smoke_test()                              -> verifies connection + channel access

RUNTIME_MODE=mock: prints to terminal, writes logs, skips all real Slack calls.
RUNTIME_MODE=real: hits Slack. Requires SLACK_BOT_TOKEN.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).parent.parent
LOGS_DIR = ROOT / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)

MODE = os.environ.get("RUNTIME_MODE", "mock").lower()
CHANNEL_ID = os.environ.get("SLACK_CHANNEL_ID", "C_MOCK_CHANNEL")


# ── Data types ───────────────────────────────────────────────
@dataclass
class ThreadReply:
    user: str
    text: str
    ts: str
    files: list[dict] = field(default_factory=list)


# ── Mock store (file-backed so it persists across processes) ──
_MOCK_FILE = LOGS_DIR / "mock-slack-state.json"


def _load_mock_state() -> dict[str, Any]:
    if _MOCK_FILE.exists():
        raw = json.loads(_MOCK_FILE.read_text())
        # Re-hydrate ThreadReply objects from dicts
        replies: dict[str, list] = {}
        for pts, items in raw.get("replies", {}).items():
            replies[pts] = [
                ThreadReply(
                    user=i["user"],
                    text=i["text"],
                    ts=i["ts"],
                    files=i.get("files") or [],
                )
                for i in items
            ]
        raw["replies"] = replies
        return raw
    return {
        "messages": {},
        "replies": {},
        "reactions": {},
        "counter": 1_000_000,
    }


def _save_mock_state(state: dict[str, Any]) -> None:
    # Serialise ThreadReply dataclasses back to dicts
    serial = dict(state)
    serial["replies"] = {
        pts: [
            {"user": r.user, "text": r.text, "ts": r.ts, "files": r.files}
            for r in items
        ]
        for pts, items in state.get("replies", {}).items()
    }
    _MOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    _MOCK_FILE.write_text(json.dumps(serial, indent=2, default=str))


_MOCK_STATE: dict[str, Any] = _load_mock_state()


def _next_ts() -> str:
    _MOCK_STATE["counter"] += 1
    _save_mock_state(_MOCK_STATE)
    return f"{time.time():.0f}.{_MOCK_STATE['counter']:06d}"


def _log(event: dict) -> None:
    event["_ts"] = time.time()
    event["_mode"] = MODE
    with (LOGS_DIR / "slack.log").open("a") as f:
        f.write(json.dumps(event) + "\n")


# ── Client ───────────────────────────────────────────────────
class SlackClient:
    def __init__(self, channel_id: Optional[str] = None):
        self.channel_id = channel_id or CHANNEL_ID
        self.mode = MODE
        self._wc = None
        if self.mode == "real":
            token = os.environ.get("SLACK_BOT_TOKEN")
            if not token:
                raise RuntimeError(
                    "RUNTIME_MODE=real requires SLACK_BOT_TOKEN. "
                    "Set it in .env or switch RUNTIME_MODE=mock."
                )
            from slack_sdk import WebClient  # local import so mock mode has no SDK dep

            self._wc = WebClient(token=token)

    # ── Smoke test ──
    def smoke_test(self) -> dict:
        if self.mode == "mock":
            print("🟡 SlackClient running in MOCK mode — no real Slack calls will be made.")
            return {"mode": "mock", "channel": self.channel_id}
        info = self._wc.auth_test()
        ch = self._wc.conversations_info(channel=self.channel_id)
        print(f"✅ Slack connected. Bot = {info['user_id']}, Channel = {ch['channel']['name']} ({self.channel_id})")
        return {
            "mode": "real",
            "bot_user": info["user_id"],
            "channel_id": self.channel_id,
            "channel_name": ch["channel"]["name"],
        }

    # ── Post the brief ──
    def post_brief(self, date_str: str, blocks: list[dict], fallback_text: str) -> str:
        """Post the daily brief as a top-level channel message. Returns its ts."""
        _log({"op": "post_brief", "date": date_str, "channel": self.channel_id})

        if self.mode == "mock":
            ts = _next_ts()
            _MOCK_STATE["messages"][ts] = {
                "channel": self.channel_id,
                "text": fallback_text,
                "blocks": blocks,
                "thread_ts": None,
                "date": date_str,
            }
            _MOCK_STATE["replies"].setdefault(ts, [])
            _save_mock_state(_MOCK_STATE)
            print("─" * 70)
            print(f"📤 [MOCK] Posted brief to {self.channel_id} — ts={ts}")
            print(f"   date={date_str}")
            print("─" * 70)
            for block in blocks:
                if block.get("type") == "section" and "text" in block:
                    print(block["text"]["text"])
                    print()
                elif block.get("type") == "divider":
                    print("·" * 40)
                elif block.get("type") == "context":
                    for el in block.get("elements", []):
                        print(f"ℹ️  {el.get('text', '')}")
            print("─" * 70)
            return ts

        resp = self._wc.chat_postMessage(
            channel=self.channel_id,
            blocks=blocks,
            text=fallback_text,
            unfurl_links=False,
            unfurl_media=False,
        )
        ts = resp["ts"]
        print(f"✅ Posted brief to {self.channel_id} at ts={ts}")
        return ts

    # ── Read thread replies ──
    def list_thread_replies(self, parent_ts: str) -> list[ThreadReply]:
        _log({"op": "list_thread_replies", "parent_ts": parent_ts})

        if self.mode == "mock":
            replies = _MOCK_STATE["replies"].get(parent_ts, [])
            return list(replies)

        resp = self._wc.conversations_replies(channel=self.channel_id, ts=parent_ts)
        out: list[ThreadReply] = []
        for msg in resp.get("messages", []):
            # Skip the parent (first message equals parent)
            if msg.get("ts") == parent_ts:
                continue
            out.append(
                ThreadReply(
                    user=msg.get("user", ""),
                    text=msg.get("text", ""),
                    ts=msg.get("ts", ""),
                    files=msg.get("files", []) or [],
                )
            )
        return out

    # ── Download a file (videos) ──
    def download_file(self, file_info: dict, dest: Path) -> Path:
        _log({"op": "download_file", "file_id": file_info.get("id"), "dest": str(dest)})
        dest.parent.mkdir(parents=True, exist_ok=True)

        if self.mode == "mock":
            # In mock mode, the "files" array items are expected to have a local `mock_source`
            # path we copy from. See SlackClient.mock_upload_file below.
            src = file_info.get("mock_source")
            if src and Path(src).exists():
                dest.write_bytes(Path(src).read_bytes())
            else:
                # Otherwise write a tiny placeholder so the pipeline still runs
                dest.write_bytes(b"MOCK_VIDEO_PLACEHOLDER")
            return dest

        import requests  # local import

        url = file_info.get("url_private_download") or file_info.get("url_private")
        if not url:
            raise ValueError(f"No download URL on file: {file_info}")
        headers = {"Authorization": f"Bearer {os.environ['SLACK_BOT_TOKEN']}"}
        r = requests.get(url, headers=headers, stream=True, timeout=60)
        r.raise_for_status()
        with dest.open("wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 256):
                f.write(chunk)
        return dest

    # ── Post a processed clip output ──
    def post_processed_output(
        self,
        parent_ts: str,
        clip_id: str,
        variant_index: int,
        total_variants: int,
        file_paths: dict[str, Path],
        notes: str = "",
    ) -> str:
        """Upload processed clips to Slack as thread replies.

        file_paths keys are platform labels ('tiktok', 'ig-reels', etc.),
        values are local paths. Returns the ts of the reply message.
        """
        _log(
            {
                "op": "post_processed_output",
                "parent_ts": parent_ts,
                "clip_id": clip_id,
                "files": {k: str(v) for k, v in file_paths.items()},
            }
        )

        blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"*🎞 Processed {clip_id} — {variant_index}/{total_variants}*"
                        + (f"\n{notes}" if notes else "")
                    ),
                },
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": (
                            "*React to approve:*  :+1: ship  ·  :arrows_counterclockwise: regenerate"
                            "  ·  :x: kill"
                        ),
                    }
                ],
            },
        ]
        fallback_text = f"Processed {clip_id} ({variant_index}/{total_variants})"

        if self.mode == "mock":
            ts = _next_ts()
            _MOCK_STATE["messages"][ts] = {
                "channel": self.channel_id,
                "text": fallback_text,
                "blocks": blocks,
                "thread_ts": parent_ts,
                "clip_id": clip_id,
                "files": {k: str(v) for k, v in file_paths.items()},
            }
            _save_mock_state(_MOCK_STATE)
            print(f"📤 [MOCK] Posted processed {clip_id} ({variant_index}/{total_variants}) to thread {parent_ts}")
            for platform, path in file_paths.items():
                print(f"    · {platform}: {path}")
            print("    (React 👍 / 🔄 / ❌ in mock store to trigger approval)")
            return ts

        # Real: upload primary file via files_upload_v2 with channel + thread anchor
        # then post the formatted block message. Keep it simple — one attachment upload
        # per platform file.
        primary_path = next(iter(file_paths.values()))
        upload = self._wc.files_upload_v2(
            channel=self.channel_id,
            thread_ts=parent_ts,
            file=str(primary_path),
            initial_comment=fallback_text,
        )
        # Additional platform files attached as plain uploads
        for platform, path in list(file_paths.items())[1:]:
            self._wc.files_upload_v2(
                channel=self.channel_id,
                thread_ts=parent_ts,
                file=str(path),
                initial_comment=f"↑ {platform} version",
            )
        # Separate block message with the approval prompt
        resp = self._wc.chat_postMessage(
            channel=self.channel_id,
            thread_ts=parent_ts,
            blocks=blocks,
            text=fallback_text,
        )
        return resp["ts"]

    # ── Reactions ──
    def get_reactions(self, ts: str) -> dict[str, list[str]]:
        _log({"op": "get_reactions", "ts": ts})
        if self.mode == "mock":
            return dict(_MOCK_STATE["reactions"].get(ts, {}))
        resp = self._wc.reactions_get(channel=self.channel_id, timestamp=ts)
        out: dict[str, list[str]] = {}
        for r in (resp.get("message") or {}).get("reactions", []) or []:
            out[r["name"]] = list(r.get("users", []))
        return out

    # ── Mock testing helpers ──
    def mock_upload_reply(
        self,
        parent_ts: str,
        user: str,
        text: str,
        local_file_paths: list[Path],
    ) -> str:
        """Simulate Dilani uploading clip files as a thread reply."""
        assert self.mode == "mock", "Only usable in mock mode"
        reply_ts = _next_ts()
        files = [
            {
                "id": f"F_MOCK_{i}",
                "name": p.name,
                "size": p.stat().st_size if p.exists() else 0,
                "mock_source": str(p),
                "url_private_download": f"mock://{p}",
            }
            for i, p in enumerate(local_file_paths)
        ]
        _MOCK_STATE["replies"].setdefault(parent_ts, []).append(
            ThreadReply(user=user, text=text, ts=reply_ts, files=files)
        )
        _save_mock_state(_MOCK_STATE)
        print(f"📥 [MOCK] {user} replied to {parent_ts}: {text!r} (+{len(files)} file(s))")
        return reply_ts

    def mock_add_reaction(self, ts: str, emoji: str, user: str) -> None:
        assert self.mode == "mock", "Only usable in mock mode"
        bucket = _MOCK_STATE["reactions"].setdefault(ts, {})
        users = bucket.setdefault(emoji, [])
        if user not in users:
            users.append(user)
        _save_mock_state(_MOCK_STATE)
        print(f"✋ [MOCK] {user} reacted :{emoji}: on {ts}")
