import logging, os, sqlite3
from pathlib import Path
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

TOKEN=os.getenv("TELEGRAM_BOT_TOKEN")
OWNER=os.getenv("OWNER_TELEGRAM_ID")
DB=os.getenv("DATABASE_PATH","/data/taskbot.sqlite3")
logging.basicConfig(level=logging.INFO)
log=logging.getLogger("taskbot")
SITES=[
("Clickworker","https://www.clickworker.com/clickworker/","Mikrotapşırıqlar və AI məlumat tapşırıqları; ölkə uyğunluğu tələb olunur."),
("Toloka","https://toloka.ai/tolokers/","Məlumat yoxlama tapşırıqları; təkliflər ölkəyə görə dəyişir."),
("SproutGigs","https://sproutgigs.com/","Kiçik onlayn işlər; hər tapşırığın şərtlərini yoxla."),
("Fiverr","https://www.fiverr.com/","Bacarıq xidməti satışı: tərcümə, dizayn, mətn və s."),
("Upwork","https://www.upwork.com/","Freelance layihələr; müştəri təsdiqi tələb olunur."),
("make.fun","https://make.fun/","AI agentlər üçün kod yarışmaları; yalnız pulsuz girişli bountylər seçilməlidir. Qazanc yalnız qalib olduqda USDC/Solana ilədir."),
("Clustly","https://www.clustly.ai/","AI agent xidməti yerləşdirib müştəri sifarişi almaq; ödəniş USDC/Solana escrow-dadır və müştəri təsdiqi tələb olunur."),
("Superteam Earn","https://superteam.fun/earn","Yalnız agentlərə açıq (AGENT_ALLOWED/AGENT_ONLY) elanlar izlənməlidir; insan üçün olan elanlara bot müraciət etməməlidir.")
]
def connect():
 Path(DB).parent.mkdir(parents=True,exist_ok=True)
 c=sqlite3.connect(DB); c.row_factory=sqlite3.Row
 c.executescript("""
 CREATE TABLE IF NOT EXISTS tasks(id INTEGER PRIMARY KEY,title TEXT,url TEXT,note TEXT);
 CREATE TABLE IF NOT EXISTS done(id INTEGER PRIMARY KEY,task_id INTEGER,note TEXT,created TEXT);
 CREATE TABLE IF NOT EXISTS income(id INTEGER PRIMARY KEY,task_id INTEGER,cents INTEGER,note TEXT,created TEXT);
 """)
 for site in SITES:
  c.execute("INSERT OR IGNORE INTO tasks(title,url,note) SELECT ?,?,? WHERE NOT EXISTS (SELECT 1 FROM tasks WHERE title=?)",(*site,site[0]))
 c.commit(); return c
def cash(n): return f"${n/100:.2f}"
async def allowed(u):
 if not OWNER:
  await u.effective_message.reply_text(f"Bot hazırdır. Sənin Telegram ID-n: {u.effective_user.id}\nSahib ID-si serverdə OWNER_TELEGRAM_ID kimi təyin olunmalıdır.")
  return False
 if str(u.effective_user.id)!=OWNER:
  await u.effective_message.reply_text("Bu şəxsi bot yalnız sahibinin istifadəsi üçündür."); return False
 return True
async def start(u:Update,ctx:ContextTypes.DEFAULT_TYPE):
 if not await allowed(u): return
 await u.message.reply_text("TaskBot AZ hazırdır 🤖\n/tasks — platformalar\n/done ID qeyd — işi tamamlandı kimi yaz\n/paid ID məbləğ qeyd — faktiki aldığın pulu yaz\n/balance — real gəlir\n/history — tarixçə")
async def myid(u,ctx): await u.message.reply_text(f"Telegram ID: {u.effective_user.id}")
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
 for cmd,fn in [("start",start),("id",myid),("tasks",tasks),("done",done),("paid",paid),("balance",balance),("history",history)]:
  app.add_handler(CommandHandler(cmd,fn))
 log.info("TaskBot AZ starting"); app.run_polling()
if __name__=="__main__": main()
