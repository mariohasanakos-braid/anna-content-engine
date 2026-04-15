# Runbook — how to demo this

Goal: show the team (and Dilani) the entire daily loop in ~5 minutes, then flip it to real-Slack mode for tomorrow's first shoot.

## Three modes

| Mode | API keys needed | What happens |
|------|-----------------|--------------|
| **mock E2E** | none | Everything runs offline. Outputs real MP4s. Safe to demo before any Slack setup. |
| **mock with Claude** | `ANTHROPIC_API_KEY` | Brief generator uses Claude for sharper hooks. Slack still mocked. |
| **real** | `SLACK_BOT_TOKEN` + channel | Posts to #anna-content. Dilani uploads from her phone. |

## A. Zero-friction demo (no keys, 90 seconds)

This is what you run to show the team "it works":

```bash
cd /Users/mario/dev/anna-content-engine
pip install -r requirements.txt
python3 tests/e2e_mock.py
```

Watch the terminal. You'll see:
1. A brief generated for tomorrow (read from `content/calendar.yaml`)
2. "Posted" to a mock channel — the full Block Kit rendered as text
3. Three mock uploads from "Dilani" (uses `/tmp/ace-test/sample.mp4` — generate once with the snippet below)
4. Each clip processed, 5 platform outputs produced
5. Each result "posted" back to the thread with approval prompts
6. Mock 👍 reactions added
7. Approval poller flips states → scheduler prints tomorrow's posting plan
8. Final state and output-file listing

If you've never run it before, generate the sample video first:

```bash
mkdir -p /tmp/ace-test
ffmpeg -y -f lavfi -i "testsrc=duration=5:size=640x1138:rate=30" \
  -f lavfi -i "sine=frequency=440:duration=5" \
  -c:v libx264 -pix_fmt yuv420p -c:a aac -shortest /tmp/ace-test/sample.mp4
```

## B. Real-Slack demo (5 minutes, requires Slack setup)

First-time prep (~5 min, from `docs/SLACK_SETUP.md`):
1. Create the Slack app, install to your workspace, get bot token
2. Create `#anna-content`, invite the bot
3. `cp .env.example .env` and fill in `SLACK_BOT_TOKEN`, `SLACK_CHANNEL_ID`, set `RUNTIME_MODE=real`

### Act 1 — Dilani's morning (2 min)

On your phone, open Slack → `#anna-content`. On the desktop:

```bash
python bin/generate-brief.py --date tomorrow --no-print
python bin/post-brief.py --date tomorrow
```

A formatted brief appears in the channel. Show your phone — this is what Dilani sees at 7 AM every day: three clips, each with hook + purpose + target length + delivery notes.

**Talking point:** "This is the only thing Dilani has to open. 15-20 minutes of filming and she's done for the day."

### Act 2 — Dilani records + uploads (1 min)

On your phone, reply to the brief thread with 3 short videos from Photos — any videos work for the demo. Caption each reply with the clip ID: `b1`, `b2`, `b3`.

**Talking point:** "Dilani's done. Everything after this is us, not her."

### Act 3 — Processing + output (1.5 min)

```bash
python bin/watch-uploads.py --date tomorrow
```

It detects the 3 uploads, downloads them, auto-captions (if whisper is installed), re-encodes to platform specs, and posts each result back to the thread. You'll see three "Processed bX (1/3)" messages appear, each with attached platform files.

**Talking point:** "Auto-cut the filler, auto-caption, and render platform-specific versions. TikTok gets the full thing, YouTube Shorts gets a 13s teaser + 60s version, Instagram and Facebook share one file."

### Act 4 — Approval + scheduling (30 sec)

React 👍 on each processed-clip message in Slack. Then on desktop:

```bash
python bin/watch-approvals.py --date tomorrow
```

Approvals transition → scheduler writes `output/{date}/schedule.json` and prints the plan:
```
✅ b1 → approved
✅ b2 → approved
✅ b3 → approved
🗓  Schedule plan written (13 entries):
   b1 · tiktok         · 2026-04-16T19:00:00+11:00
   b1 · ig-reels       · 2026-04-16T12:00:00+11:00
   ...
```

**Talking point:** "Scheduling to real platforms is a one-line change — we just need to pick Buffer vs Metricool vs direct platform APIs. Everything upstream works today."

## C. Going live with Dilani tomorrow

