import asyncio
import json
import logging
import os
import re
import sqlite3
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip() or os.getenv("BOT_TOKEN", "").strip()
OWNER = os.getenv("OWNER_TELEGRAM_ID", "")
DB = os.getenv("DATABASE_PATH", "/data/taskbot.sqlite3")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("task-worker")

SITES = [
    ("Microworkers", "https://www.microworkers.com/", "Kiçik onlayn tapşırıqlar. Ödəniş üsulu, minimum çıxarış və KYC-ni hesabda yoxla; tapşırıq sayı ölkəyə görə dəyişir."),
    ("Mindrift", "https://www.mindrift.ai/", "AI mətn qiymətləndirmə və təlim layihələri. Azərbaycan üzrə qəbul və ödəniş üsulunu əvvəlcədən təsdiqlə."),
    ("Clickworker", "https://www.clickworker.com/clickworker/", "Mikrotapşırıqlar və AI data işi. Azərbaycan qeydiyyatı və ödəniş üsulu Payment details bölməsində təsdiqlənməlidir."),
    ("CrowdGen by Appen", "https://crowdgen.com/", "AI data layihələri. Layihənin Azərbaycana açıq olmasını və ödəniş metodunu hər elanda yoxla."),
    ("Work.az", "https://work.az/", "Azərbaycan üzrə yerli işlər. Müştəri ilə qiyməti, son tarixi və ödənişi yazılı razılaşdır."),
    ("Upwork", "https://www.upwork.com/", "Beynəlxalq freelance layihələr. Komissiya və Azərbaycanda işləyən çıxarış üsulunu əvvəlcədən yoxla."),
    ("Fiverr", "https://www.fiverr.com/", "Xidmət satışı. Sifarişlər insan təsdiqi ilə; Azərbaycanda işləyən çıxarış metodunu yoxla."),
    ("GitHub Bounties", "https://github.com/issues?q=is%3Aissue+is%3Aopen+bounty", "Yalnız real pul məbləği, açıq issue və təsdiqlənən orijinal mənbə olan bounty elanları."),
    ("FaucetPay", "https://faucetpay.io/", "Kripto mikro-cüzdanıdır; özü işəgötürən deyil. Faucet, PTC və offerwall tapşırıqları üçüncü tərəflərdən gəlir. Bot yalnız qaydaların açıq icazə verdiyi API-ləri avtomatlaşdıra bilər."),
    ("Algora", "https://algora.io/", "Açıq mənbə bounty-ləri. Pul mükafatı, uyğunluq və payout şərtlərini hər işdə yoxla."),
]

GITHUB_QUERIES = [
    "is:issue is:open label:bounty",
    "is:issue is:open bounty",
    'is:issue is:open "reward" "USDC"',
]
HUMAN_ONLY = ("no ai", "no automation", "human only", "human-only", "must be done manually", "no bots")
AGENT_PERMISSION = ("ai agents are welcome", "ai agents may", "agents are explicitly allowed", "autonomous agents are allowed", "agent submissions are allowed", "bot submissions are allowed", "automation is explicitly allowed")
JUNK_PHRASES = ("banana pudding", "bananarmonics", "stereogustatory", "recursive ontological singularity", "five-fold esoteric", "opire singularity council")
NO_CASH_PHRASES = (
    "no cash allocated", "does not currently have cash", "no cash reward",
    "not a cash bounty", "cash is not guaranteed", "cash not guaranteed",
    "deferred ledger", "recognition-only", "recognition only", "token-only",
    "paid in tokens", "token reward only", "no monetary reward", "no payment",
    "unpaid", "volunteer", "for recognition only"
)
MONEY_RE = re.compile(r"\$\s?([0-9][0-9,]*(?:\.\d{1,2})?)\s?([kKmM]?)|([0-9][0-9,]*(?:\.\d{1,2})?)\s?(USDC|USD|ETH|SOL)", re.I)
SOURCE_URL_RE = re.compile(r"https?://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/issues/\d+", re.I)

def extract_source_url(body, fallback):
    match = SOURCE_URL_RE.search(body or "")
    return match.group(0).rstrip(").,") if match else fallback

