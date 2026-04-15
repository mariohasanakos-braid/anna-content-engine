# App Scope — Anna Content Engine

## What this app is for

Keep Dilani's time-cost below 45 min/day while shipping 5 high-quality posts per week across 4 platforms. The system is the producer; Dilani is the camera.

## Architecture at a glance

```
┌─────────────────────────┐
│  content/calendar.yaml  │  human-editable content calendar
└──────────┬──────────────┘
           │
           ▼
┌─────────────────────────────────────────┐
│  Brief Generator (Claude API)           │
│  - reads calendar for date              │
│  - reads last 7d performance            │
│  - reads unanswered comment threads     │
│  - picks 3 clips for today              │
│  - drafts hooks/purpose/length/notes    │
└──────────┬──────────────────────────────┘
           │
           ▼
┌─────────────────────────────────────────┐
│  Slack Poster (Block Kit)               │
│  Posts today's brief to #anna-content   │
│  as parent message in a thread          │
└──────────┬──────────────────────────────┘
           │
           ▼  Dilani sees it on mobile
           │
           ▼  Dilani records 3 clips, uploads as thread replies
           │
┌─────────────────────────────────────────┐
│  Upload Watcher (poll thread every 30s) │
│  Downloads new clips to staging/        │
└──────────┬──────────────────────────────┘
           │
           ▼
┌─────────────────────────────────────────┐
│  Clip Processor                         │
│  - Whisper transcription                │
│  - auto-cut filler/silence              │
│  - burn-in captions (Remotion)          │
│  - platform-specific renders            │
│    • TikTok (9:16, full length)         │
│    • Instagram Reels (9:16, ≤90s)       │
│    • Facebook Reels (same as IG)        │
│    • YouTube Shorts (13s + 60s cuts)    │
└──────────┬──────────────────────────────┘
           │
           ▼
┌─────────────────────────────────────────┐
│  Output Poster                          │
│  Uploads processed videos back to       │
│  same Slack thread with approval prompt │
└──────────┬──────────────────────────────┘
           │
           ▼  Dilani / Mario react with emoji
           │  👍 = ship  🔄 = regenerate  ❌ = kill
           │
┌─────────────────────────────────────────┐
│  Approval Poller                        │
│  Polls reactions on output messages     │
│  Triggers schedule or regenerate        │
└──────────┬──────────────────────────────┘
           │
           ▼
┌─────────────────────────────────────────┐
│  Scheduler (Tier 2: real Buffer API;    │
│  Tier 1: logs "would schedule at X")    │
└─────────────────────────────────────────┘
```

## Entry points

All CLI, designed to run from cron or manually. No server required for MVP.

| Script | Purpose | When it runs |
|--------|---------|--------------|
| `bin/generate-brief.py` | Generate brief for a date | Cron: daily at 6:30 AM |
| `bin/post-brief.py` | Post brief to Slack | Cron: daily at 7:00 AM |
| `bin/watch-uploads.py` | Long-running poller for clip uploads | Launchd service |
| `bin/process-clip.py` | Process a specific staged clip | Triggered by watch-uploads |
| `bin/post-outputs.py` | Post processed clips back to thread | Triggered by processor |
| `bin/watch-approvals.py` | Poll reactions, trigger downstream | Long-running |
| `bin/schedule-post.py` | Queue approved posts for scheduling | Triggered by approvals |

## Modules

### `src/brief_generator.py`

Inputs: today's date, content calendar YAML, last 7 days' post performance, unanswered comment queue.

