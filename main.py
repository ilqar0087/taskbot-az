import logging, os, sqlite3
from pathlib import Path
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

TOKEN=os.getenv("TELEGRAM_BOT_TOKEN")
OWNER=os.getenv("OWNER_TELEGRAM_ID")
DB=os.getenv("DATABASE_PATH","/data/taskbot.sqlite3")
MAX_USERS=10
logging.basicConfig(level=logging.INFO)
log=logging.getLogger("taskbot")
SITES=[
("Clickworker","https://www.clickworker.com/clickworker/","İnsan hesabı ilə mikrotapşırıqlar; avtomatik botla klikləmək və təqdim etmək olmaz."),
("Toloka","https://toloka.ai/tolokers/","İnsan tərəfindən yerinə yetirilməli tapşırıqlar; AI yalnız tapşırıq qaydaları açıq icazə verəndə kömək edə bilər."),
("SproutGigs","https://sproutgigs.com/","İnsan tərəfindən görülən mikroişlər; bot, skript və avtomatik sübut təqdimatı qadağandır."),
("Fiverr","https://www.fiverr.com/","Xidmət satışı; profil, müştəri ünsiyyəti və sifariş təsdiqi insan nəzarəti ilə olmalıdır."),
("Upwork","https://www.upwork.com/","Freelance layihələr; təklif və müştəri ünsiyyəti insan təsdiqi ilə, platforma qaydalarına uyğun aparılmalıdır."),
("make.fun","https://make.fun/","AI agentlər üçün kod yarışmaları; yalnız pulsuz girişli bountylər seçilməlidir. Qazanc yalnız qalib olduqda USDC/Solana ilədir."),
("Clustly","https://www.clustly.ai/","AI agent xidməti yerləşdirib müştəri sifarişi almaq; ödəniş USDC/Solana escrow-dadır və müştəri təsdiqi tələb olunur."),
("Superteam Earn","https://superteam.fun/earn","Yalnız agentlərə açıq (AGENT_ALLOWED/AGENT_ONLY) elanlar izlənməlidir; insan üçün olan elanlara bot müraciət etməməlidir."),
("BasedAgents","https://basedagents.ai/","AI agentlər üçün tapşırıq bazarı; qəbul edilən işə görə USDC ödənişi. Əsas şəbəkə Base-dir, Solana deyil; müştəri qəbul etməlidir."),
("TaskMarket / Daydreams","https://taskmarket.dev/","AI agentlər üçün escrow-li tapşırıqlar; qəbul edilən işə görə USDC (Base) və ya dəstəklənən digər şəbəkə. Bəzi əməliyyatlar ödəniş tələb edə bilər."),
("AgentBounties","https://agentbounties.app/","AI agentlər üçün yoxlanıla bilən nəticə mükafatları; USDC, əsasən Base ekosistemi. Yalnız real escrow və pulsuz iştirak olanları seç."),
("BaseBounty","https://www.basebounty.app/","AI agentlər və insanlar üçün Base şəbəkəsində USDC mükafatlı tapşırıqlar; kəşfiyyat üçün ödənişli əməliyyat ola bilər."),
("AgentHansa","https://www.agenthansa.com/","AI agentlər üçün quest və kommersiya tapşırıqları; qeydiyyat, tapşırıq şərtləri və mükafat növü ayrıca yoxlanmalıdır."),
("Jobbi Agent Gigs","https://jobbi.org/gigs/report/","AI agentlər üçün müxtəlif bounty lövhələrini toplayan kataloqdur; özü ödəniş etmir, yalnız tapşırıq mənbələrini tapmağa kömək edir."),
("Algora","https://algora.io/","Açıq mənbə proqramlaşdırma issue-ləri üçün mükafatlar; agent kod hazırlamağa kömək edə bilər, amma GitHub PR və ödəniş qaydaları insan nəzarəti tələb edə bilər."),

]
def connect():
 Path(DB).parent.mkdir(parents=True,exist_ok=True)
 c=sqlite3.connect(DB); c.row_factory=sqlite3.Row
 c.executescript("""
 CREATE TABLE IF NOT EXISTS tasks(id INTEGER PRIMARY KEY,title TEXT,url TEXT,note TEXT);
 CREATE TABLE IF NOT EXISTS done(id INTEGER PRIMARY KEY,task_id INTEGER,note TEXT,created TEXT);
 CREATE TABLE IF NOT EXISTS income(id INTEGER PRIMARY KEY,task_id INTEGER,cents INTEGER,note TEXT,created TEXT);
 CREATE TABLE IF NOT EXISTS allowed_users(user_id TEXT PRIMARY KEY, added_by TEXT, created TEXT);
 """)
 if OWNER:
  c.execute("INSERT OR IGNORE INTO allowed_users(user_id,added_by,created) VALUES(?,?,?)",(str(OWNER),str(OWNER),datetime.now(timezone.utc).isoformat()))
 for site in SITES:
  c.execute("INSERT OR IGNORE INTO tasks(title,url,note) SELECT ?,?,? WHERE NOT EXISTS (SELECT 1 FROM tasks WHERE title=?)",(*site,site[0]))
 c.commit(); return c
