# AI Binance Trader (safe first build)

Telegram-controlled Binance market scanner. The initial release is **TESTNET-only** and defaults to analysis/alerts, not order placement.

## Included
- Spot and USDT-M Futures market scans
- 15m / 1h / 4h trade analysis plus 1d / 1w long-horizon opportunity scan
- EMA, RSI, MACD momentum, ATR volatility and volume checks
- Order-book imbalance, spread, funding rate and open-interest snapshot where supported
- Pre-trade risk gate: confidence threshold, risk/reward, position sizing, daily loss limit
- 3x–10x leverage recommendation (not an instruction to use leverage)
- Long-horizon 1d / 1w technical watchlist for roughly 1 week to 1 month
- SQLite signal history
- Telegram owner-only controls: /scan, /status, /history, /pause, /resume
- No martingale, no averaging down, no withdrawal permission or withdrawal code

## Safety limits
- `TRADING_MODE` must remain `testnet`; the application refuses any other mode.
- `AUTO_TRADE_TESTNET=false` by default. No orders are placed in this initial build.
- Risk sizing is not approved until a verified account equity is configured; no fictional balance is assumed.
- Spot and Futures signals are analytical alerts. This release does not yet place live or testnet orders.
- It does not promise profits or loss-free trading.
- Binance Earn, Launchpool, Megadrop and bonus campaigns are not auto-subscribed. The first version does not use coupons; campaign discovery needs a separate account/region eligibility integration.

## Run
1. Create a Telegram bot with BotFather and keep its token private.
2. Copy `.env.example` to `.env`, fill `TELEGRAM_BOT_TOKEN` and your Telegram numeric ID.
3. Install requirements and run `python main.py`.
4. For Railway, set the same environment variables in the service settings. Mount a persistent volume at `/data`.

## Required before any order execution
A later, separately reviewed release must add and test:
- Binance Spot Testnet OCO exits
- Binance Futures Testnet entry + reduce-only stop/target orders
- Live balance/equity reconciliation and exchange-side daily loss monitoring
- Order idempotency, partial-fill handling, restart recovery and emergency close logic

Never put API keys in source code or chat. Use TESTNET keys only. Do not grant withdrawal permissions.
