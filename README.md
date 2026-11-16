# TaskBot AZ

Private Telegram assistant for tracking online-work opportunities and actual received payments.

Commands: /start, /id, /tasks, /done ID note, /paid ID amount note, /balance, /history.

Railway variables:
- TELEGRAM_BOT_TOKEN: Telegram bot token (secret).
- OWNER_TELEGRAM_ID: owner's numeric Telegram user ID.
- DATABASE_PATH: /data/taskbot.sqlite3.

Attach a persistent Railway volume at /data to preserve the ledger across redeploys.

The bot does not generate money by itself. Listed services are external platforms; task availability, eligibility and payouts vary by country and account. The balance only records payments actually received. There are no automatic third-party platform API integrations yet.