def parse_reward(title, body):
    clean_body = re.split(r"积分币奖励|coin reward", body or "", flags=re.I)[0]
    candidates = []
    for line in (title + "\n" + clean_body).splitlines():
        if re.search(r"real reward|cash reward|bounty|reward|赏金", line, re.I):
            for match in MONEY_RE.finditer(line):
                if match.group(1):
                    amount = float(match.group(1).replace(",", ""))
                    suffix = (match.group(2) or "").lower()
                    amount *= 1000 if suffix == "k" else 1000000 if suffix == "m" else 1
                    candidates.append(amount)
                elif match.group(3) and (match.group(4) or "").upper() in ("USD", "USDC"):
                    candidates.append(float(match.group(3).replace(",", "")))
    if not candidates:
        return "Mükafat təsdiqlənməyib"
    amount = max(candidates)
    return "$" + format(amount, ",.0f") if amount % 1 == 0 else "$" + format(amount, ",.2f")

def classify_eligibility(text):
    lowered = (text or "").lower()
    if any(word in lowered for word in HUMAN_ONLY):
        return "HUMAN_ONLY — avtomatlaşdırma etmə"
    if any(phrase in lowered for phrase in AGENT_PERMISSION):
        return "AGENT_ALLOWED — yenə də platforma qaydalarını yoxla"
    return "REVIEW_REQUIRED — AI agent icazəsi açıq təsdiqlənməyib"

def verify_github_issue(url):
    match = re.match(r"https?://github\.com/([^/]+)/([^/]+)/issues/(\d+)", url or "")
    if not match:
        return False, "Orijinal GitHub issue linki tapılmadı"
    owner, repo, number = match.groups()
    api_url = "https://api.github.com/repos/%s/%s/issues/%s" % (owner, repo, number)
    req = urllib.request.Request(api_url, headers={"Accept": "application/vnd.github+json", "User-Agent": "TaskWorkerAZ/2.0"})
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            issue = json.loads(response.read().decode("utf-8"))
        if issue.get("state") != "open" or issue.get("pull_request"):
            return False, "Orijinal elan açıq deyil və ya issue deyil"
        if issue.get("assignees"):
            return False, "Orijinal elan artıq icraçıya təyin edilib"
        content = (issue.get("title") or "") + "\n" + (issue.get("body") or "")
        if any(term in content.lower() for term in NO_CASH_PHRASES):
            return False, "Elan nağd pul ödənişi deyil və ya ödəniş təmin edilməyib"
        return True, content
    except Exception as exc:
        return False, "Orijinal elan yoxlanmadı (%s)" % type(exc).__name__


def mode_keyboard(mode="demo"):
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(("✅ " if mode == "demo" else "") + "🧪 DEMO", callback_data="task_mode_demo"),
        InlineKeyboardButton(("✅ " if mode == "real" else "") + "🚀 REAL", callback_data="task_mode_real"),
    ]])



def connect():
    Path(DB).parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB)
    db.row_factory = sqlite3.Row
    db.executescript("""
    CREATE TABLE IF NOT EXISTS opportunities(
      id INTEGER PRIMARY KEY AUTOINCREMENT, source TEXT, title TEXT, url TEXT UNIQUE,
      reward TEXT, eligibility TEXT, summary TEXT, updated TEXT
    );
    CREATE TABLE IF NOT EXISTS done(id INTEGER PRIMARY KEY, task_id INTEGER, note TEXT, created TEXT);
    CREATE TABLE IF NOT EXISTS income(id INTEGER PRIMARY KEY, task_id INTEGER, cents INTEGER, note TEXT, created TEXT);
    CREATE TABLE IF NOT EXISTS visitors(user_id TEXT PRIMARY KEY, username TEXT, full_name TEXT, first_seen TEXT);
    """)
    return db


