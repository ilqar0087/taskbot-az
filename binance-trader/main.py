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
from earn import fetch_earn_products, fetch_campaign_headlines, format_earn_report

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("ai-binance-trader")
settings = Settings()
PAUSED = False
LAST_SCAN = "Hələ skan edilməyib"
LAST_EARN_SCAN = None

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
    leverage_text = "Spot — leverage yoxdur" if market == "spot" else str(s.get("leverage", 1)) + "x"
    return (
        f"📊 {market.upper()} | {symbol}\n"
        f"Siqnal: {s['action']} | Etibarlılıq: {s.get('confidence', 0)}%\n"
        f"Giriş: {s.get('price', 0):.6g}\n"
        f"Stop-Loss: {s.get('stop_loss', 0):.6g}\n"
        f"Take-Profit: {s.get('take_profit', 0):.6g}\n"
        f"Leverage: {leverage_text}\n"
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
                if market_name == "futures":
                    approved, note, sizing = approve_trade(signal, settings.risk_equity_usd, settings)
                else:
                    approved, note, sizing = False, "Spot hazırda yalnız siqnal rejimindədir; sifariş açılmır.", {}
                notify = save_signal(settings.database_path, symbol, market_name, signal, approved, note)
                text = fmt_signal(symbol, market_name, signal, approved, note)
                if text and notify:
                    messages.append(text)
                if notify and market_name == "spot" and signal.get("long_term_action") == "BUY":
                    zone = signal.get("long_term_buy_zone")
                    zone_text = f"{zone[0]} – {zone[1]}" if zone else "hesablanmayıb"
                    messages.append(
                        f"🧭 UZUNMÜDDƏTLİ ALIŞ İZLƏMƏSİ | {symbol}\n"
                        f"Müddət: {signal.get('long_term_horizon')}\n"
                        f"Etibarlılıq balı: {signal.get('long_term_confidence')}%\n"
                        f"İzlənəcək zona: {zone_text}\n"
                        "Bu yalnız xəbərdarlıqdır; avtomatik alış etmir."
                    )
            except Exception as exc:
                log.warning("Scan failed for %s %s: %s", market_name, symbol, exc)
    LAST_SCAN = datetime.now(timezone.utc).isoformat()
    if messages:
        for message in messages:
            await send_owner(app, message)
    if manual:
        return "\n\n".join(messages) if messages else "Hazırda təsdiqlənmiş alış/satış siqnalı yoxdur. Bot gözləyir."
    return "Skan tamamlandı."

async def earn_report():
    products = await asyncio.to_thread(fetch_earn_products, settings.earn_api_key, settings.earn_api_secret)
    feed_url = __import__("os").getenv("BINANCE_ANNOUNCEMENTS_RSS_URL", "")
    campaigns = await asyncio.to_thread(fetch_campaign_headlines, feed_url) if feed_url else []
    return format_earn_report(products, campaigns)

async def earn_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not owner_only(update): return
    await update.message.reply_text("Binance Earn və kampaniya imkanları yoxlanılır...")
    try:
        report = await earn_report()
        await update.message.reply_text(report[:3900], disable_web_page_preview=True)
    except Exception as exc:
        await update.message.reply_text(f"Earn məlumatı alınmadı: {str(exc)[:500]}")

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not owner_only(update):
        await update.message.reply_text("Bu bot şəxsi idarəetmə üçündür. Sahib hesabı ilə daxil olun.")
        return
    await update.message.reply_text(
        "🤖 AI Binance Trader — TESTNET analiz rejimi\n"
        "/scan — indi bazarı yoxla\n/earn — Earn və bonusları yoxla\n/status — vəziyyət\n/history — son siqnallar\n/pause — skanı dayandır\n/resume — skanı davam etdir\n\n"
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
        f"Risk hesablaması üçün equity: ${settings.risk_equity_usd:.2f}\n"
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
    global LAST_EARN_SCAN
    while True:
        try:
            await scan_all(app)
        except Exception:
            log.exception("Skan dövründə xəta")
        now = datetime.now(timezone.utc)
        if LAST_EARN_SCAN is None or (now - LAST_EARN_SCAN).total_seconds() >= 86400:
            try:
                await send_owner(app, await earn_report())
            except Exception as exc:
                await send_owner(app, "Earn yoxlaması üçün read-only Binance API açarı tələb olunur. /earn ilə əl ilə də yoxlaya bilərsən. " + str(exc)[:250])
            LAST_EARN_SCAN = now
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
    app.add_handler(CommandHandler("earn", earn_cmd))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CommandHandler("history", history_cmd))
    app.add_handler(CommandHandler("pause", pause_cmd))
    app.add_handler(CommandHandler("resume", resume_cmd))
    log.info("AI Binance Trader başladı: TESTNET, order placement disabled by default.")
    app.run_polling()

if __name__ == "__main__":
    main()
