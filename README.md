# Anna Content Engine

Slack-native content pipeline for Anna's brand channel. Takes Dilani's daily camera work + AI-generated assets and turns them into scheduled multi-platform posts with minimum human-tokens spent.

## The core idea

Dilani spends <45 min/day being a camera. Everything else is automated:

```
Daily brief generator → Slack post to #anna-content
        ↓
Dilani records 3 clips (iPhone front camera, her kitchen)
        ↓
Uploads clips as replies in Slack thread
        ↓
Pipeline auto-downloads → cuts → captions → multi-platform renders
        ↓
Processed videos post back to same Slack thread
        ↓
Mario + Dilani emoji-approve (👍 ship / 🔄 regenerate / ❌ kill)
        ↓
Scheduler queues for posting to TikTok + IG Reels + FB Reels + YT Shorts
```

Everything flows through Slack. No SMS. No dashboard. No new app for Dilani to learn.

## Status

Tier 1 (this repo's current scope):
- [x] Repo scaffolding
- [x] Channel plan + scope docs
- [x] Brief generator (Claude API + calendar; template fallback when no key)
- [x] Slack poster for daily brief (mock + real modes)
- [x] Upload watcher (polls thread, downloads clips, auto-detects clip_id)
- [x] Clip processor (ffmpeg reframe + optional whisper captions → 4 platform outputs)
- [x] Output poster + emoji-reaction approval flow
- [x] Schedule stub (writes schedule.json with staggered platform times)
- [x] Runbook + end-to-end mock demo (`tests/e2e_mock.py`)

Tier 2 (post-MVP):
- [ ] Real platform posting (Buffer/Metricool API)
- [ ] Comment triage + reply drafts
- [ ] Performance feedback loop (posts → briefs)
- [ ] Remotion b-roll splicing for agent-demo clips

## Quick start (zero keys needed)

```bash
pip install -r requirements.txt

# Generate a sample video for the mock upload
mkdir -p /tmp/ace-test
ffmpeg -y -f lavfi -i "testsrc=duration=5:size=640x1138:rate=30" \
  -f lavfi -i "sine=frequency=440:duration=5" \
  -c:v libx264 -pix_fmt yuv420p -c:a aac -shortest /tmp/ace-test/sample.mp4

# Run the full pipeline in mock mode (no API keys)
python3 tests/e2e_mock.py
```

That prints a generated brief, mocks Dilani uploading 3 clips, processes them into
5 platform outputs each, mocks 👍 reactions, and writes a posting schedule.

For real-Slack mode, see `docs/SLACK_SETUP.md` and `docs/RUNBOOK.md`.

## Docs
- [Channel plan](docs/CHANNEL_PLAN.md) — what we're building this for
- [App scope](docs/SCOPE.md) — full scope of the engine
- [Slack setup](docs/SLACK_SETUP.md) — 5-min Slack app install
- [Runbook](docs/RUNBOOK.md) — demo this to the team