def fetch_github_bounties():
    found = []
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "TaskWorkerAZ/2.0"}
    for query in GITHUB_QUERIES:
        params = urllib.parse.urlencode({"q": query, "sort": "updated", "order": "desc", "per_page": 20})
        req = urllib.request.Request("https://api.github.com/search/issues?" + params, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=15) as response:
                payload = json.loads(response.read().decode("utf-8"))
            for item in payload.get("items", []):
                title = (item.get("title") or "").strip()
                body = item.get("body") or ""
                if not title or not item.get("html_url"):
                    continue
                combined = title + "\n" + body
                lowered = combined.lower()
                if any(phrase in lowered for phrase in JUNK_PHRASES):
                    continue
                source_url = extract_source_url(body, item["html_url"])
                # Only show canonical, verified, open, unassigned cash bounty issues.
                verified, source_content = verify_github_issue(source_url)
                if not verified or not isinstance(source_content, str):
                    continue
                if item.get("assignees"):
                    continue
                if any(term in source_content.lower() for term in NO_CASH_PHRASES):
                    continue
                if verified and isinstance(source_content, str):
                    source_title, _, source_body = source_content.partition("\n")
                    if source_title:
                        title = source_title.strip()
                    reward_text = parse_reward(title, source_body)
                    if reward_text == "Mükafat təsdiqlənməyib":
                        continue
                    eligibility = classify_eligibility(title + "\n" + source_body)
                    summary_source = source_body
                else:
                    continue
                verification = "ORIGINAL_VERIFIED_CASH_REWARD"
                summary = "[%s] %s" % (verification, re.sub(r"\s+", " ", summary_source).strip()[:450])
                found.append({
                    "source": "GitHub", "title": title[:240], "url": source_url,
                    "reward": reward_text, "eligibility": eligibility,
                    "summary": summary,
                    "updated": item.get("updated_at") or datetime.now(timezone.utc).isoformat(),
                })
        except Exception as exc:
            log.warning("GitHub task scan failed: %s", exc)
    unique = {item["url"]: item for item in found}
    return list(unique.values())[:40]

def save_opportunities(items):
    new_items = []
    with connect() as db:
        known = {row[0] for row in db.execute("SELECT url FROM opportunities")}
        for item in items:
            if item["url"] not in known:
                new_items.append(item)
            db.execute("""INSERT INTO opportunities(source,title,url,reward,eligibility,summary,updated)
              VALUES(?,?,?,?,?,?,?) ON CONFLICT(url) DO UPDATE SET
              title=excluded.title,reward=excluded.reward,eligibility=excluded.eligibility,
              summary=excluded.summary,updated=excluded.updated""",
              (item["source"], item["title"], item["url"], item["reward"],
               item["eligibility"], item["summary"], item["updated"]))
    return new_items


async def private_only(update):
    if not update.effective_chat or update.effective_chat.type != "private":
        await update.effective_message.reply_text("Təhlükəsizlik üçün bot yalnız şəxsi çatda işləyir.")
        return False
    return True


async def scheduled_scan(app):
    while True:
        try:
            items = await asyncio.to_thread(fetch_github_bounties)
            new_items = await asyncio.to_thread(save_opportunities, items)
            if OWNER and new_items:
                lines = ["🆕 Yeni açıq bounty elanları:"]
                for item in new_items[:8]:
                    lines.append(f"\n• {item['title']}\n{item['reward']} | {item['eligibility']}\n{item['url']}")
                await app.bot.send_message(chat_id=int(OWNER), text="\n".join(lines), disable_web_page_preview=True)
        except Exception:
            log.exception("Scheduled task discovery failed")
        await asyncio.sleep(6 * 60 * 60)


async def post_init(app):
    app.create_task(scheduled_scan(app))


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await private_only(update):
        return
    user = update.effective_user
    with connect() as db:
        cur = db.execute("INSERT OR IGNORE INTO visitors(user_id,username,full_name,first_seen) VALUES(?,?,?,?)",
            (str(user.id), user.username or "", user.full_name, datetime.now(timezone.utc).isoformat()))
        is_new = cur.rowcount > 0
    if is_new and OWNER and str(user.id) != OWNER:
        try:
            await context.bot.send_message(chat_id=int(OWNER),
                text=f"Yeni istifadəçi: {user.full_name} | @{user.username or 'yoxdur'} | ID: {user.id}")
        except Exception:
            log.exception("Owner notification failed")
    mode = context.user_data.get("task_mode", "demo")
    await update.message.reply_text(
        "🤖 Task Worker AZ\n"
        f"Rejim: {'DEMO' if mode == 'demo' else 'REAL elan axtarışı'}\n\n"
        "/scan — açıq bounty tapşırıqlarını axtar\n"
        "/tasks — tapşırıq mənbələri\n"
        "/opportunities — tapılmış elanlar\n"
        "/view ID — elan təfərrüatı\n"
        "/done ID qeyd — işi tamamlandı kimi qeyd et\n"
        "/paid ID məbləğ qeyd — faktiki alınan pulu yaz\n"
        "/balance — real gəlir\n/history — tarixçə\n/id — Telegram ID\n\n"
        "DEMO: sınaq və elan baxışı. REAL: cari açıq elanlar; müraciət və işi tamamlamaq üçün sahib təsdiqi tələb olunur.",
        reply_markup=mode_keyboard(mode)
    )


