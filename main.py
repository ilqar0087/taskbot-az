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
# Avoid logging HTTP URLs that contain Telegram bot API tokens.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
log = logging.getLogger("task-worker")

SITES = [
    ("Microworkers", "https://www.microworkers.com/", "Kiçik onlayn tapşırıqlar. Ödəniş üsulu, minimum çıxarış və KYC-ni hesabda yoxla; tapşırıq sayı ölkəyə görə dəyişir."),
    ("Mindrift", "https://www.mindrift.ai/", "AI mətn qiymətləndirmə və təlim layihələri. Azərbaycan üzrə qəbul və ödəniş üsulunu əvvəlcədən təsdiqlə."),
    ("Clickworker", "https://www.clickworker.com/clickworker/", "Mikrotapşırıqlar və AI data işi. Azərbaycan qeydiyyatı və ödəniş üsulu Payment details bölməsində təsdiqlənməlidir."),
    ("CrowdGen by Appen", "https://crowdgen.com/", "AI data layihələri. Layihənin Azərbaycana açıq olmasını və ödəniş metodunu hər elanda yoxla."),
    ("Jwuma / Corpshore", "https://platform.corpshore.ai/azerbaijan", "Azərbaycan üçün AI data, mətn, tərcümə və səs tapşırıqları. USD bank hesabına köçürmə göstərilir; telefonda işləmə və konkret layihə mövcudluğunu əvvəlcədən təsdiqlə."),
    ("Crowtado", "https://www.crowtado.com/en", "Telefonla foto, video və səs tapşırıqları. Azərbaycan üzrə tapşırıq və çıxarış metodunu hesabda yoxla; gəlir zəmanətli deyil."),
    ("Wake", "https://wake.inc/contribute/", "Android/iOS ilə fiziki işlərin videosunu çəkib AI təliminə töhfə ver. Azərbaycan ödəniş ölkələri siyahısındadır; tapşırıq mövcudluğu tətbiqdə görünür. Rəsmi başlanğıc tarif $6/təsdiqlənmiş saatdır."),
    ("OneForma — Azeri Translation Quality Rater", "https://www.oneforma.com/projects/paragraph-level-translation-quality-rater/", "Azərbaycan üçün açıq dil layihəsi; kompüter və gündə 2 saat tələb olunur, telefonla işləmək uyğun deyil."),
    ("KLKT / CNTXT AI", "https://play.google.com/store/apps/details?id=com.cntxt.cntxtai.data.services", "Android tətbiqində foto, video və audio data tapşırıqları. Azərbaycan üçün payout metodunu və aktiv tapşırıqları tətbiqdə təsdiqlə."),
    ("Andovar", "https://careers.andovar.com/freelance-and-work-from-home-opportunities/", "Dil və səs yazısı layihələri. Konkret Azərbaycan layihəsinin açıq olub-olmadığını yoxla; əvvəlki səs yazısı elanı aktiv olmaya bilər."),
    ("Work.az", "https://work.az/", "Azərbaycan üzrə yerli işlər. Müştəri ilə qiyməti, son tarixi və ödənişi yazılı razılaşdır."),
    ("Upwork", "https://www.upwork.com/", "Beynəlxalq freelance layihələr. Komissiya və Azərbaycanda işləyən çıxarış üsulunu əvvəlcədən yoxla."),
    ("Fiverr", "https://www.fiverr.com/", "Xidmət satışı. Sifarişlər insan təsdiqi ilə; Azərbaycanda işləyən çıxarış metodunu yoxla."),
    ("GitHub Bounties", "https://github.com/issues?q=is%3Aissue+is%3Aopen+bounty", "Yalnız real pul məbləği, açıq issue və təsdiqlənən orijinal mənbə olan bounty elanları."),
    ("FaucetPay", "https://faucetpay.io/", "Kripto mikro-cüzdanıdır; özü işəgötürən deyil. Faucet, PTC və offerwall tapşırıqları üçüncü tərəflərdən gəlir. Bot yalnız qaydaların açıq icazə verdiyi API-ləri avtomatlaşdıra bilər."),
    ("Algora", "https://algora.io/", "Açıq mənbə bounty-ləri. Pul mükafatı, uyğunluq və payout şərtlərini hər işdə yoxla."),
    ("Jobicy", "https://jobicy.com/", "Uzaqdan iş elanları. Bot açıq API-dən elanları çəkir; ölkə uyğunluğu və maaşı yoxla."),
    ("Remote OK", "https://remoteok.com/", "Uzaqdan iş elanları. Bot açıq feed-dən elanları çəkir; müraciət əl ilə edilir."),
]

