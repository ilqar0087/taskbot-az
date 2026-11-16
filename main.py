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

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
OWNER = os.getenv("OWNER_TELEGRAM_ID", "")
DB = os.getenv("DATABASE_PATH", "/data/taskbot.sqlite3")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("task-worker")

SITES = [
    ("GitHub Bounties", "https://github.com/issues?q=is%3Aissue+is%3Aopen+bounty", "Açıq mənbə proqramlaşdırma mükafatları; hər elanın şərtlərini yoxla."),
    ("Algora", "https://algora.io/", "Açıq mənbə issue-ləri üçün bounty platforması; iştirak şərtləri dəyişir."),
    ("Superteam Earn", "https://superteam.fun/earn", "Yalnız elanda AI agentə açıq icazə varsa avtomatlaşdırma kömək edə bilər."),
    ("make.fun", "https://make.fun/", "AI agentlər üçün yarışma və bounty elanları; ödəniş yalnız qalibiyyət və qəbuldan sonra."),
    ("Clustly", "https://www.clustly.ai/", "Agent xidmətləri və sifarişlər; escrow və müştəri təsdiqi tələb oluna bilər."),
    ("BasedAgents", "https://basedagents.ai/", "Agent tapşırıqları; mükafat və şərtləri hər elanda yoxla."),
    ("TaskMarket", "https://taskmarket.dev/", "Agent tapşırıqları; bəzi əməliyyatlar ödəniş və ya wallet tələb edə bilər."),
    ("Clickworker", "https://www.clickworker.com/clickworker/", "İnsan hesabı ilə mikrotapşırıqlar; botla klikləmək və saxta sübut göndərmək olmaz."),
    ("Toloka", "https://toloka.ai/tolokers/", "İnsan tərəfindən görülən tapşırıqlar; yalnız qaydalar açıq icazə verəndə AI köməyi."),
    ("SproutGigs", "https://sproutgigs.com/", "İnsan mikroişləri; platforma qaydalarını pozan avtomatlaşdırma olmaz."),
    ("Fiverr", "https://www.fiverr.com/", "Xidmət satışı; profil, təklif və müştəri yazışması insan təsdiqi ilə."),
    ("Upwork", "https://www.upwork.com/", "Freelance layihələr; müraciət və müştəri ünsiyyəti insan təsdiqi ilə."),
]

GITHUB_QUERIES = [
    "is:issue is:open label:bounty",
    "is:issue is:open bounty",
    'is:issue is:open "reward" "USDC"',
]
HUMAN_ONLY = ("no ai", "no automation", "human only", "human-only", "must be done manually", "no bots")
AGENT_WORDS = ("agent allowed", "ai agent", "agent-only", "agent only", "autonomous agent")
REWARD_RE = re.compile(r"(?:\$\s?\d[\d,]*(?:\.\d{1,2})?|\d[\d,]*(?:\.\d{1,2})?\s?(?:USDC|USD|ETH|SOL))", re.I)


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
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "TaskWorkerAZ/1.0"}
    for query in GITHUB_QUERIES:
        params = urllib.parse.urlencode({"q": query, "sort": "updated", "order": "desc", "per_page": 20})
        req = urllib.request.Request("https://api.github.com/search/issues?" + params, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=15) as response:
                payload = json.loads(response.read().decode("utf-8"))
            for item in payload.get("items", []):
                title = (item.get("title") or "").strip()
                body = item.get("body") or ""
                labels = [x.get("name", "") for x in item.get("labels", [])]
                text = (title + " " + body + " " + " ".join(labels)).lower()
                if not title or not item.get("html_url"):
                    continue
                if any(word in text for word in HUMAN_ONLY):
                    eligibility = "HUMAN_ONLY"
                elif any(word in text for word in AGENT_WORDS):
                    eligibility = "AGENT_ALLOWED — yenə də şərtləri yoxla"
                else:
                    eligibility = "REVIEW_REQUIRED — AI agent icazəsi təsdiqlənməyib"
                reward_match = REWARD_RE.search(title + " " + body)
                reward = reward_match.group(0) if reward_match else "Mükafat göstərilməyib"
                found.append({
                    "source": "GitHub", "title": title[:240], "url": item["html_url"],
                    "reward": reward, "eligibility": eligibility,
                    "summary": re.sub(r"\s+", " ", body).strip()[:500],
                    "updated": item.get("updated_at") or datetime.now(timezone.utc).isoformat(),
                })
        except Exception as exc:
            log.warning("GitHub task scan failed: %s", exc)
    unique = {item["url"]: item for item in found}
    return list(unique.values())[:40]


def save_opportunities(items):
    with connect() as db:
        for item in items:
            db.execute("""INSERT INTO opportunities(source,title,url,reward,eligibility,summary,updated)
              VALUES(?,?,?,?,?,?,?) ON CONFLICT(url) DO UPDATE SET
              title=excluded.title,reward=excluded.reward,eligibility=excluded.eligibility,
              summary=excluded.summary,updated=excluded.updated""",
              (item["source"], item["title"], item["url"], item["reward"],
               item["eligibility"], item["summary"], item["updated"]))


async def private_only(update):
    if not update.effective_chat or update.effective_chat.type != "private":
        await update.effective_message.reply_text("Təhlükəsizlik üçün bot yalnız şəxsi çatda işləyir.")
        return False
    return True


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
    await update.message.reply_text(
        "🤖 Task Worker AZ\n\n"
        "/scan — açıq bounty tapşırıqlarını axtar\n"
        "/tasks — tapşırıq mənbələri\n"
        "/opportunities — tapılmış elanlar\n"
        "/view ID — elan təfərrüatı\n"
        "/done ID qeyd — işi tamamlandı kimi qeyd et\n"
        "/paid ID məbləğ qeyd — faktiki alınan pulu yaz\n"
        "/balance — real gəlir\n/history — tarixçə\n/id — Telegram ID"
    )


async def myid(update, context):
    await update.message.reply_text(f"Telegram ID: {update.effective_user.id}")


async def tasks(update, context):
    if not await private_only(update):
        return
    lines = ["İş və bounty mənbələri (elanlar platformanın özündədir):"]
    lines += [f"\n{i}. {name}\n{note}\n{url}" for i, (name, url, note) in enumerate(SITES, 1)]
    lines.append("\nBot yalnız açıq elanları tapır. Ölkə uyğunluğu, hesab tələbləri və ödəniş hər platformada ayrıca yoxlanmalıdır.")
    await update.message.reply_text("\n".join(lines), disable_web_page_preview=True)


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
    app = Application.builder().token(TOKEN).build()
    for name, handler in [
        ("start", start), ("id", myid), ("tasks", tasks), ("scan", scan),
        ("opportunities", opportunities), ("view", view), ("done", done),
        ("paid", paid), ("balance", balance), ("history", history)
    ]:
        app.add_handler(CommandHandler(name, handler))
    log.info("Task Worker AZ started")
    app.run_polling()


if __name__ == "__main__":
    main()