async def mode_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "task_mode_demo":
        context.user_data["task_mode"] = "demo"
        label = "🧪 DEMO rejimi seçildi. Heç bir müraciət və iş icrası edilmir."
    elif query.data == "task_mode_real":
        context.user_data["task_mode"] = "real"
        label = ("🚀 REAL rejimi seçildi. Bot cari açıq elanları axtarır. "
                 "Platformaya müraciət və ödəniş addımları avtomatik edilmir; elan şərtləri və işə başlamaq sənin təsdiqini tələb edir.")
    else:
        return
    await query.message.reply_text(label, reply_markup=mode_keyboard(context.user_data["task_mode"]))


async def myid(update, context):
    await update.message.reply_text(f"Telegram ID: {update.effective_user.id}")


async def tasks(update, context):
    if not await private_only(update):
        return
    lines = ["İş və bounty mənbələri (elanlar platformanın özündədir):"]
    lines += [f"\n{i}. {name}\n{note}\n{url}" for i, (name, url, note) in enumerate(SITES, 1)]
    lines.append("\nAzərbaycanda qeydiyyat və pul çıxarışı hər hesabda fərqli ola bilər. İşə başlamazdan əvvəl payout metodunu yoxla. İş almaq üçün heç bir sayta depozit ödəmə.")
    lines.append("GitHub skanında yalnız açıq, orijinalı təsdiqlənmiş, icraçıya verilməmiş və rəqəmlə göstərilən USD/USDC mükafatlı elanlar göstərilir. Token və qeyri-müəyyən mükafatlar çıxarılır.")
    await update.message.reply_text("\n".join(lines), disable_web_page_preview=True)

 
async def faucet(update, context):
    if not await private_only(update):
        return
    await update.message.reply_text(
        "FaucetPay: https://faucetpay.io/\n\n"
        "FaucetPay özü işəgötürən deyil, kripto mikro-cüzdandır. Qazanc faucet, PTC reklamları və offerwall tərəfdaşlarının tapşırıqlarından gəlir.\n"
        "Hesabında Faucet List, PTC Ads və Offerwall bölmələrini yoxla.\n\n"
        "Bot CAPTCHA, reklam baxışı və ya saytın qadağan etdiyi claim-ləri avtomatik etməyəcək. Yalnız rəsmi API və konkret tapşırıq qaydaları avtomatlaşdırmaya açıq icazə verəndə icra modulu qoşulacaq.\n"
        "FaucetPay bank hesabına birbaşa çıxarış etmir; kripto cüzdana çıxarış, minimum və şəbəkə haqqı tətbiq olunur.",
        disable_web_page_preview=True
    )


async def scan(update, context):
    if not await private_only(update):
        return
    await update.message.reply_text("Açıq bounty elanları axtarılır...")
    try:
        items = await asyncio.to_thread(fetch_github_bounties)
        await asyncio.to_thread(save_opportunities, items)
        await update.message.reply_text(f"Yoxlama bitdi: {len(items)} elan tapıldı. /opportunities yaz.")
    except Exception as exc:
        log.exception("Task scan failed")
        await update.message.reply_text(f"Axtarış zamanı xəta: {str(exc)[:250]}")


async def opportunities(update, context):
    if not await private_only(update):
        return
    with connect() as db:
        rows = db.execute("SELECT id,title,reward,eligibility,url FROM opportunities ORDER BY updated DESC LIMIT 15").fetchall()
    if not rows:
        await update.message.reply_text("Hələ elan tapılmayıb. Əvvəl /scan yaz.")
        return
    lines = ["Tapılmış açıq elanlar:"]
    for row in rows:
        lines.append(f"\nID {row['id']}: {row['title']}\nMükafat: {row['reward']}\nİcazə: {row['eligibility']}\n{row['url']}")
    lines.append("\nQeyd: elanların mövcudluğu və mükafatın ödənməsi zəmanətli deyil.")
    await update.message.reply_text("\n".join(lines), disable_web_page_preview=True)