def cash(n): return f"${n/100:.2f}"
async def is_owner(u):
 return bool(OWNER) and str(u.effective_user.id)==str(OWNER)
async def allowed(u):
 if not OWNER:
  await u.effective_message.reply_text(f"Bot hazırdır. Sənin Telegram ID-n: {u.effective_user.id}\nSahib ID-si serverdə OWNER_TELEGRAM_ID kimi təyin olunmalıdır.")
  return False
 if u.effective_chat.type!="private":
  await u.effective_message.reply_text("Təhlükəsizlik üçün bot yalnız şəxsi çatda istifadə olunur.")
  return False
 with connect() as c:
  row=c.execute("SELECT 1 FROM allowed_users WHERE user_id=?",(str(u.effective_user.id),)).fetchone()
 if not row:
  await u.effective_message.reply_text("Bu botdan istifadə icazən yoxdur. İcazə üçün bot sahibinə müraciət et.")
  return False
 return True
async def start(u:Update,ctx:ContextTypes.DEFAULT_TYPE):
 if not await allowed(u): return
 await u.message.reply_text("TaskBot AZ hazırdır 🤖\n/tasks — platformalar\n/done ID qeyd — işi tamamlandı kimi yaz\n/paid ID məbləğ qeyd — faktiki aldığın pulu yaz\n/balance — real gəlir\n/history — tarixçə")
async def myid(u,ctx): await u.message.reply_text(f"Telegram ID: {u.effective_user.id}")
async def users(u,ctx):
 if not await is_owner(u): return await u.effective_message.reply_text("Bu əmr yalnız bot sahibinə açıqdır.")
 with connect() as c: rows=c.execute("SELECT user_id FROM allowed_users ORDER BY created").fetchall()
 await u.message.reply_text("İcazəli istifadəçilər (maksimum 10):\\n"+"\\n".join(f"{i+1}. {r['user_id']}" for i,r in enumerate(rows)))
async def adduser(u,ctx):
 if not await is_owner(u): return await u.effective_message.reply_text("Bu əmr yalnız bot sahibinə açıqdır.")
 if len(ctx.args)!=1 or not ctx.args[0].isdigit(): return await u.message.reply_text("İstifadə: /adduser TELEGRAM_ID")
 uid=ctx.args[0]
 with connect() as c:
  exists=c.execute("SELECT 1 FROM allowed_users WHERE user_id=?",(uid,)).fetchone()
  count=c.execute("SELECT COUNT(*) FROM allowed_users").fetchone()[0]
  if exists: return await u.message.reply_text("Bu istifadəçi artıq icazəlidir.")
  if count>=MAX_USERS: return await u.message.reply_text("10 istifadəçi limiti dolub. Əvvəl /removeuser ID ilə birini sil.")
  c.execute("INSERT INTO allowed_users(user_id,added_by,created) VALUES(?,?,?)",(uid,str(u.effective_user.id),datetime.now(timezone.utc).isoformat()))
 await u.message.reply_text(f"{uid} əlavə edildi. İcazəli istifadəçi sayı: {count+1}/10")
async def removeuser(u,ctx):
 if not await is_owner(u): return await u.effective_message.reply_text("Bu əmr yalnız bot sahibinə açıqdır.")
 if len(ctx.args)!=1 or not ctx.args[0].isdigit(): return await u.message.reply_text("İstifadə: /removeuser TELEGRAM_ID")
 uid=ctx.args[0]
 if uid==str(OWNER): return await u.message.reply_text("Əsas sahibin icazəsini silmək olmaz.")
 with connect() as c: cur=c.execute("DELETE FROM allowed_users WHERE user_id=?",(uid,))
 await u.message.reply_text("İcazə silindi." if cur.rowcount else "Bu ID siyahıda tapılmadı.")
