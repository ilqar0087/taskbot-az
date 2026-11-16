import sqlite3
from pathlib import Path
from datetime import datetime, timezone

def connect(path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.execute("""CREATE TABLE IF NOT EXISTS signals(
        id INTEGER PRIMARY KEY AUTOINCREMENT, created TEXT, symbol TEXT,
        market TEXT, action TEXT, confidence INTEGER, price REAL, stop REAL,
        target REAL, leverage INTEGER, approved INTEGER, note TEXT
    )""")
    db.commit()
    return db

def save_signal(path, symbol, market, signal, approved, note):
    with connect(path) as db:
        db.execute(
            "INSERT INTO signals(created,symbol,market,action,confidence,price,stop,target,leverage,approved,note) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (datetime.now(timezone.utc).isoformat(), symbol, market,
             signal.get("action"), signal.get("confidence"), signal.get("price"),
             signal.get("stop_loss"), signal.get("take_profit"),
             signal.get("leverage"), int(approved), note)
        )

def recent(path, limit=10):
    with connect(path) as db:
        return db.execute(
            "SELECT created,symbol,market,action,confidence,price,approved,note FROM signals ORDER BY id DESC LIMIT ?",
            (limit,)
        ).fetchall()