async def view(update, context):
    if not await private_only(update):
        return
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("İstifadə: /view ID")
        return
    with connect() as db:
        row = db.execute("SELECT * FROM opportunities WHERE id=?", (int(context.args[0]),)).fetchone()
    if not row:
        await update.message.reply_text("Elan tapılmadı. /scan ilə yenilə.")
        return
    await update.message.reply_text(
        f"{row['title']}\nMükafat: {row['reward']}\nİcazə: {row['eligibility']}\n"
        f"Yenilənib: {row['updated']}\n{row['url']}\n\n"
        f"Qısa təsvir: {row['summary'] or 'Təsvir yoxdur'}\n\n"
        "İşə başlamazdan əvvəl qaydaları, AI istifadəsinə icazəni və ödəniş şərtlərini özün təsdiqlə.",
        disable_web_page_preview=True)


async def done(update, context):
    if not await private_only(update):
        return
    if len(context.args) < 2 or not context.args[0].isdigit():
        await update.message.reply_text("İstifadə: /done ID qeyd")
        return
    task_id = int(context.args[0])
    with connect() as db:
        row = db.execute("SELECT title FROM opportunities WHERE id=?", (task_id,)).fetchone()
        if not row:
            await update.message.reply_text("Elan ID-si tapılmadı.")
            return
        db.execute("INSERT INTO done(task_id,note,created) VALUES(?,?,?)",
            (task_id, " ".join(context.args[1:]), datetime.now(timezone.utc).isoformat()))
    await update.message.reply_text("Tamamlandı kimi qeyd edildi. Bu qeyd ödəniş demək deyil; pul gələndə /paid yaz.")


async def paid(update, context):
    if not await private_only(update):
        return
    if len(context.args) < 2 or not context.args[0].isdigit():
        await update.message.reply_text("İstifadə: /paid ID məbləğ qeyd")
        return
    try:
        task_id = int(context.args[0])
        amount = Decimal(context.args[1].replace(",", "."))
        cents = int(amount * 100)
        if amount <= 0 or cents <= 0:
            raise ValueError()
    except (ValueError, InvalidOperation):
        await update.message.reply_text("ID və müsbət məbləği düzgün yaz.")
        return
    with connect() as db:
        row = db.execute("SELECT title FROM opportunities WHERE id=?", (task_id,)).fetchone()
        if not row:
            await update.message.reply_text("Elan ID-si tapılmadı.")
            return
        db.execute("INSERT INTO income(task_id,cents,note,created) VALUES(?,?,?,?)",
            (task_id, cents, " ".join(context.args[2:]), datetime.now(timezone.utc).isoformat()))
    await update.message.reply_text("Faktiki alınmış ödəniş qeydə alındı: $" + f"{cents/100:.2f}")


async def balance(update, context):
    if not await private_only(update):
        return
    with connect() as db:
        total = db.execute("SELECT COALESCE(SUM(cents),0) FROM income").fetchone()[0]
        count = db.execute("SELECT COUNT(*) FROM income").fetchone()[0]
    await update.message.reply_text("Qeydə alınmış faktiki gəlir: $" + f"{total/100:.2f}" + f"\nÖdəniş sayı: {count}")


async def history(update, context):
    if not await private_only(update):
        return
    with connect() as db:
        rows = db.execute("SELECT cents,note,task_id FROM income ORDER BY id DESC LIMIT 15").fetchall()
        done_rows = db.execute("SELECT task_id,note FROM done ORDER BY id DESC LIMIT 10").fetchall()
    lines = ["Ödənişlər:"] + ["+$" + f"{r['cents']/100:.2f}" + f" — elan {r['task_id']} — {r['note']}" for r in rows]
    if not rows:
        lines.append("Hələ ödəniş yoxdur.")
    lines.append("\nTamamlanan iş qeydləri:")
    lines += [f"• Elan {r['task_id']} — {r['note']}" for r in done_rows] or ["Hələ qeyd yoxdur."]
    await update.message.reply_text("\n".join(lines))


def main():
    if not TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN təyin edilməyib")
    app = Application.builder().token(TOKEN).post_init(post_init).build()
    for name, handler in [
        ("start", start), ("id", myid), ("tasks", tasks), ("scan", scan),
        ("opportunities", opportunities), ("faucet", faucet), ("view", view), ("done", done),
        ("paid", paid), ("balance", balance), ("history", history)
    ]:
        app.add_handler(CommandHandler(name, handler))
    app.add_handler(CallbackQueryHandler(mode_callback, pattern=r"^task_mode_"))
    log.info("Task Worker AZ started")
    app.run_polling()


if __name__ == "__main__":
    main()
