import asyncio
import logging
from datetime import datetime, timezone
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from config import Settings
from market import make_exchange, get_snapshot
from analysis import analyse
from risk import approve_trade
from store import save_signal, recent

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("ai-binance-trader")
settings = Settings()
PAUSED = False
LAST_SCAN = "Hələ skan edilməyib"

def owner_only(update: Update) -> bool:
    return bool(settings.owner_id) and str(update.effective_user.id) == settings.owner_id

async def send_owner(app, message: str):
    if settings.owner_id:
        try:
            await app.bot.send_message(chat_id=int(settings.owner_id), text=message)
        except Exception:
            log.exception("Telegram bildirişi göndərilmədi")

def fmt_signal(symbol, market, s, approved, note):
    if s.get("action") not in {"LONG", "SHORT"}:
        return None
    return (
        f"📊 {market.upper()} | {symbol}\n"
        f"Siqnal: {s['action']} | Etibarlılıq: {s.get('confidence', 0)}%\n"
        f"Giriş: {s.get('price', 0):.6g}\n"
        f"Stop-Loss: {s.get('stop_loss', 0):.6g}\n"
        f"Take-Profit: {s.get('take_profit', 0):.6g}\n"
        f"Leverage təklifi: {s.get('leverage', 1)}x\n"
        f"Risk yoxlaması: {'KEÇDİ' if approved else 'İMTİNA'}\n"
        f"Səbəb: {note}\n"
        "Qeyd: Bu versiya TESTNET/analiz üçündür; real ticarət bağlıdır."
    )

def scan_market(symbol: str, futures: bool):
    exchange = make_exchange(settings, futures=futures)
    try:
        market_symbol = symbol
        if futures and ":USDT" not in symbol:
            market_symbol = symbol + ":USDT"
        snapshot = get_snapshot(exchange, market_symbol)
        signal = analyse(snapshot, settings.max_leverage)
        return signal
    finally:
        try: exchange.close()
        except Exception: pass

async def scan_all(app, manual=False):
    global LAST_SCAN
    if PAUSED:
        return "Bot pauzadadır."
    messages = []
    for symbol in settings.symbols:
        for market_name, enabled, futures in (
            ("spot", settings.spot_enabled, False),
            ("futures", settings.futures_enabled, True),
        ):
            if not enabled:
                continue
            try:
                signal = await asyncio.to_thread(scan_market, symbol, futures)
                approved, note, sizing = approve_trade(signal, 100.0, settings)
                save_signal(settings.database_path, symbol, market_name, signal, approved, note)
                text = fmt_signal(symbol, market_name, signal, approved, note)
                if text and (approved or manual):
                    messages.append(text)
            except Exception as exc:
                log.warning("Scan failed for %s %s: %s", market_name, symbol, exc)
    LAST_SCAN = datetime.now(timezone.utc).isoformat()
    if messages:
        for message in messages:
            await send_owner(app, message)
    if manual:
        return "\n\n".join(messages) if messages else "Hazırda təsdiqlənmiş alış/satış siqnalı yoxdur. Bot gözləyir."
    return "Skan tamamlandı."

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not owner_only(update):
        await update.message.reply_text("Bu bot şəxsi idarəetmə üçündür. Sahib hesabı ilə daxil olun.")
        return
    await update.message.reply_text(
        "🤖 AI Binance Trader — TESTNET analiz rejimi\n"
        "/scan — indi bazarı yoxla\n/status — vəziyyət\n/history — son siqnallar\n/pause — skanı dayandır\n/resume — skanı davam etdir\n\n"
        "Real ticarət və pul çıxarma funksiyası bu versiyada bağlıdır."
    )

async def scan_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not owner_only(update): return
    await update.message.reply_text("Bazar çoxqatlı analizdən keçirilir...")
    result = await scan_all(context.application, manual=True)
    await update.message.reply_text(result[:3900])

async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not owner_only(update): return
    await update.message.reply_text(
        f"Rejim: {settings.trading_mode.upper()}\n"
        f"Avtomatik Testnet sifarişi: {'aktiv' if settings.auto_trade_testnet else 'bağlı'}\n"
        f"Spot skanı: {settings.spot_enabled}\nFutures skanı: {settings.futures_enabled}\n"
        f"Leverage həddi: 3x–{settings.max_leverage}x\n"
        f"Risk/əməliyyat: {settings.risk_per_trade_pct}%\n"
        f"Gündəlik stop: {settings.daily_loss_limit_pct}%\n"
        f"Son skan: {LAST_SCAN}\nPauza: {PAUSED}"
    )

async def history_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not owner_only(update): return
    rows = recent(settings.database_path, 10)
    if not rows:
        await update.message.reply_text("Hələ siqnal tarixçəsi yoxdur.")
        return
    lines = ["Son siqnallar:"]
    for row in rows:
        created, symbol, market, action, conf, price, approved, note = row
        lines.append(f"{symbol} {market}: {action or 'WAIT'} | {conf or 0}% | {price or 0} | {'OK' if approved else 'NO'}")
    await update.message.reply_text("\n".join(lines))

async def pause_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global PAUSED
    if not owner_only(update): return
    PAUSED = True
    await update.message.reply_text("Skan dayandırıldı. Açıq Binance mövqelərinə toxunulmur.")

async def resume_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global PAUSED
    if not owner_only(update): return
    PAUSED = False
    await update.message.reply_text("Skan yenidən aktivdir.")

async def scan_loop(app):
    while True:
        try:
            await scan_all(app)
        except Exception:
            log.exception("Skan dövründə xəta")
        await asyncio.sleep(settings.scan_interval)

async def post_init(app):
    app.create_task(scan_loop(app))

def main():
    settings.validate()
    if not settings.telegram_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN dəyişəni təyin edilməyib.")
    app = Application.builder().token(settings.telegram_token).post_init(post_init).build()
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("scan", scan_cmd))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CommandHandler("history", history_cmd))
    app.add_handler(CommandHandler("pause", pause_cmd))
    app.add_handler(CommandHandler("resume", resume_cmd))
    log.info("AI Binance Trader başladı: TESTNET, order placement disabled by default.")
    app.run_polling()

if __name__ == "__main__":
    main()