AZERBAIJAN_LEADS = [
    {
        "name": "Jwuma / Corpshore — Azərbaycan AI tapşırıqları",
        "url": "https://platform.corpshore.ai/azerbaijan",
        "status": "Azərbaycan ayrıca dəstəklənən ölkə kimi göstərilir; bu, avtomatik iş zəmanəti deyil.",
        "details": "Mətn annotasiyası, tərcümə yoxlaması, QA və səs/məlumat toplama. Ödəniş həftəlik batch kimi göstərilir; Azərbaycan üçün USD bank köçürməsi, 2% komissiya (minimum $10, maksimum $30). USD hesab tələb oluna bilər. Telefon uyğunluğu və real tapşırıq mövcudluğu qeydiyyatdan əvvəl təsdiqlənməlidir."
    },
    {
        "name": "Wake — telefonla video çəkilişi (Android/iOS)",
        "url": "https://wake.inc/contribute/",
        "status": "Azərbaycan rəsmi ödəniş ölkələri siyahısındadır. Tətbiqdə görünən tapşırıqlar ölkə və çəkiliş şərtlərinə görə dəyişir.",
        "details": "Əllər sərbəst çəkilişlə yemək hazırlamaq, yığmaq, təmir etmək və gündəlik fiziki işləri videoya çəkmək. Rəsmi sayt başlanğıc tarifi $6/təsdiqlənmiş saat göstərir; bu, zəmanətli qazanc və ya daimi tapşırıq demək deyil. Tətbiqdə Azərbaycan üçün açıq tapşırığı və ödəniş şərtlərini yoxla."
    },
    {
        "name": "OneForma — Azeri Translation Quality Rater (kompüter tələb edir)",
        "url": "https://www.oneforma.com/projects/paragraph-level-translation-quality-rater/",
        "status": "Axtarış zamanı Azerbaijan üçün açıq və müraciət qəbul edən layihə kimi göstərilirdi; status dəyişə bilər.",
        "details": "Azeri (Latin) ↔ English tərcümə keyfiyyətinin yoxlanması; ödəniş təsdiqlənmiş material başınadır, gündə təxminən 2 saat. Layihə kompüter və sabit internet tələb edir, yalnız telefonla işləmək üçün uyğun deyil."
    },
    {
        "name": "Crowtado — telefonla foto, video və audio tapşırıqları",
        "url": "https://www.crowtado.com/en",
        "status": "Platforma və mobil tapşırıqlar mövcuddur; Azərbaycan üzrə tapşırıq və pul çıxarışı ayrıca yoxlanmalıdır.",
        "details": "Yalnız tətbiqdə görünən aktiv tapşırığa və hesabda göstərilən payout şərtlərinə əsasən işə başla. Ödəniş və ölkə uyğunluğu təsdiqlənmədən gəlir hesab etmə."
    },
    {
        "name": "KLKT / CNTXT AI — Android data tapşırıqları",
        "url": "https://play.google.com/store/apps/details?id=com.cntxt.cntxtai.data.services",
        "status": "Android tətbiqi mövcuddur; Azərbaycan üçün aktiv layihə və payout təsdiqi tələb olunur.",
        "details": "Foto, video və audio məlumat toplama tapşırıqları. Ödəniş metodları ölkəyə görə dəyişə bilər; tətbiqdə Azərbaycan hesabı üçün çıxarış üsulunu yoxla."
    },
    {
        "name": "Andovar — dil və səs yazısı layihələri",
        "url": "https://careers.andovar.com/freelance-and-work-from-home-opportunities/",
        "status": "Ümumi freelancer qeydiyyat səhifəsi mövcuddur; əvvəlki Azərbaycan səs layihəsinin aktivliyi təsdiqlənməyib.",
        "details": "Azərbaycan dili üzrə konkret layihə açıqdırsa müraciət et. Tapşırıq, qiymət, cihaz tələbi və ödəniş müddətini yazılı təsdiqlə."
    },
    {
        "name": "Welo Data — Azerbaijani Talent Hub",
        "url": "https://jobs.lever.co/weloglobal/e0af350d-f782-4fd7-9f4a-7a011df6bcab",
        "status": "İştirakçı bazasına qəbul; aktiv vakansiya və zəmanətli iş deyil.",
        "details": "Azərbaycan dili və ingilis dili tələb oluna bilər. Welo-nun rəsmi FAQ-sına görə mobil telefonla işləmək mümkün deyil; kompüter tələb olunur. Buna görə telefon siyahısında ehtiyat variantdır."
    },
    {
        "name": "Work.az — Azərbaycan üzrə yerli və frilans işlər",
        "url": "https://work.az/",
        "status": "Elan kataloqu; hər elanın etibarlılığı və statusu ayrıca yoxlanmalıdır.",
        "details": "Müştəri ilə iş həcmini, qiyməti, son tarixi və ödənişi yazılı razılaşdır. İşə başlamaq üçün əvvəlcədən pul göndərmə."
    }
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
MIRROR_WARNING_PHRASES = (
    "automated ci conformance mirror", "automated ci regression mirror",
    "manual pull requests from human engineers are not reviewed",
    "external edge conformance mirror", "specification shards"
)
MONEY_RE = re.compile(r"\$\s?([0-9][0-9,]*(?:\.\d{1,2})?)\s?([kKmM]?)|([0-9][0-9,]*(?:\.\d{1,2})?)\s?(USDC|USD)\b", re.I)
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

def has_mirror_warning(text):
    lowered = (text or "").lower()
    return any(phrase in lowered for phrase in MIRROR_WARNING_PHRASES)


def has_competing_pull_request(owner, repo, issue_number):
    """Skip issues that already have an open or merged solution PR."""
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "TaskWorkerAZ/2.2"}
    comments_url = "https://api.github.com/repos/%s/%s/issues/%s/comments?per_page=100" % (owner, repo, issue_number)
    try:
        req = urllib.request.Request(comments_url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as response:
            comments = json.loads(response.read().decode("utf-8"))
        pattern = re.compile(r"https?://github\.com/%s/%s/pull/(\d+)" % (re.escape(owner), re.escape(repo)), re.I)
        pr_numbers = set()
        for comment in comments:
            pr_numbers.update(pattern.findall(comment.get("body") or ""))
        for number in pr_numbers:
            pr_url = "https://api.github.com/repos/%s/%s/pulls/%s" % (owner, repo, number)
            req = urllib.request.Request(pr_url, headers=headers)
            with urllib.request.urlopen(req, timeout=10) as response:
                pr = json.loads(response.read().decode("utf-8"))
            if pr.get("state") == "open" or pr.get("merged") is True:
                return True
        return False
    except Exception as exc:
        log.info("Optional PR check skipped for %s/%s#%s: %s", owner, repo, issue_number, type(exc).__name__)
        return False


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
        if has_mirror_warning(content):
            return False, "Avtomatik CI güzgüsüdür; normal PR-lar qəbul edilmir"
        if any(term in content.lower() for term in NO_CASH_PHRASES):
            return False, "Nağd ödəniş təsdiqlənməyib"
        if has_competing_pull_request(owner, repo, number):
            return False, "Artıq açıq və ya birləşdirilmiş həll PR-ı mövcuddur"
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
      reward TEXT, eligibility TEXT, summary TEXT, updated TEXT, active INTEGER NOT NULL DEFAULT 1
    );
    CREATE TABLE IF NOT EXISTS done(id INTEGER PRIMARY KEY, task_id INTEGER, note TEXT, created TEXT);
    CREATE TABLE IF NOT EXISTS income(id INTEGER PRIMARY KEY, task_id INTEGER, cents INTEGER, note TEXT, created TEXT);
    CREATE TABLE IF NOT EXISTS visitors(user_id TEXT PRIMARY KEY, username TEXT, full_name TEXT, first_seen TEXT);
    CREATE TABLE IF NOT EXISTS user_settings(user_id TEXT PRIMARY KEY, task_mode TEXT NOT NULL DEFAULT 'real');
    """)
    columns = {row[1] for row in db.execute("PRAGMA table_info(opportunities)")}
    if "active" not in columns:
        db.execute("ALTER TABLE opportunities ADD COLUMN active INTEGER NOT NULL DEFAULT 1")
    return db


def get_mode(user_id):
    with connect() as db:
        row = db.execute("SELECT task_mode FROM user_settings WHERE user_id=?", (str(user_id),)).fetchone()
    return row[0] if row else "real"


def set_mode(user_id, mode):
    with connect() as db:
        db.execute("INSERT INTO user_settings(user_id,task_mode) VALUES(?,?) "
                   "ON CONFLICT(user_id) DO UPDATE SET task_mode=excluded.task_mode",
                   (str(user_id), mode))


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
                if any(phrase in lowered for phrase in JUNK_PHRASES) or has_mirror_warning(combined):
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


def fetch_remote_job_feeds():
    """Fetch public remote-job feeds; retain the original source URL and attribution."""
    found = []
    headers = {"User-Agent": "TaskWorkerAZ/2.1 (+https://github.com/ilqar0087/taskbot-az)", "Accept": "application/json"}

    try:
        req = urllib.request.Request("https://jobicy.com/api/v2/remote-jobs?count=50", headers=headers)
        with urllib.request.urlopen(req, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
        for job in payload.get("jobs", []):
            title = (job.get("jobTitle") or "").strip()
            url = job.get("url") or ""
            if not title or not url.startswith("http"):
                continue
            location = job.get("jobGeo") or "Remote — dəqiqləşdir"
            salary_min, salary_max = job.get("salaryMin"), job.get("salaryMax")
            currency = job.get("salaryCurrency") or "USD"
            salary = f"Maaş: {salary_min or '?'}–{salary_max or '?'} {currency}" if salary_min or salary_max else "Maaş: elanda göstərilməyib"
            excerpt = job.get("jobExcerpt") or job.get("jobDescription") or ""
            found.append({
                "source": "Jobicy",
                "title": f"{title} — {job.get('companyName') or 'Şirkət göstərilməyib'} [{location}]",
                "url": url,
                "reward": salary,
                "eligibility": "REMOTE_JOB — ölkə uyğunluğu və müraciət şərtlərini yoxla",
                "summary": "[Mənbə: Jobicy] " + re.sub(r"\s+", " ", excerpt).strip()[:450],
                "updated": job.get("pubDate") or datetime.now(timezone.utc).isoformat(),
            })
    except Exception as exc:
        log.warning("Jobicy feed failed: %s", type(exc).__name__)

    # Remote OK's first JSON object contains its API usage/attribution notice.
    try:
        req = urllib.request.Request("https://remoteok.com/api", headers=headers)
        with urllib.request.urlopen(req, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
        for job in payload:
            if not isinstance(job, dict) or not job.get("position") or not job.get("url"):
                continue
            url = job["url"]
            if not url.startswith("http"):
                continue
            location = job.get("location") or "Remote — dəqiqləşdir"
            low, high = job.get("salary_min"), job.get("salary_max")
            salary = f"Maaş: ${low}–${high}" if low or high else "Maaş: elanda göstərilməyib"
            tags = ", ".join(job.get("tags") or [])
            summary = (job.get("description") or "") + (f" | Etiketlər: {tags}" if tags else "")
            found.append({
                "source": "Remote OK",
                "title": f"{job['position']} — {job.get('company') or 'Şirkət göstərilməyib'} [{location}]",
                "url": url,
                "reward": salary,
                "eligibility": "REMOTE_JOB — ölkə uyğunluğu və müraciət şərtlərini yoxla",
                "summary": "[Mənbə: Remote OK] " + re.sub(r"<[^>]+>", " ", re.sub(r"\s+", " ", summary)).strip()[:450],
                "updated": job.get("date") or datetime.now(timezone.utc).isoformat(),
            })
    except Exception as exc:
        log.warning("Remote OK feed failed: %s", type(exc).__name__)

    unique = {item["url"]: item for item in found}
    return list(unique.values())[:80]


def fetch_all_opportunities():
    return fetch_github_bounties() + fetch_remote_job_feeds()


def save_opportunities(items):
    new_items = []
    with connect() as db:
        if items:
            db.execute("UPDATE opportunities SET active=0")
        known = {row[0] for row in db.execute("SELECT url FROM opportunities")}
        for item in items:
            if item["url"] not in known:
                new_items.append(item)
                known.add(item["url"])
            db.execute("""INSERT INTO opportunities(source,title,url,reward,eligibility,summary,updated,active)
              VALUES(?,?,?,?,?,?,?,1) ON CONFLICT(url) DO UPDATE SET
              title=excluded.title,reward=excluded.reward,eligibility=excluded.eligibility,
              summary=excluded.summary,updated=excluded.updated,active=1""",
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
            items = await asyncio.to_thread(fetch_all_opportunities)
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
    app.bot_data["scanner_task"] = asyncio.create_task(scheduled_scan(app))


async def post_shutdown(app):
    task = app.bot_data.get("scanner_task")
    if task and not task.done():
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


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
    mode = get_mode(user.id)
    await update.message.reply_text(
        "🤖 Task Worker AZ\n"
        f"Rejim: {'DEMO' if mode == 'demo' else 'REAL elan axtarışı'}\n\n"
        "/scan — bounty və uzaqdan iş elanlarını axtar\n"
        "/tasks — tapşırıq mənbələri\n"
        "/opportunities — tapılmış elanlar\n"
        "/view ID — elan təfərrüatı\n"
        "/done ID qeyd — işi tamamlandı kimi qeyd et\n"
        "/paid ID məbləğ qeyd — faktiki alınan pulu yaz\n"
        "/balance — real gəlir\n/history — tarixçə\n/faucet — FaucetPay məlumatı\n/id — Telegram ID\n\n"
        "DEMO: sınaq və elan baxışı. REAL: bounty və uzaqdan iş elanları; müraciət və iş icrası üçün insan təsdiqi tələb olunur.",
        reply_markup=mode_keyboard(mode)
    )


async def mode_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "task_mode_demo":
        mode = "demo"
        label = "🧪 DEMO rejimi seçildi."
    elif query.data == "task_mode_real":
        mode = "real"
        label = ("🚀 REAL rejimi aktivdir. Bot real elanları axtaracaq və yeniləri barədə xəbər verəcək. "
                 "Heç bir saxta qazanc yazılmır; müraciət və işə başlamaq üçün təsdiq tələb olunur.")
    else:
        return
    set_mode(query.from_user.id, mode)
    await query.message.reply_text(label, reply_markup=mode_keyboard(mode))


async def real_mode(update, context):
    if not await private_only(update):
        return
    set_mode(update.effective_user.id, "real")
    await update.message.reply_text(
        "🚀 REAL rejim aktivdir və yadda saxlanıldı. Bot açıq ödənişli elanları axtaracaq; "
        "yeni nəticələr barədə xəbər verəcək. /scan — indi axtar.",
        reply_markup=mode_keyboard("real"))


async def demo_mode(update, context):
    if not await private_only(update):
        return
    set_mode(update.effective_user.id, "demo")
    await update.message.reply_text("🧪 DEMO rejimi aktivdir.", reply_markup=mode_keyboard("demo"))


async def status(update, context):
    if not await private_only(update):
        return
    mode = get_mode(update.effective_user.id)
    await update.message.reply_text("Vəziyyət: " + ("🚀 REAL" if mode == "real" else "🧪 DEMO") +
        "\nMənbələr: GitHub nağd bounty, Jobicy, Remote OK.\n/scan — axtarış\n/azjobs — Azərbaycan platformaları")


async def myid(update, context):
    await update.message.reply_text(f"Telegram ID: {update.effective_user.id}")


async def tasks(update, context):
    if not await private_only(update):
        return
    lines = ["İş və bounty mənbələri (elanlar platformanın özündədir):"]
    lines += [f"\n{i}. {name}\n{note}\n{url}" for i, (name, url, note) in enumerate(SITES, 1)]
    lines.append("\nAzərbaycanda qeydiyyat və pul çıxarışı hər hesabda fərqli ola bilər. İşə başlamazdan əvvəl payout metodunu yoxla. İş almaq üçün heç bir sayta depozit ödəmə.")
    lines.append("Bot GitHub-da təsdiqlənən nağd bounty-ləri, Jobicy və Remote OK uzaqdan iş elanlarını axtarır. Elanlar mənbəyə keçidlə göstərilir; müraciət və işi görmək insan təsdiqi tələb edir.")
    await update.message.reply_text("\n".join(lines), disable_web_page_preview=True)

 
async def azjobs(update, context):
    if not await private_only(update):
        return
    lines = ["🇦🇿 Azərbaycan üçün iş platformaları — telefon uyğunluğu və ödəniş statusu ayrıca göstərilir:"]
    for i, lead in enumerate(AZERBAIJAN_LEADS, 1):
        lines.append(f"\n{i}. {lead['name']}\nStatus: {lead['status']}\nTələblər: {lead['details']}\n{lead['url']}")
    lines.append("\nƏvvəl Wake və Crowtado-da telefonla açıq tapşırıqları yoxla. Wake Azərbaycanı ödəniş ölkəsi kimi göstərir, amma tapşırıq sayı zəmanətli deyil. OneForma layihəsi kompüter tələb edir. Jwuma-da USD köçürmə şərtlərini, digər platformalarda payout metodunu hesabda təsdiqlə. Heç bir sayta iş almaq üçün depozit ödəmə.")
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
        items = await asyncio.to_thread(fetch_all_opportunities)
        await asyncio.to_thread(save_opportunities, items)
        await update.message.reply_text(f"Yoxlama bitdi: {len(items)} elan tapıldı. /opportunities yaz.")
    except Exception as exc:
        log.exception("Task scan failed")
        await update.message.reply_text(f"Axtarış zamanı xəta: {str(exc)[:250]}")


async def opportunities(update, context):
    if not await private_only(update):
        return
    with connect() as db:
        rows = db.execute("SELECT id,title,reward,eligibility,url FROM opportunities WHERE active=1 ORDER BY updated DESC LIMIT 15").fetchall()
    if not rows:
        await update.message.reply_text("Hələ elan tapılmayıb. Əvvəl /scan yaz.")
        return
    lines = ["Tapılmış açıq elanlar:"]
    for row in rows:
        lines.append(f"\nID {row['id']}: {row['title']}\nÖdəniş: {row['reward']}\nNöv: {row['eligibility']}\n{row['url']}")
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
        f"{row['title']}\nÖdəniş: {row['reward']}\nNöv: {row['eligibility']}\n"
        f"Yenilənib: {row['updated']}\n{row['url']}\n\n"
        f"Qısa təsvir: {row['summary'] or 'Təsvir yoxdur'}\n\n"
        "İşə başlamazdan əvvəl qaydaları, AI istifadəsinə icazəni və ödəniş şərtlərini özün təsdiqlə.",
        disable_web_page_preview=True)



async def prepare(update, context):
    if not await private_only(update):
        return
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("İstifadə: /prepare ID")
        return
    with connect() as db:
        row = db.execute("SELECT * FROM opportunities WHERE id=?", (int(context.args[0]),)).fetchone()
    if not row:
        await update.message.reply_text("Elan tapılmadı. /scan ilə siyahını yenilə.")
        return
    title = row["title"]
    summary = re.sub(r"\s+", " ", row["summary"] or "").strip()
    if len(summary) > 650:
        summary = summary[:650] + "…"
    draft = (
        "Müraciət mətni — göndərməzdən əvvəl öz təcrübənə uyğun redaktə et:\n\n"
        "Salam!\n\n"
        f"“{title}” elanı ilə maraqlanıram. Tapşırığın tələblərini nəzərdən keçirməyə və "
        "razılaşdırılmış müddətdə keyfiyyətli nəticə təqdim etməyə hazıram.\n\n"
        "İşə başlamazdan əvvəl gözlənilən nəticəni, qəbul meyarlarını, son tarixi və ödəniş "
        "qaydalarını dəqiqləşdirmək istərdim. AI alətlərindən istifadə yalnız elan və platforma "
        "qaydaları buna açıq icazə verərsə mümkün olacaq.\n\n"
        "Mənim uyğun təcrübəm: [öz real təcrübəni burada yaz].\n"
        "Təşəkkür edirəm."
    )
    await update.message.reply_text(
        f"📄 Elan #{row['id']} üçün müraciət layihəsi\n"
        f"Mənbə: {row['source']}\nÖdəniş: {row['reward']}\n"
        f"Uyğunluq: {row['eligibility']}\n\n"
        f"Elan xülasəsi: {summary}\n\n{draft}\n\n"
        f"Orijinal elan: {row['url']}\n\n"
        "Bu layihə avtomatik göndərilmir. Təcrübə hissəsini yalnız doğru məlumatla doldur və "
        "müraciəti platformanın özündə özün təsdiqlə.",
        disable_web_page_preview=True
    )


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
    app = Application.builder().token(TOKEN).post_init(post_init).post_shutdown(post_shutdown).build()
    for name, handler in [
        ("start", start), ("id", myid), ("real", real_mode), ("demo", demo_mode), ("status", status),
        ("tasks", tasks), ("azjobs", azjobs), ("scan", scan),
        ("opportunities", opportunities), ("faucet", faucet), ("view", view), ("prepare", prepare), ("done", done),
        ("paid", paid), ("balance", balance), ("history", history)
    ]:
        app.add_handler(CommandHandler(name, handler))
    app.add_handler(CallbackQueryHandler(mode_callback, pattern=r"^task_mode_"))
    log.info("Task Worker AZ started")
    app.run_polling()


if __name__ == "__main__":
    main()
