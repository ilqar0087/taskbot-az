# Task Worker AZ

Telegram assistant for discovering public open-source bounty issues, listing work platforms, and tracking work notes and payments.

## Telegram commands
- `/start`, `/id`
- `/scan` — searches public GitHub issues for open bounty/reward opportunities; automatic background scan runs every 6 hours and sends only new matches to the owner
- `/opportunities` — shows discovered issues
- `/view ID` — shows details, reward hints, and AI-eligibility classification
- `/tasks` — lists other task marketplaces
- `/done ID note`, `/paid ID amount note`, `/balance`, `/history`

## Railway variables
- `TELEGRAM_BOT_TOKEN` — private Telegram token
- `OWNER_TELEGRAM_ID` — owner's numeric Telegram ID
- `DATABASE_PATH` — use `/data/taskbot.sqlite3` with a persistent volume mounted at `/data`

## Important limitations
- The first live scanner queries GitHub's public Search API; other listed platforms are directory links, not authenticated integrations.
- The bot discovers opportunities and tracks actual payments. It does not create marketplace accounts, submit proposals, click through human-only tasks, or claim work is complete.
- AI-agent permission must be verified in each bounty's own rules. An automated text classifier is only a hint, not proof of permission.
- No income is guaranteed. The balance records only payments the owner manually confirms as received.
- Never pay an upfront fee or connect a wallet to an unverified bounty. Human review is required before starting or submitting any work.
