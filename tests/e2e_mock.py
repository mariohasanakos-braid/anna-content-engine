#!/usr/bin/env python3
"""End-to-end mock dry run.

Exercises the full pipeline in RUNTIME_MODE=mock:

  generate-brief  →  post-brief  →  mock upload 3 clips  →  watch-uploads
                     (process + post outputs)  →  mock 👍 reactions  →
                     watch-approvals (transitions + schedule)

Produces real files in output/ and logs every step. No real Slack calls.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

os.environ.setdefault("RUNTIME_MODE", "mock")
os.environ.setdefault("SKIP_TRANSCRIBE", "1")  # keep the test fast

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))


def sh(cmd: list[str]) -> None:
    print(f"\n$ {' '.join(cmd)}")
    r = subprocess.run(cmd)
    assert r.returncode == 0, f"command failed: {cmd}"


def main() -> None:
    target = (date.today() + timedelta(days=1)).isoformat()

    # 1. Brief generator
    sh([sys.executable, "bin/generate-brief.py", "--date", target, "--no-print"])

    # 2. Post brief (mock)
    sh([sys.executable, "bin/post-brief.py", "--date", target])

    # 3. Mock Dilani uploading 3 clips
    from src.slack_client import SlackClient  # noqa: E402

    state = json.loads((ROOT / "output" / target / "state.json").read_text())
    parent_ts = state["parent_ts"]
    brief = json.loads((ROOT / "output" / target / "brief.json").read_text())
    sample = Path("/tmp/ace-test/sample.mp4").resolve()
    assert sample.exists(), "run the ffmpeg sample-generator block from the runbook first"

    slack = SlackClient()
    for clip in brief["clips"]:
        slack.mock_upload_reply(
            parent_ts=parent_ts,
            user="U_DILANI",
            text=f"{clip['id']} take 1",
            local_file_paths=[sample],
        )

    # 4. Watch uploads (one pass — processes + posts approvals)
    sh([sys.executable, "bin/watch-uploads.py", "--date", target])

    # 5. Mock approval reactions
    state = json.loads((ROOT / "output" / target / "state.json").read_text())
    for clip_id, entry in state["approvals"].items():
        slack.mock_add_reaction(entry["approval_ts"], "+1", "U_MARIO")
        slack.mock_add_reaction(entry["approval_ts"], "+1", "U_DILANI")

    # 6. Approval poller + schedule
    sh([sys.executable, "bin/watch-approvals.py", "--date", target])

    # 7. Print final state summary
    print("\n────────── FINAL STATE ──────────")
    print(json.dumps(json.loads((ROOT / "output" / target / "state.json").read_text()), indent=2))
    schedule_path = ROOT / "output" / target / "schedule.json"
    if schedule_path.exists():
        print("\n────────── SCHEDULE ──────────")
        print(json.dumps(json.loads(schedule_path.read_text()), indent=2))
    print("\n────────── OUTPUT FILES ──────────")
    for f in sorted((ROOT / "output" / target).rglob("*.mp4")):
        size = f.stat().st_size
        print(f"   {f.relative_to(ROOT)}  ({size // 1024} KB)")


if __name__ == "__main__":
    main()