async def tasks(u,ctx):
 if not await allowed(u): return
 with connect() as c: rows=c.execute("SELECT * FROM tasks ORDER BY id").fetchall()
 s=["Qazanc platformaları (işlər platformanın özündə verilir):"]
 for r in rows: s.append(f"\n{r['id']}. {r['title']}\n{r['note']}\n{r['url']}")
 s.append("\nTapşırıq sayı, ölkə uyğunluğu və ödəniş zəmanətli deyil.")
 await u.message.reply_text("\n".join(s),disable_web_page_preview=True)
async def done(u,ctx):
 if not await allowed(u): return
 if not ctx.args: return await u.message.reply_text("İstifadə: /done ID qeyd")
 try: tid=int(ctx.args[0])
 except ValueError: return await u.message.reply_text("ID rəqəm olmalıdır.")
 with connect() as c:
  t=c.execute("SELECT title FROM tasks WHERE id=?",(tid,)).fetchone()
  if not t: return await u.message.reply_text("Tapşırıq tapılmadı.")
  c.execute("INSERT INTO done(task_id,note,created) VALUES(?,?,?)",(tid," ".join(ctx.args[1:]),datetime.now(timezone.utc).isoformat()))
 await u.message.reply_text(f"{t['title']} tamamlandı kimi qeyd edildi. Pul gələndə /paid ilə faktiki məbləği yaz.")
async def paid(u,ctx):
 if not await allowed(u): return
 if len(ctx.args)<2: return await u.message.reply_text("İstifadə: /paid ID məbləğ qeyd (məs: /paid 1 2.50 ödəniş)")
 try:
  tid=int(ctx.args[0]); amount=Decimal(ctx.args[1].replace(",",".")); cents=int(amount*100)
  if amount<=0 or cents<=0: raise ValueError()
 except (ValueError,InvalidOperation): return await u.message.reply_text("ID və müsbət məbləği düzgün yaz.")
 with connect() as c:
  t=c.execute("SELECT title FROM tasks WHERE id=?",(tid,)).fetchone()
  if not t: return await u.message.reply_text("Tapşırıq tapılmadı.")
  c.execute("INSERT INTO income(task_id,cents,note,created) VALUES(?,?,?,?)",(tid,cents," ".join(ctx.args[2:]),datetime.now(timezone.utc).isoformat()))
 await u.message.reply_text(f"Faktiki alınmış ödəniş qeydə alındı: {cash(cents)} — {t['title']}")
async def balance(u,ctx):
 if not await allowed(u): return
 with connect() as c:
  total=c.execute("SELECT COALESCE(SUM(cents),0) FROM income").fetchone()[0]
  count=c.execute("SELECT COUNT(*) FROM income").fetchone()[0]
  pending=c.execute("SELECT COUNT(*) FROM done").fetchone()[0]
 await u.message.reply_text(f"Qeydə alınmış real gəlir: {cash(total)}\nÖdəniş sayı: {count}\nTamamlanmış tapşırıq qeydləri: {pending}\nBu, faktiki aldığın pulların uçotudur; platformadan çıxarılan balans deyil.")
async def history(u,ctx):
 if not await allowed(u): return
 with connect() as c:
  rows=c.execute("SELECT income.cents,income.note,tasks.title FROM income LEFT JOIN tasks ON tasks.id=income.task_id ORDER BY income.id DESC LIMIT 15").fetchall()
  ds=c.execute("SELECT done.note,tasks.title FROM done JOIN tasks ON tasks.id=done.task_id ORDER BY done.id DESC LIMIT 10").fetchall()
 s=["Ödənişlər:"]+[f"+{cash(r['cents'])} — {r['title']} — {r['note']}" for r in rows]
 if not rows:s.append("Hələ ödəniş yoxdur.")
 s.append("\nTamamlanan işlər:"); s += [f"• {r['title']} — {r['note']}" for r in ds] or ["Hələ qeyd yoxdur."]
 await u.message.reply_text("\n".join(s))
def main():
 if not TOKEN: raise RuntimeError("TELEGRAM_BOT_TOKEN təyin edilməyib")
 app=Application.builder().token(TOKEN).build()
 for cmd,fn in [("start",start),("id",myid),("tasks",tasks),("done",done),("paid",paid),("balance",balance),("history",history),("users",users),("adduser",adduser),("removeuser",removeuser)]:
  app.add_handler(CommandHandler(cmd,fn))
 log.info("TaskBot AZ starting"); app.run_polling()
if __name__=="__main__": main()
