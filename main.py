import logging
import os
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

TOKEN = (os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("BOT_TOKEN") or "").strip()
OWNER = (os.getenv("OWNER_TELEGRAM_ID") or "").strip()
DB_PATH = os.getenv("DATABASE_PATH", "/data/taskbot.sqlite3")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("task-worker")

APPS = {
    "gold": ("Gold Diggers", 25),
    "arctic": ("Arctic Rush", 25),
    "lumber": ("Lumberjack", 24),
    "task": ("Task Worker AZ tapşırıqları", 0),
}
BTC_ADDRESS_RE = re.compile(r"^(bc1[ac-hj-np-z02-9]{11,71}|[13][a-km-zA-HJ-NP-Z1-9]{25,34})$")

def now_local():
    return datetime.now(timezone(timedelta(hours=4))).isoformat(timespec="seconds")

def connect():
    path = Path(DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(path))
    db.row_factory = sqlite3.Row
    return db

def init_db():
    with connect() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS tracker_email_accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL UNIQUE COLLATE NOCASE,
            created TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS tracker_app_status (
            account_id INTEGER NOT NULL,
            app_key TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            updated TEXT NOT NULL,
            PRIMARY KEY(account_id, app_key),
            FOREIGN KEY(account_id) REFERENCES tracker_email_accounts(id)
        );
        CREATE TABLE IF NOT EXISTS tracker_earnings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            app_key TEXT NOT NULL,
            account_id INTEGER,
            satoshis INTEGER NOT NULL CHECK(satoshis >= 0),
            ads_count INTEGER NOT NULL DEFAULT 0 CHECK(ads_count >= 0),
            note TEXT NOT NULL DEFAULT '',
            created TEXT NOT NULL,
            FOREIGN KEY(account_id) REFERENCES tracker_email_accounts(id)
        );
        CREATE TABLE IF NOT EXISTS tracker_wallet (
            id INTEGER PRIMARY KEY CHECK(id = 1),
            address TEXT NOT NULL,
            updated TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS tracker_lightning_wallet (
            id INTEGER PRIMARY KEY CHECK(id = 1),
            address TEXT NOT NULL,
            updated TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS tracker_app_withdrawals (id INTEGER PRIMARY KEY AUTOINCREMENT, account_id INTEGER NOT NULL, app_key TEXT NOT NULL, satoshis INTEGER NOT NULL CHECK(satoshis >= 20), reference TEXT NOT NULL, created TEXT NOT NULL, FOREIGN KEY(account_id) REFERENCES tracker_email_accounts(id));
        CREATE TABLE IF NOT EXISTS tracker_withdrawals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            satoshis INTEGER NOT NULL CHECK(satoshis > 0),
            txid TEXT NOT NULL,
            created TEXT NOT NULL
        );
        """)

async def allowed(update: Update):
    user = update.effective_user
    chat = update.effective_chat
    if not OWNER or not user or str(user.id) != OWNER:
        if update.effective_message:
            await update.effective_message.reply_text(
                "Bot hələ sahib Telegram ID-si ilə məhdudlaşdırılmayıb və ya bu hesab sahib deyil. "
                "Railway-də OWNER_TELEGRAM_ID dəyişənini yoxla."
            )
        return False
    if not chat or chat.type != "private":
        if update.effective_message:
            await update.effective_message.reply_text("Təhlükəsizlik üçün botdan şəxsi çatda istifadə et.")
        return False
    return True

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await allowed(update):
        return
    await update.effective_message.reply_text(
        "🤖 TASK WORKER AZ — QAZANC İZLƏYİCİ\n\n"
        "Tətbiqlər: Gold Diggers, Arctic Rush, Lumberjack və Task Worker AZ tapşırıqları.\n"
        "Gündəlik hədəf: 25 + 25 + 24 = 74 reklam (hədəfdir, məcburi limit deyil).\n"
        "BTC və Lightning ünvanları ayrıca saxlanılır. Qazanc və çıxarışlar əl ilə qeyd olunur.\n\n"
        "/apps — tətbiqlər və hədəflər\n"
        "/email add email@gmail.com — e-poçt profili əlavə et\n"
        "/email list — profilləri göstər\n"
        "/appstatus set 1 gold active — profilin tətbiq statusunu qeyd et\n"
        "/appstatus list 1 — profilin tətbiq statuslarını göstər\n"
        "/record gold 1 120 20 qeyd — 120 satoshi və 20 reklamı qeyd et\n"
        "/record task - 500 0 tapşırıq qazancı\n"
        "/balance — ümumi balans\n"
        "/today — bugünkü qeydlər\n"
        "/wallet — BTC ünvanına bax\n"
        "/wallet set BTC_UNVANI — Bitcoin ünvanını yaz\n"
        "/lightning — Lightning ünvanına bax\n"
        "/lightning set EMAIL@DOMAIN — Lightning ünvanını yaz\n"
        "/ready — 20 satoshi həddinə çatanlar\n"
        "/withdrawapp ID gold|arctic|lumber 20 QEBZ — real çıxarışı qeyd et\n"
        "/withdraw SATOSHI TXID — edilmiş çıxarışı qeyd et\n"
        "/history — tarixçə\n"
        "/help — kömək"
    )

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)

async def apps(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await allowed(update):
        return
    lines = ["📋 TƏTBİQLƏR VƏ GÜNDƏLİK HƏDƏFLƏR"]
    for key, (name, target) in APPS.items():
        target_text = f"{target} reklam" if target else "tapşırıq qeydi"
        lines.append(f"• {name} — {target_text} (dəyişən hədəf)")
    lines.append("\nHədəflər plan üçündür. Faktiki reklam sayı və mükafat tətbiqin özündə təsdiqlənməlidir.")
    await update.effective_message.reply_text("\n".join(lines))

async def email_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await allowed(update):
        return
    args = context.args
    if not args or args[0].lower() == "list":
        with connect() as db:
            rows = db.execute("SELECT id,email FROM tracker_email_accounts ORDER BY id").fetchall()
        if not rows:
            await update.effective_message.reply_text("Hələ e-poçt profili əlavə edilməyib. /email add email@gmail.com")
            return
        await update.effective_message.reply_text(
            "📧 E-POÇT PROFİLLƏRİ\n" + "\n".join(f"{r['id']}. {r['email']}" for r in rows) +
            "\n\nYalnız ünvan saxlanılır; parol və giriş kodu istənilmir."
        )
        return
    if args[0].lower() == "add" and len(args) == 2:
        email = args[1].strip().lower()
        if len(email) > 254 or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
            await update.effective_message.reply_text("E-poçt ünvanı düzgün deyil.")
            return
        try:
            with connect() as db:
                cur = db.execute("INSERT INTO tracker_email_accounts(email,created) VALUES(?,?)", (email, now_local()))
                account_id = cur.lastrowid
            await update.effective_message.reply_text(f"Əlavə edildi: profil #{account_id} — {email}")
        except sqlite3.IntegrityError:
            await update.effective_message.reply_text("Bu e-poçt artıq siyahıdadır.")
        return
    await update.effective_message.reply_text("İstifadə: /email add email@gmail.com və ya /email list")


async def appstatus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await allowed(update):
        return
    args = context.args
    if not args:
        await update.effective_message.reply_text(
            "İstifadə: /appstatus set EMAIL_ID gold|arctic|lumber active|pending|unavailable|closed\n"
            "və ya: /appstatus list EMAIL_ID"
        )
        return
    action = args[0].lower()
    if action == "set" and len(args) == 4:
        try:
            account_id = int(args[1])
        except ValueError:
            await update.effective_message.reply_text("EMAIL_ID rəqəm olmalıdır. /email list yaz.")
            return
        app_key, status = args[2].lower(), args[3].lower()
        if app_key not in ("gold", "arctic", "lumber"):
            await update.effective_message.reply_text("Tətbiq gold, arctic və ya lumber olmalıdır.")
            return
        if status not in ("active", "pending", "unavailable", "closed"):
            await update.effective_message.reply_text("Status active, pending, unavailable və ya closed olmalıdır.")
            return
        with connect() as db:
            exists = db.execute("SELECT email FROM tracker_email_accounts WHERE id=?", (account_id,)).fetchone()
            if not exists:
                await update.effective_message.reply_text("Profil tapılmadı. /email list yaz.")
                return
            db.execute(
                "INSERT INTO tracker_app_status(account_id,app_key,status,updated) VALUES(?,?,?,?) "
                "ON CONFLICT(account_id,app_key) DO UPDATE SET status=excluded.status,updated=excluded.updated",
                (account_id, app_key, status, now_local())
            )
        await update.effective_message.reply_text(
            f"✅ Status qeyd edildi: profil #{account_id} ({exists['email']}) — "
            f"{APPS[app_key][0]}: {status}"
        )
        return
    if action == "list" and len(args) == 2:
        try:
            account_id = int(args[1])
        except ValueError:
            await update.effective_message.reply_text("EMAIL_ID rəqəm olmalıdır.")
            return
        with connect() as db:
            email = db.execute("SELECT email FROM tracker_email_accounts WHERE id=?", (account_id,)).fetchone()
            rows = db.execute(
                "SELECT app_key,status,updated FROM tracker_app_status WHERE account_id=? ORDER BY app_key",
                (account_id,)
            ).fetchall()
        if not email:
            await update.effective_message.reply_text("Profil tapılmadı. /email list yaz.")
            return
        lines = [f"📱 TƏTBİQ STATUSLARI — {email['email']}"]
        status_map = {r["app_key"]: r["status"] for r in rows}
        for key in ("gold", "arctic", "lumber"):
            lines.append(f"• {APPS[key][0]}: {status_map.get(key, 'qeyd edilməyib')}")
        await update.effective_message.reply_text("\n".join(lines))
        return
    await update.effective_message.reply_text(
        "İstifadə: /appstatus set EMAIL_ID gold|arctic|lumber active|pending|unavailable|closed "
        "və ya /appstatus list EMAIL_ID"
    )

async def record(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await allowed(update):
        return
    args = context.args
    if len(args) < 3:
        await update.effective_message.reply_text(
            "İstifadə: /record gold|arctic|lumber|task EMAIL_ID|- SATOSHI [REKLAM_SAYI] [QEYD]"
        )
        return
    app_key = args[0].lower()
    if app_key not in APPS:
        await update.effective_message.reply_text("Mənbə gold, arctic, lumber və ya task olmalıdır.")
        return
    try:
        account_id = None if args[1] == "-" else int(args[1])
        satoshis = int(args[2])
        ads_count = int(args[3]) if len(args) >= 4 else 0
        if satoshis < 0 or ads_count < 0:
            raise ValueError
    except ValueError:
        await update.effective_message.reply_text("Satoshi, reklam sayı və profil ID-si tam müsbət ədədlər olmalıdır.")
        return
    if app_key != "task" and account_id is None:
        await update.effective_message.reply_text("Bu tətbiq üçün e-poçt profil ID-si lazımdır. Əvvəl /email list yaz.")
        return
    note = " ".join(args[4:]) if len(args) >= 5 else ""
    with connect() as db:
        if account_id is not None:
            exists = db.execute("SELECT 1 FROM tracker_email_accounts WHERE id=?", (account_id,)).fetchone()
            if not exists:
                await update.effective_message.reply_text("Profil tapılmadı. /email list yaz.")
                return
        cur = db.execute(
            "INSERT INTO tracker_earnings(app_key,account_id,satoshis,ads_count,note,created) VALUES(?,?,?,?,?,?)",
            (app_key, account_id, satoshis, ads_count, note, now_local())
        )
    await update.effective_message.reply_text(
        f"✅ Qeyd edildi: #{cur.lastrowid}\n{APPS[app_key][0]}\n"
        f"Qazanc: {satoshis:,} satoshi\nReklam: {ads_count}\n"
        "Qeyd: bu, sənin daxil etdiyin qeyddir; tətbiq balansı ayrıca yoxlanmalıdır."
    )

async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await allowed(update):
        return
    with connect() as db:
        total = db.execute("SELECT COALESCE(SUM(satoshis),0) FROM tracker_earnings").fetchone()[0]
        withdrawn = db.execute("SELECT COALESCE(SUM(satoshis),0) FROM tracker_withdrawals").fetchone()[0]
        rows = db.execute(
            "SELECT app_key,COALESCE(SUM(satoshis),0) AS sats,COALESCE(SUM(ads_count),0) AS ads "
            "FROM tracker_earnings GROUP BY app_key ORDER BY app_key"
        ).fetchall()
    lines = ["💰 BALANS", f"Qeydə alınmış qazanc: {total:,} satoshi", f"Qeydə alınmış çıxarış: {withdrawn:,} satoshi",
             f"Qalan qeydiyyat balansı: {max(total-withdrawn,0):,} satoshi", ""]
    for r in rows:
        lines.append(f"• {APPS[r['app_key']][0]}: {r['sats']:,} satoshi | {r['ads']} reklam")
    lines.append("\nBu balans yalnız əl ilə daxil edilmiş qeydlərin cəmidir; blokçeyn balansı deyil.")
    await update.effective_message.reply_text("\n".join(lines))

async def today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await allowed(update):
        return
    day = datetime.now(timezone(timedelta(hours=4))).date().isoformat()
    with connect() as db:
        rows = db.execute(
            "SELECT app_key,SUM(satoshis) AS sats,SUM(ads_count) AS ads,COUNT(*) AS entries "
            "FROM tracker_earnings WHERE substr(created,1,10)=? GROUP BY app_key ORDER BY app_key", (day,)
        ).fetchall()
    if not rows:
        await update.effective_message.reply_text("Bu gün hələ qazanc qeydi yoxdur.")
        return
    lines = ["📅 BUGÜNKÜ QEYDLƏR"]
    for r in rows:
        lines.append(f"• {APPS[r['app_key']][0]}: {r['sats']:,} satoshi, {r['ads']} reklam, {r['entries']} qeyd")
    await update.effective_message.reply_text("\n".join(lines))

async def wallet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await allowed(update):
        return
    args = context.args
    if args and args[0].lower() == "set" and len(args) == 2:
        address = args[1].strip()
        if not BTC_ADDRESS_RE.fullmatch(address):
            await update.effective_message.reply_text("BTC ünvanı formatı tanınmadı. Ünvanı yoxla; şəxsi açar və seed phrase göndərmə.")
            return
        with connect() as db:
            db.execute(
                "INSERT INTO tracker_wallet(id,address,updated) VALUES(1,?,?) "
                "ON CONFLICT(id) DO UPDATE SET address=excluded.address,updated=excluded.updated",
                (address, now_local())
            )
        await update.effective_message.reply_text("✅ Ümumi Bitcoin qəbul ünvanı saxlanıldı. Bot bu ünvana avtomatik köçürmə etmir.")
        return
    with connect() as db:
        row = db.execute("SELECT address FROM tracker_wallet WHERE id=1").fetchone()
    await update.effective_message.reply_text(
        "Ümumi BTC ünvanı: " + (row["address"] if row else "hələ əlavə edilməyib") +
        "\nBot yalnız ünvanı saxlayır; pul göndərmir və private key saxlamır."
    )


async def lightning(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await allowed(update):
        return
    args = context.args
    if args and args[0].lower() == "set" and len(args) == 2:
        address = args[1].strip()
        if len(address) > 254 or not re.fullmatch(r"[^@\\s]+@[^@\\s]+\\.[^@\\s]+", address):
            await update.effective_message.reply_text(
                "Lightning ünvanının formatı düzgün görünmür. Məsələn: name@walletofsatoshi.com"
            )
            return
        with connect() as db:
            db.execute(
                "INSERT INTO tracker_lightning_wallet(id,address,updated) VALUES(1,?,?) "
                "ON CONFLICT(id) DO UPDATE SET address=excluded.address,updated=excluded.updated",
                (address, now_local())
            )
        await update.effective_message.reply_text(
            "✅ Wallet of Satoshi Lightning ünvanı saxlanıldı. Bu, BTC on-chain ünvanından ayrıdır. "
            "Bot avtomatik ödəniş göndərmir."
        )
        return
    with connect() as db:
        row = db.execute("SELECT address FROM tracker_lightning_wallet WHERE id=1").fetchone()
    await update.effective_message.reply_text(
        "Lightning ünvanı: " + (row["address"] if row else "hələ əlavə edilməyib") +
        "\\nBu ünvan yalnız saxlanılır; bot ödəniş göndərmir."
    )

async def withdraw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await allowed(update):
        return
    if len(context.args) != 2:
        await update.effective_message.reply_text("İstifadə: /withdraw SATOSHI TXID — yalnız artıq edilmiş çıxarışı qeyd etmək üçündür.")
        return
    try:
        sats = int(context.args[0])
        txid = context.args[1].strip()
        if sats <= 0 or len(txid) < 20 or len(txid) > 150:
            raise ValueError
    except ValueError:
        await update.effective_message.reply_text("Məbləğ müsbət satoshi, TXID isə real əməliyyat hash-i olmalıdır.")
        return
    with connect() as db:
        db.execute("INSERT INTO tracker_withdrawals(satoshis,txid,created) VALUES(?,?,?)", (sats, txid, now_local()))
    await update.effective_message.reply_text(f"Çıxarış qeydə alındı: {sats:,} satoshi. TXID: {txid}")

async def ready_withdrawals(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await allowed(update): return
    with connect() as db:
        rows = db.execute("SELECT a.id,a.email,e.app_key,COALESCE(SUM(e.satoshis),0)-COALESCE((SELECT SUM(w.satoshis) FROM tracker_app_withdrawals w WHERE w.account_id=a.id AND w.app_key=e.app_key),0) AS available FROM tracker_email_accounts a JOIN tracker_earnings e ON e.account_id=a.id WHERE e.app_key IN ('gold','arctic','lumber') GROUP BY a.id,a.email,e.app_key HAVING available >= 20 ORDER BY a.id,e.app_key").fetchall()
    if not rows:
        await update.effective_message.reply_text("Hələ 20 satoshi həddinə çatan profil yoxdur."); return
    lines = ["⚡ 20 SATOSHI HƏDDİNƏ ÇATANLAR", "Bu siyahı çıxarışa hazır balansı göstərir; pul avtomatik göndərilmir."]
    for r in rows: lines.append(f"#{r['id']} {r['email']} | {APPS[r['app_key']][0]}: {r['available']} sat")
    await update.effective_message.reply_text("\n".join(lines))

async def app_withdrawal_record(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await allowed(update): return
    args = context.args
    if len(args) != 4:
        await update.effective_message.reply_text("İstifadə: /withdrawapp EMAIL_ID gold|arctic|lumber SATOSHI QEBZ — yalnız real çıxarışdan sonra."); return
    try:
        account_id, app_key, sats, reference = int(args[0]), args[1].lower(), int(args[2]), args[3].strip()
        if app_key not in ('gold','arctic','lumber') or sats < 20 or len(reference) < 3: raise ValueError
    except ValueError:
        await update.effective_message.reply_text("Məlumat düzgün deyil; minimum 20 satoshi və qəbz istinadı lazımdır."); return
    with connect() as db:
        email = db.execute("SELECT email FROM tracker_email_accounts WHERE id=?", (account_id,)).fetchone()
        earned = db.execute("SELECT COALESCE(SUM(satoshis),0) FROM tracker_earnings WHERE account_id=? AND app_key=?", (account_id,app_key)).fetchone()[0]
        withdrawn = db.execute("SELECT COALESCE(SUM(satoshis),0) FROM tracker_app_withdrawals WHERE account_id=? AND app_key=?", (account_id,app_key)).fetchone()[0]
        if not email or sats > earned-withdrawn:
            await update.effective_message.reply_text("Profil yoxdur və ya qeydiyyat balansı kifayət etmir."); return
        db.execute("INSERT INTO tracker_app_withdrawals(account_id,app_key,satoshis,reference,created) VALUES(?,?,?,?,?)", (account_id,app_key,sats,reference,now_local()))
    await update.effective_message.reply_text(f"Çıxarış qeydə alındı: {email['email']} — {sats} satoshi. Bu qeyd pul köçürmür.")

async def history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await allowed(update):
        return
    with connect() as db:
        earnings = db.execute(
            "SELECT e.id,e.app_key,e.satoshis,e.ads_count,e.note,e.created,a.email "
            "FROM tracker_earnings e LEFT JOIN tracker_email_accounts a ON a.id=e.account_id "
            "ORDER BY e.id DESC LIMIT 12"
        ).fetchall()
        withdrawals = db.execute("SELECT satoshis,txid,created FROM tracker_withdrawals ORDER BY id DESC LIMIT 5").fetchall()
    lines = ["🧾 SON QAZANC QEYDLƏRİ"]
    for r in earnings:
        lines.append(f"#{r['id']} {APPS[r['app_key']][0]}: +{r['satoshis']:,} sat | {r['ads_count']} reklam | {r['email'] or 'profil yoxdur'} | {r['created']}")
    if not earnings:
        lines.append("Hələ qazanc qeydi yoxdur.")
    lines.append("\nÇIXARIŞLAR")
    for r in withdrawals:
        lines.append(f"-{r['satoshis']:,} sat | {r['txid']} | {r['created']}")
    if not withdrawals:
        lines.append("Hələ çıxarış qeydi yoxdur.")
    await update.effective_message.reply_text("\n".join(lines))

def main():
    if not TOKEN:
        raise RuntimeError("BOT_TOKEN və ya TELEGRAM_BOT_TOKEN Railway-də təyin edilməyib.")
    init_db()
    app = Application.builder().token(TOKEN).build()
    for command, handler in [
        ("start", start), ("help", help_cmd), ("apps", apps), ("email", email_cmd), ("appstatus", appstatus),
        ("record", record), ("balance", balance), ("today", today), ("wallet", wallet),
        ("lightning", lightning), ("withdraw", withdraw), ("ready", ready_withdrawals), ("withdrawapp", app_withdrawal_record), ("history", history),
    ]:
        app.add_handler(CommandHandler(command, handler))
    log.info("Task Worker AZ earnings tracker started")
    app.run_polling()

if __name__ == "__main__":
    main()
