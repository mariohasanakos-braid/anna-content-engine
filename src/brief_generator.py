"""
Brief generator — picks tomorrow's 3 clips and drafts hooks/purpose/delivery notes.

Inputs:
  - content/calendar.yaml (cadence + topic pool)
  - date to generate for
  - (Tier 2) last 7 days' post performance
  - (Tier 2) unanswered comment queue

Output:
  - structured JSON brief saved to output/{date}/brief.json
  - Slack Block Kit version saved to output/{date}/brief.blockkit.json

Uses Claude API for the final draft pass — the calendar provides the "what",
Claude provides the "how" (crisp hook line, delivery direction, tailored to the
voice rules in the calendar).
"""

from __future__ import annotations

import json
import os
import random
import sys
from dataclasses import dataclass, field, asdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

import yaml
from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).parent.parent
CALENDAR_PATH = ROOT / "content" / "calendar.yaml"
OUTPUT_DIR = ROOT / "output"

CLAUDE_MODEL = "claude-opus-4-6"  # Opus 4.6 — latest, best for this


# ── Types ────────────────────────────────────────────────────
@dataclass
class ClipBrief:
    id: str
    type: str  # agent-demo | avatar-explainer | reaction | pure-dilani
    topic_id: str
    theme: str
    hook: str
    purpose: str
    target_length_sec: int
    delivery_notes: str
    b_roll_brief: Optional[str] = None
    platforms: list[str] = field(default_factory=list)


@dataclass
class DailyBrief:
    date: str
    weekday: str
    clips: list[ClipBrief]

    def to_dict(self) -> dict:
        return {
            "date": self.date,
            "weekday": self.weekday,
            "clips": [asdict(c) for c in self.clips],
        }


# ── Calendar helpers ─────────────────────────────────────────
def load_calendar() -> dict:
    with open(CALENDAR_PATH) as f:
        return yaml.safe_load(f)


def save_calendar(cal: dict) -> None:
    """Persist the calendar, stripping any transient underscore-prefixed keys."""
    clean = json.loads(json.dumps(cal))  # deep copy
    for topic in clean.get("topics", []):
        for k in list(topic.keys()):
            if k.startswith("_"):
                del topic[k]
    with open(CALENDAR_PATH, "w") as f:
        yaml.safe_dump(clean, f, sort_keys=False, width=120, allow_unicode=True)


def weekday_key(d: date) -> str:
    return ["mon", "tue", "wed", "thu", "fri", "sat", "sun"][d.weekday()]


def pick_topics(
    cal: dict,
    target_date: date,
    num_clips: int = 3,
) -> list[dict]:
    """Pick topic candidates honoring cadence, recency, priority.

    For the MVP we pick exactly one topic matching today's cadence type, plus 2
    more to fill the 3-clip brief. The filler clips prefer the type that appears
    least in the last 7 days to maintain the weekly mix.
    """
    day = weekday_key(target_date)
    primary_type = cal["cadence"].get(day)
    if primary_type in (None, "rest"):
        return []

    cutoff = (target_date - timedelta(days=14)).isoformat()

    def topic_available(t: dict) -> bool:
        if t.get("status") != "active":
            return False
        used = t.get("used_on") or []
        return not any(u >= cutoff for u in used)

    def score(t: dict) -> int:
        pri = {"high": 3, "medium": 2, "low": 1}.get(t.get("priority", "medium"), 2)
        used = t.get("used_on") or []
        freshness = 0 if not used else -1  # mild penalty for ever-used
        return pri + freshness + random.uniform(0, 0.3)  # small jitter

    pool = [t for t in cal["topics"] if topic_available(t)]

    # Primary clip: match today's cadence type
    primary_candidates = [t for t in pool if t["type"] == primary_type]
    if not primary_candidates:
        # fall back to any active type if the cadence slot has no topics
        primary_candidates = pool
    primary_candidates.sort(key=score, reverse=True)
    primary = primary_candidates[0] if primary_candidates else None
    picks = [primary] if primary else []

    # Secondary clips: prefer least-used types
    type_counts: dict[str, int] = {}
    for t in cal["topics"]:
        type_counts[t["type"]] = type_counts.get(t["type"], 0) + len(t.get("used_on") or [])

    def secondary_score(t: dict) -> float:
        base = score(t)
        # prefer types that appear less frequently overall
        type_penalty = -0.3 * type_counts.get(t["type"], 0)
        return base + type_penalty

    remaining = [t for t in pool if t not in picks]
    remaining.sort(key=secondary_score, reverse=True)
    while len(picks) < num_clips and remaining:
        picks.append(remaining.pop(0))

    return picks[:num_clips]