1. Make sure `RUNTIME_MODE=real` + Slack token present in `.env`
2. Invite Dilani + the bot to `#anna-content`
3. Send her [a one-minute video tour](https://loom.com/) of what her morning looks like (record one using the channel)
4. Tonight: `python bin/generate-brief.py --date tomorrow`. Review the brief in `output/{date}/brief.json`. Hand-edit any hook that feels off.
5. Morning of: `python bin/post-brief.py --date tomorrow` at 7 AM (or set a cron)
6. Run `python bin/watch-uploads.py --date tomorrow --loop` in a long-running terminal
7. Run `python bin/watch-approvals.py --date tomorrow --loop` in another
8. React 👍 as outputs come in. Check `schedule.json` at end of day.

### Recommended cron (once you trust it)

```cron
# 7:00 AM daily — generate + post tomorrow's brief (runs on Mac mini or VPS)
0 7 * * *  cd /path/to/anna-content-engine && python3 bin/generate-brief.py --date today --no-print && python3 bin/post-brief.py --date today

# Every minute — watch uploads + approvals (systemd/launchd are cleaner for this)
* * * * *  cd /path/to/anna-content-engine && python3 bin/watch-uploads.py --date today
* * * * *  cd /path/to/anna-content-engine && python3 bin/watch-approvals.py --date today
```

## What's working vs stubbed

| Component | Status | Notes |
|-----------|--------|-------|
| Brief generator | ✅ Real | Uses Claude when `ANTHROPIC_API_KEY` is set; falls back to calendar templates otherwise. |
| Slack posting | ✅ Real (or mock) | Mock mode is file-backed and persists across processes. |
| Upload watcher | ✅ Real | Dedupes by reply ts; auto-detects clip_id from text or filename. |
| Clip processor | ✅ Real | ffmpeg reframe + optional whisper captions. Remotion b-roll splicing (Anna-agent UI) is deferred to Tier 2. |
| Output poster | ✅ Real | One approval message per clip, attached platform files. |
| Approval poller | ✅ Real | 👍 ships, 🔄 regenerates (marked; rerun pipeline manually), ❌ kills. |
| Scheduler | ⚠️ Stub | Writes `schedule.json` with planned times. Does NOT post to platforms yet. Next: Buffer API. |
| Comment triage + reply drafting | 🔜 Tier 2 | Not built. |
| Performance feedback loop | 🔜 Tier 2 | Brief generator doesn't yet read post performance. |

## Environment toggles

| Var | Effect |
|-----|--------|
| `RUNTIME_MODE=mock \| real` | Toggles Slack mocking. |
| `SKIP_TRANSCRIBE=1` | Skips whisper transcription (faster dev/demo; outputs are caption-pending). |
| `ANTHROPIC_API_KEY` | Enables Claude-drafted briefs. Missing → template fallback. |
| `TIMEZONE` | IANA tz for scheduled-for timestamps (default UTC). |

## Troubleshooting

**Brief looks generic:** `content/calendar.yaml` is the seed. If a type has few topics, fillers duplicate. Add 3+ topics per type and the generator will pick better fits.

**Slack post doesn't appear:** bot not in channel. `/invite @Anna Content Engine` in `#anna-content`. Also check `SLACK_CHANNEL_ID` in `.env` matches the channel's ID (right-click channel → details → scroll to bottom).

**Upload watcher returns "No parent_ts":** you haven't posted a brief yet. Run `post-brief.py` before `watch-uploads.py`.

**Whisper takes forever:** first run downloads the base.en model (~140MB). Subsequent runs are fast. For dev, set `SKIP_TRANSCRIBE=1`.

**Subtitles filter breaks on macOS:** ffmpeg's `subtitles` filter needs `libass`. Verify with `ffmpeg -filters | grep subtitles`. If missing: `brew reinstall ffmpeg --with-libass` or let SKIP_TRANSCRIBE=1 bypass it.

**Mock file grows weird:** delete `logs/mock-slack-state.json` between runs to reset the mock store.

## What "ready for Dilani" looks like

The demo passes if:
1. Brief posts cleanly, readable on mobile
2. Phone uploads are detected within 30-60s
3. Processed outputs appear in the thread within ~3 min per clip
4. Approvals flip state correctly
5. Schedule log is coherent

Once that's green: invite Dilani to `#anna-content`, send her a Loom tour, schedule tomorrow's brief with cron, and ship.

## Next steps after the demo

1. Pick scheduling tool (Buffer / Metricool / direct platform APIs). Wire it into `src/scheduler.py` — the data model is already correct.
2. Build comment triage + reply drafting — biggest Tier 2 time-save.
3. Set up a VPS or always-on Mac so briefs fire at 7 AM independent of your laptop state.
4. Eventually: Remotion b-roll splicing for agent-demo clips — reuse `anna-ad-gen`'s UI components.
