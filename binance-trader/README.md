# AI Binance Trader (safe first build)

Telegram-controlled Binance market scanner. It reads public Binance mainnet market data for analysis and alerts; it does not authenticate for trading or place orders.

## Included
- Spot and USDT-M Futures market scans
- 15m / 1h / 4h trade analysis plus 1d / 1w long-horizon opportunity scan
- EMA, RSI, MACD momentum, ATR volatility and volume checks
- Order-book imbalance, spread, funding rate and open-interest snapshot where supported
- Pre-trade risk gate: confidence threshold, risk/reward, position sizing, daily loss limit
- 3x–10x leverage recommendation (not an instruction to use leverage)
- Long-horizon 1d / 1w technical watchlist for roughly 1 week to 1 month
- Binance Simple Earn Flexible/Locked product scanner (read-only API access)
- Daily Earn/bonus summary and manual Telegram /earn command
- Campaign headline filter excludes coupon/voucher-required offers when a verified RSS feed is configured
- SQLite signal history
- Telegram owner-only controls: /scan, /status, /history, /earn, /pause, /resume
- No martingale, no averaging down, no withdrawal permission or withdrawal code

## Safety limits
- `TRADING_MODE` must remain `testnet`; the application refuses any other mode.
- `AUTO_TRADE_TESTNET=false` by default. No orders are placed in this initial build.
- Risk sizing is not approved until a verified account equity is configured; no fictional balance is assumed.
- Spot and Futures signals are analytical alerts from public mainnet data. This release does not place live or testnet orders.
- It does not promise profits or loss-free trading.
- Earn uses Binance production read-only Simple Earn API endpoints for product information; this is separate from Testnet trading. Configure a dedicated API key with read-only permission only. Never enable trading or withdrawals. Product listings do not guarantee your account or region is eligible.
- No Earn subscription, redemption, transfer, order, or withdrawal is executed. You must review and act yourself.
- Bonus campaign headlines are only scanned if a verified official HTTPS RSS feed is configured in BINANCE_ANNOUNCEMENTS_RSS_URL. Until then, bonus alerts are not active. Coupon/voucher-required offers are filtered out.

## Run
1. Create a Telegram bot with BotFather and keep its token private.
2. Copy `.env.example` to `.env`, fill `TELEGRAM_BOT_TOKEN` and your Telegram numeric ID. For Earn product listings, optionally add separate `BINANCE_EARN_API_KEY` and `BINANCE_EARN_API_SECRET` values from a Binance MAINNET key with **read-only permission only**. Do not reuse Testnet keys; never enable trading or withdrawals.
3. Install requirements and run `python main.py`.
4. For Railway, set the same environment variables in the service settings. Mount a persistent volume at `/data`.

## Required before any order execution
A later, separately reviewed release must add and test:
- Binance Spot Testnet OCO exits
- Binance Futures Testnet entry + reduce-only stop/target orders
- Live balance/equity reconciliation and exchange-side daily loss monitoring
- Order idempotency, partial-fill handling, restart recovery and emergency close logic

Never put API keys in source code or chat. Use TESTNET keys only. Do not grant withdrawal permissions.