# ── Claude drafting ──────────────────────────────────────────
DRAFT_SYSTEM_PROMPT = """You are the content director for Anna, an AI family assistant for busy parents. You're writing a daily brief for Dilani, one of Anna's founders, who will read this on her phone at 7 AM and record 3 clips for social.

You are not a marketer. You are a crisp, no-nonsense director who knows social content. Your job:

1. Take the topic seeds and the shared delivery context.
2. Pick ONE hook from each topic's hook_options (or write a better one if none fit).
3. Draft a 1-sentence purpose, a target length in seconds, and delivery notes.
4. If the clip type is `agent-demo`, also draft a b_roll_brief describing what Anna-as-agent UI will do between Dilani's lines.

Hard rules:
- NEVER use em dashes. Use periods or commas.
- NEVER start dialogue with "Anna" — TikTok captions confuse it with a child's name. Put Anna's name at the end if needed, or rephrase.
- Keep dialogue to ~22-26 words for any continuous spoken unit.
- The word "Anna" should rarely appear in dialogue. This is info content, not selling.
- Delivery notes should be concrete (posture, gesture, expression, pacing cue), not vague (avoid "be authentic").

Output strictly as JSON matching this schema:
{
  "clips": [
    {
      "id": "b1" | "b2" | "b3",
      "type": "<same as input>",
      "topic_id": "<same as input>",
      "theme": "<same as input>",
      "hook": "<the chosen or improved hook line>",
      "purpose": "<1 sentence on what this clip exists to do>",
      "target_length_sec": <number>,
      "delivery_notes": "<concrete direction>",
      "b_roll_brief": "<only for agent-demo type>",
      "platforms": ["tiktok", "ig-reels", "fb-reels", "yt-shorts"]
    }
  ]
}

For avatar-explainer clips, platforms should be ["tiktok", "yt-shorts"] only.
"""


def _platforms_for(clip_type: str) -> list[str]:
    if clip_type == "avatar-explainer":
        return ["tiktok", "yt-shorts"]
    return ["tiktok", "ig-reels", "fb-reels", "yt-shorts"]


def draft_briefs_from_templates(topics: list[dict]) -> list[ClipBrief]:
    """Fallback drafting when ANTHROPIC_API_KEY is absent.

    Uses the topic's first hook_option + reasonable defaults so the pipeline
    still produces a sensible brief. Good enough for demo + for days Claude
    is unreachable.
    """
    clips: list[ClipBrief] = []
    length_defaults = {
        "pure-dilani": 45,
        "agent-demo": 25,
        "reaction": 30,
        "avatar-explainer": 40,
    }
    delivery_defaults = {
        "pure-dilani": "Face to camera. Warm, direct, one idea per sentence. No script card.",
        "agent-demo": "Intro only. 1-2 sentences that set up the demo. Pause on the last word so we can cut to b-roll cleanly.",
        "reaction": "Stitch or green-screen. Play 3-5s of the source, then your reaction. Warm, not mocking.",
        "avatar-explainer": "Maya (AI character) delivers this, clearly labeled. You will not record this one yourself.",
    }

    for i, t in enumerate(topics, 1):
        hook = (t.get("hook_options") or [t.get("angle", t.get("theme", ""))])[0]
        clips.append(
            ClipBrief(
                id=t.get("_clip_id", f"b{i}"),
                type=t["type"],
                topic_id=t["id"],
                theme=t["theme"],
                hook=hook,
                purpose=t.get("angle", t.get("theme", "")),
                target_length_sec=length_defaults.get(t["type"], 30),
                delivery_notes=delivery_defaults.get(t["type"], "Conversational. One minute prep."),
                b_roll_brief=t.get("b_roll") if t["type"] == "agent-demo" else None,
                platforms=_platforms_for(t["type"]),
            )
        )
    return clips