Uses Claude API to:
1. Select 3 clip topics for today maintaining the weekly content-type balance (2 agent-demo, 1 explainer, 1 reaction, 1 pure Dilani over the week)
2. Check recency penalty (don't repeat topic within 14 days)
3. Draft hook line, purpose, target length, delivery notes for each clip
4. Output structured JSON + Slack Block Kit formatted version

Output schema:
```json
{
  "date": "2026-04-16",
  "clips": [
    {
      "id": "b1",
      "type": "agent-demo" | "avatar-explainer" | "reaction" | "pure-dilani",
      "hook": "My Sunday-night brain dump is killing me.",
      "purpose": "Intro for Anna-as-agent demo of weekly planning.",
      "target_length_sec": 10,
      "delivery_notes": "Just the intro. We cut to Anna-agent UI after your line. Keep it conversational, like you're mid-thought.",
      "b_roll_brief": "We'll splice in a Remotion chat demo showing Anna reading your emails and spitting out 3 action cards.",
      "platforms": ["tiktok", "ig-reels", "fb-reels", "yt-shorts"]
    }
  ]
}
```

### `src/slack_client.py`

Thin wrapper over `slack_sdk.WebClient` with:
- Mock mode for dry runs (prints to terminal with same structure)
- Auto-retry with exponential backoff
- Helper methods: `post_brief_message`, `post_output_clip`, `poll_thread_replies`, `poll_reactions`, `download_file`

### `src/slack_watcher.py`

Long-running poller. Every 30s:
1. Calls `conversations.replies` on today's brief thread
2. Diffs against last-seen-reply-ts
3. For new file uploads: downloads via `files.info` + auth'd GET to private URL
4. Writes to `staging/{date}/{clip_id}.mp4`
5. Emits an event → triggers clip processor

### `src/clip_processor.py`

Pipeline per clip:
1. `whisper` transcribe → word-level timestamps
2. `ffmpeg` cut: trim leading/trailing silence, remove "um"s where Whisper low-confidence
3. Generate SRT from transcription
4. If clip is `agent-demo` type: look up matching b-roll spec from brief, render Remotion composition with Dilani clip + Anna-agent UI demo
5. Platform-specific outputs:
   - TikTok: full-length, 9:16, 1080x1920
   - IG/FB Reels: same file (IG cross-posts to FB)
   - YT Shorts: 13s hook-only + full-length versions

Writes to `output/{date}/{clip_id}/{platform}.mp4`.

### `src/output_poster.py`

For each processed clip, posts to the same Slack thread as an attachment with:
- The four platform files as attachments
- Text: "Processed clip 1/3. React 👍 to ship, 🔄 to regenerate, ❌ to kill."
- Metadata in thread storage for approval poller to match reactions

### `src/approval_poller.py`

Polls `reactions.get` on output messages every 30s. State machine:
- `awaiting` → `👍` from both Dilani+Mario → `approved`
- `awaiting` → `🔄` → `regenerate` (re-runs processor with revised params)
- `awaiting` → `❌` → `killed` (skip scheduling)
- `approved` → trigger scheduler

### `src/scheduler.py`

Tier 1 (demo): logs "would schedule clip X to platform Y at time Z based on platform's best posting time." Writes a queue file `output/{date}/schedule.json`.

Tier 2: real posting via Buffer API or Metricool API. Posts at platform-optimized times.

### `content/calendar.yaml`

Human-editable 14-day planning horizon. Example:

```yaml
cadence:
  mon: pure-dilani
  tue: agent-demo
  wed: reaction
  thu: agent-demo
  fri: avatar-explainer
  sat: rest
  sun: rest

topics_pool:
  - id: agentic-parenting-intro
    theme: "What is agentic parenting?"
    used_on: []
    priority: high
  - id: sunday-brain-dump
    theme: "Sunday-night planning session with Anna"
    used_on: [2026-04-13]
    priority: medium
  # ...
```

## Slack workspace + channel layout

- Workspace: Mario's existing BraidApp Slack (or a new one if preferred)
- Channel: `#anna-content`
- Bot invited to channel with scopes: `chat:write`, `files:read`, `channels:history`, `channels:read`, `reactions:read`
- All daily brief threads live in this channel. Nothing else happens here to keep threads findable.

## State / storage

Filesystem-backed, no DB yet:

```
staging/{date}/{clip_id}.mp4          raw Dilani uploads
output/{date}/{clip_id}/tiktok.mp4    processed per platform
output/{date}/{clip_id}/ig.mp4
output/{date}/{clip_id}/yt-13s.mp4
output/{date}/{clip_id}/yt-full.mp4
output/{date}/state.json              brief + approval state
output/{date}/schedule.json           scheduled posts
logs/{date}.log                       everything the day did
```

## Runtime modes

Controlled by `RUNTIME_MODE` env var:

- `mock`: prints everything to terminal, generates real briefs, writes real files, but never hits Slack. For local dev + demo without a Slack app.
- `real`: hits Slack. Requires `SLACK_BOT_TOKEN`.

Every module must gracefully handle both.

## Failure modes we design around

| Failure | Mitigation |
|---------|-----------|
| Dilani records flat / bad audio | Clip processor runs a quick QC (face detected, audio not clipped, duration within target). If fails, posts "reshoot pls" back to thread before she leaves kitchen. |
| Briefs get repetitive | Recency penalty in brief generator: down-weight any topic used in last 14 days. |
| AI voice drift in drafted comments | Weekly "voice check" — agent samples 5 of its own outputs + 5 real Dilani, asks Dilani to rate. |
| Comments get weird | Classifier has `moderation-escalate` bucket that pages Mario (not Dilani). Keeps her attention protected. |
| Post flops | Agent logs it in performance history with retention metrics. Next week's brief generator down-weights the topic cluster. |

## Tiers (what's in scope for this build)

**Tier 1 (this sprint, ~4 hrs target):**
- T0-T3 complete: scaffolding, docs, brief gen, Slack post
- T4-T8 to the extent possible

**Tier 2 (next sprint):**
- Real Buffer/Metricool posting
- Comment triage + reply drafting
- Performance feedback loop (posts → brief generator)

**Tier 3 (later):**
- Voice fine-tuning for drafts
- Multi-host support (Dilani + Mario channels share the engine)
- A/B testing harness for hooks
- Webhook-based Slack integration (so we drop polling)

## Not in scope, ever (unless requirements change)

- SMS / Twilio
- Public web UI for approval
- Anna-as-character chat with users
- Multiple simultaneous brand channels (defer to 10K+)
- HeyGen avatars of real Dilani (banned by strategic plan)
