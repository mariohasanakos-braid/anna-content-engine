# Runbook — how to demo this

Goal: show the team (and Dilani) the entire daily loop in ~5 minutes.

## Before the demo (one-time setup)

1. Follow `docs/SLACK_SETUP.md` — creates the Slack app + `#anna-content` channel
2. Clone the repo, `cp .env.example .env`, fill in:
   - `ANTHROPIC_API_KEY`
   - `SLACK_BOT_TOKEN`
   - `SLACK_CHANNEL_ID`
   - `RUNTIME_MODE=real` (or `mock` for local-only demo)
3. `pip install -r requirements.txt`
4. If you want to show Remotion-rendered Anna-agent overlays in the demo: clone `anna-ad-gen` in a sibling directory and `npm install` its `remotion/` project.

## The demo itself (5 minutes)

### Act 1 — Dilani's morning (2 min)

Open Slack on your phone, with `#anna-content` open. Run from the desktop:

```bash
python bin/generate-brief.py --date tomorrow
python bin/post-brief.py --date tomorrow
```

A formatted brief appears in the channel. Show the phone — this is what Dilani sees at 7 AM every day. Three clips. Hook + purpose + target length + delivery notes. She can tap to read, then grab her phone and record.

**Talking point:** "This is the only thing Dilani has to open in the morning. 3 clips, 15-20 minutes of filming."

### Act 2 — Dilani records + uploads (1 min)

On your phone, reply to the brief thread with 3 short sample videos from Photos. Any videos work for the demo — they don't have to be on-topic.

Caption each reply with the clip ID from the brief (`b1`, `b2`, `b3`).

**Talking point:** "Dilani's done. Everything that happens after this is us, not her."

### Act 3 — Processing + output (1.5 min)

Start the watcher on the desktop:

```bash
python bin/watch-uploads.py --date tomorrow
```

It detects uploads, downloads them, processes them (adds captions, cuts to platform-specific versions), and posts back to the same thread. In the demo you'll see 3 "Processed clip 1/3" messages appear, each with 4 platform files attached.

**Talking point:** "We auto-cut the filler, auto-caption, and render platform-specific versions. TikTok gets the full thing, YouTube Shorts gets a 13s teaser and a 60s version, Instagram and Facebook share one file."

### Act 4 — Approval + scheduling (30 sec)

React 👍 on each processed clip in Slack. The approval poller detects the reactions and logs the scheduled posts:

```bash
python bin/watch-approvals.py --date tomorrow
```

Console output:
```
✅ b1 approved — would schedule tiktok @ 7:00 PM, ig-reels+fb-reels @ 12:00 PM, yt-shorts @ 2:00 PM
✅ b2 approved — ...
✅ b3 approved — ...
```

**Talking point:** "Scheduling to the real platforms is a one-line change when we decide which tool (Buffer vs Metricool vs direct platform APIs). Everything upstream of that works today."

## What's stubbed vs real

| Component | Status |
|-----------|--------|
| Brief generator | **Real.** Uses Claude API. |
| Slack poster | **Real** (when `RUNTIME_MODE=real`). Mock mode prints to terminal. |
| Upload watcher | **Real.** Polls the thread every 30s. |
| Clip processor | **Real** for cut + caption. Remotion b-roll splicing is partial (stubbed for non-agent-demo clips). |
| Output poster | **Real.** |
| Approval poller | **Real.** |
| Scheduler | **Stub.** Logs the schedule. Does not actually post. |
| Comment triage | **Not built.** Tier 2. |
| Performance feedback loop | **Not built.** Tier 2. |

## Common demo hiccups

**Brief looks generic:** the brief generator runs on a seeded `content/calendar.yaml`. If that file is empty the output is low-quality. Populate the calendar with at least a few topics before demoing.

**Slack post doesn't appear:** bot not in channel. `/invite @Anna Content Engine` in `#anna-content`.

**Upload watcher doesn't see the file:** files.read scope missing, or the watcher is polling a different channel. Check env.

**Approvals not detected:** reactions.read scope missing. Re-install the app after adding.

## What "ready for Dilani" looks like

The demo passes for the team if:
1. Brief posts cleanly with all 3 clips readable on mobile
2. Phone uploads are detected within 30-60s
3. Processed outputs appear in the thread within ~3 min per clip (whisper + ffmpeg + render time)
4. Approvals flip state correctly on emoji reaction
5. Schedule log is coherent

Once that passes: we send Dilani the channel invite + this runbook + a short Loom showing what her morning looks like. Tomorrow's brief is the first real shoot.

## Next steps after the demo

1. Decide on scheduling tool (Buffer / Metricool / direct platform APIs). Wire it into `src/scheduler.py`.
2. Build comment triage + reply drafting — biggest Tier 2 time-save.
3. Set up a cron on a small VPS (or Mac mini) so briefs post at 7 AM even if Mario's laptop is closed.