def draft_briefs_with_claude(topics: list[dict], delivery_context: dict) -> list[ClipBrief]:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("⚠️  ANTHROPIC_API_KEY not set — using template-based fallback drafting.", file=sys.stderr)
        return draft_briefs_from_templates(topics)

    client = Anthropic()

    user_payload = {
        "delivery_context": delivery_context,
        "topic_seeds": topics,
    }

    try:
        resp = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=2000,
            system=DRAFT_SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": (
                        "Draft the brief for these 3 topics. Return JSON only, no markdown.\n\n"
                        + json.dumps(user_payload, indent=2)
                    ),
                }
            ],
        )

        text = resp.content[0].text.strip()
        # strip potential ```json fences defensively
        if text.startswith("```"):
            text = text.strip("`").lstrip("json").strip()
        parsed = json.loads(text)
    except Exception as e:
        print(f"⚠️  Claude drafting failed ({e}). Falling back to templates.", file=sys.stderr)
        return draft_briefs_from_templates(topics)

    clips: list[ClipBrief] = []
    for i, c in enumerate(parsed["clips"]):
        clips.append(
            ClipBrief(
                id=c.get("id", f"b{i+1}"),
                type=c["type"],
                topic_id=c["topic_id"],
                theme=c["theme"],
                hook=c["hook"],
                purpose=c["purpose"],
                target_length_sec=int(c["target_length_sec"]),
                delivery_notes=c["delivery_notes"],
                b_roll_brief=c.get("b_roll_brief"),
                platforms=c.get("platforms", ["tiktok", "ig-reels", "fb-reels", "yt-shorts"]),
            )
        )

    return clips


# ── Slack Block Kit formatter ────────────────────────────────
def to_block_kit(brief: DailyBrief) -> list[dict]:
    """Render the brief as Slack Block Kit JSON. Readable on mobile."""
    header_text = f":clapper: *Anna content — {brief.weekday.title()} {brief.date}*"
    blocks: list[dict] = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"{header_text}\n\n"
                    "Record these 3 clips, then upload here as replies to this message. "
                    "iPhone front camera, your kitchen, natural light. Aim for 15-20 min total."
                ),
            },
        },
        {"type": "divider"},
    ]

    for i, clip in enumerate(brief.clips, 1):
        badge = {
            "pure-dilani": ":face_with_cowboy_hat:",
            "agent-demo": ":phone:",
            "reaction": ":popcorn:",
            "avatar-explainer": ":speaking_head_in_silhouette:",
        }.get(clip.type, ":clapper:")

        body = (
            f"*{badge} Clip {i} — {clip.theme}*\n"
            f"*Hook (first 2 sec):* {clip.hook}\n"
            f"*Purpose:* {clip.purpose}\n"
            f"*Target length:* {clip.target_length_sec}s\n"
            f"*Delivery:* {clip.delivery_notes}"
        )
        if clip.b_roll_brief:
            body += f"\n*Anna b-roll (we add this):* {clip.b_roll_brief}"

        blocks.append(
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": body},
            }
        )
        blocks.append({"type": "divider"})

    blocks.append(
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": (
                        f":speech_balloon: Reply here with one video per clip. "
                        f"Caption each reply with `{brief.clips[0].id}`, `{brief.clips[1].id}`, `{brief.clips[2].id}` "
                        f"so we know which is which. Shoot extra takes if you want; we'll pick the best."
                    ),
                }
            ],
        }
    )

    return blocks


# ── Main entry ───────────────────────────────────────────────
def generate_brief(target_date: date) -> DailyBrief:
    cal = load_calendar()

    if weekday_key(target_date) in {k for k, v in cal["cadence"].items() if v == "rest"}:
        raise ValueError(f"{target_date} is a rest day per calendar cadence.")

    topics = pick_topics(cal, target_date, num_clips=3)
    if not topics:
        raise ValueError(f"No active topics match the cadence for {target_date}.")

    # Assign clip ids b1/b2/b3 in deterministic order
    for i, t in enumerate(topics, 1):
        t["_clip_id"] = f"b{i}"

    clips = draft_briefs_with_claude(topics, cal["delivery_context"])

    # Mark topics as used_on target_date so the recency penalty works next time
    used_date = target_date.isoformat()
    topic_ids_picked = {t["id"] for t in topics}
    for topic in cal["topics"]:
        if topic["id"] in topic_ids_picked:
            topic.setdefault("used_on", []).append(used_date)
    save_calendar(cal)

    brief = DailyBrief(
        date=target_date.isoformat(),
        weekday=weekday_key(target_date),
        clips=clips,
    )

    # Persist
    day_dir = OUTPUT_DIR / target_date.isoformat()
    day_dir.mkdir(parents=True, exist_ok=True)
    (day_dir / "brief.json").write_text(json.dumps(brief.to_dict(), indent=2))
    (day_dir / "brief.blockkit.json").write_text(json.dumps(to_block_kit(brief), indent=2))

    return brief


# ── For ad-hoc local testing ─────────────────────────────────
if __name__ == "__main__":
    target = (
        date.fromisoformat(sys.argv[1])
        if len(sys.argv) > 1
        else date.today() + timedelta(days=1)
    )
    b = generate_brief(target)
    print(json.dumps(b.to_dict(), indent=2))
