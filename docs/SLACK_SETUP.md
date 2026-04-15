# Slack Setup (~5 min)

## 1. Create a Slack app

1. Go to https://api.slack.com/apps
2. Click **Create New App** → **From scratch**
3. Name it: `Anna Content Engine`
4. Pick your BraidApp workspace
5. Click **Create App**

## 2. Add bot scopes

Left sidebar → **OAuth & Permissions** → **Bot Token Scopes** → Add these:

| Scope | What for |
|-------|----------|
| `chat:write` | Post briefs and processed clips |
| `files:read` | Download Dilani's uploaded clips |
| `files:write` | Upload processed outputs |
| `channels:history` | Read thread replies (new uploads) |
| `channels:read` | Look up channel info |
| `channels:join` | Auto-join `#anna-content` |
| `reactions:read` | Detect 👍 🔄 ❌ approval reactions |
| `users:read` | Resolve who posted what |

## 3. Install to workspace

Same OAuth & Permissions page → **Install to Workspace** → Allow.

Copy the **Bot User OAuth Token** (starts with `xoxb-`).

## 4. Create the channel

In Slack:
1. Create channel: `#anna-content`
2. Invite the bot: `/invite @Anna Content Engine`

## 5. Get channel ID

Right-click the channel → **View channel details** → scroll to bottom → copy the Channel ID (starts with `C`).

## 6. Drop into `.env`

```env
SLACK_BOT_TOKEN=xoxb-...
SLACK_CHANNEL_ID=C0123456789
SLACK_WORKSPACE_URL=https://braidapp.slack.com
RUNTIME_MODE=real
```

## 7. Verify

```bash
python -c "from src.slack_client import SlackClient; SlackClient().smoke_test()"
```

Should print `✅ Slack client connected. Bot = U123..., Channel = C456...`.

## Adding humans

Dilani and Mario are members of `#anna-content`. They get iOS push notifications when the bot posts. Bot DMs aren't used — everything is public channel for visibility.

## Troubleshooting

**"not_in_channel" error:** bot wasn't invited. Run `/invite @Anna Content Engine` in the channel.

**"missing_scope" error:** the OAuth page requires adding scope + re-installing to workspace. App settings don't auto-update existing installs.

**File downloads 403:** files.read scope missing OR the `url_private_download` wasn't used (use it, not `url_private`).
