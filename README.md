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
- [ ] Channel plan + scope docs
- [ ] Brief generator (Claude API + content calendar)
- [ ] Slack poster for daily brief
- [ ] Upload watcher
- [ ] Clip processor
- [ ] Output poster + emoji-reaction approval
- [ ] Schedule stub
- [ ] Runbook + demo

Tier 2 (post-MVP):
- [ ] Real platform posting (Buffer/Metricool API)
- [ ] Comment triage + reply drafts
- [ ] Performance feedback loop (posts → briefs)

## Quick start

```bash
cp .env.example .env       # fill in SLACK_BOT_TOKEN, ANTHROPIC_API_KEY
pip install -r requirements.txt
python bin/generate-brief.py --date tomorrow
python bin/post-brief.py --date tomorrow
```

See `docs/SLACK_SETUP.md` for the 5-min Slack app setup.
See `docs/RUNBOOK.md` for the full demo script.

## Docs
- [Channel plan](docs/CHANNEL_PLAN.md) — what we're building this for
- [App scope](docs/SCOPE.md) — full scope of the engine
- [Slack setup](docs/SLACK_SETUP.md) — 5-min Slack app install
- [Runbook](docs/RUNBOOK.md) — demo this to the team
