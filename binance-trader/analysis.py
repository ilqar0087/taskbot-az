from math import isfinite

def ema(values, period):
    if len(values) < period:
        return None
    alpha = 2 / (period + 1)
    result = sum(values[:period]) / period
    for value in values[period:]:
        result = value * alpha + result * (1 - alpha)
    return result

def rsi(values, period=14):
    if len(values) <= period:
        return None
    gains, losses = [], []
    for i in range(1, len(values)):
        change = values[i] - values[i - 1]
        gains.append(max(change, 0))
        losses.append(max(-change, 0))
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_loss == 0:
        return 100.0
    return 100 - (100 / (1 + avg_gain / avg_loss))

def atr(rows, period=14):
    if len(rows) <= period:
        return None
    trs = []
    for i in range(1, len(rows)):
        high, low, prev_close = rows[i][2], rows[i][3], rows[i - 1][4]
        trs.append(max(high - low, abs(high - prev_close), abs(low - prev_close)))
    return sum(trs[-period:]) / period

def timeframe_vote(rows):
    closes = [float(x[4]) for x in rows]
    volumes = [float(x[5]) for x in rows]
    e20, e50 = ema(closes, 20), ema(closes, 50)
    rv = rsi(closes)
    if not e20 or not e50 or rv is None:
        return 0, {}
    macd_fast, macd_slow = ema(closes, 12), ema(closes, 26)
    macd_signal = ema(closes[-40:], 9) if len(closes) >= 40 else None
    macd_hist = (macd_fast - macd_slow - macd_signal) if macd_signal is not None else 0
    vol_base = sum(volumes[-21:-1]) / max(1, len(volumes[-21:-1]))
    vol_ratio = volumes[-1] / vol_base if vol_base else 1
    vote = 0
    if closes[-1] > e20 > e50: vote += 2
    elif closes[-1] < e20 < e50: vote -= 2
    if rv >= 52 and rv <= 72: vote += 1
    elif rv <= 48 and rv >= 28: vote -= 1
    if macd_hist > 0: vote += 1
    elif macd_hist < 0: vote -= 1
    if vol_ratio >= 1.15: vote += 1 if vote >= 0 else -1
    return vote, {"rsi": round(rv, 1), "ema20": e20, "ema50": e50,
                  "macd_hist": macd_hist, "volume_ratio": round(vol_ratio, 2)}

def analyse(snapshot: dict, max_leverage: int = 10) -> dict:
    votes, detail = {}, {}
    for tf, rows in snapshot["candles"].items():
        vote, metrics = timeframe_vote(rows)
        votes[tf] = vote
        detail[tf] = metrics
    weighted = votes.get("15m", 0) + 2 * votes.get("1h", 0) + 3 * votes.get("4h", 0)
    bids = snapshot["orderbook"].get("bids", [])
    asks = snapshot["orderbook"].get("asks", [])
    bid_qty = sum(float(x[1]) for x in bids[:10])
    ask_qty = sum(float(x[1]) for x in asks[:10])
    imbalance = (bid_qty - ask_qty) / (bid_qty + ask_qty) if bid_qty + ask_qty else 0
    funding = snapshot.get("funding")
    if funding is not None:
        if funding > 0.001: weighted -= 1
        elif funding < -0.001: weighted += 1
    if imbalance > 0.12: weighted += 1
    elif imbalance < -0.12: weighted -= 1

    price = float(snapshot["last"])
    rows = snapshot["candles"]["1h"]
    volatility = atr(rows)
    if not price or not volatility or not isfinite(volatility):
        return {"action": "WAIT", "reason": "Kifayət qədər bazar məlumatı yoxdur."}
    confidence = min(99, 50 + abs(weighted) * 3)
    direction = "LONG" if weighted >= 7 else "SHORT" if weighted <= -7 else "WAIT"
    if snapshot.get("spread_pct", 0) > 0.15:
        direction = "WAIT"
    if direction == "LONG" and detail.get("4h", {}).get("rsi", 50) > 75:
        direction = "WAIT"
    if direction == "SHORT" and detail.get("4h", {}).get("rsi", 50) < 25:
        direction = "WAIT"

    stop_distance = volatility * 1.8
    if direction == "LONG":
        stop, target = price - stop_distance, price + volatility * 3.0
    elif direction == "SHORT":
        stop, target = price + stop_distance, price - volatility * 3.0
    else:
        stop = target = None

    if direction == "WAIT":
        leverage = 1
    elif confidence >= 97 and volatility / price <= 0.02 and abs(imbalance) >= 0.25:
        leverage = min(10, max_leverage)
    elif confidence >= 90:
        leverage = min(7, max_leverage)
    elif confidence >= 82:
        leverage = min(5, max_leverage)
    else:
        leverage = min(3, max_leverage)

    return {
        "action": direction, "confidence": confidence, "price": price,
        "stop_loss": stop, "take_profit": target, "leverage": leverage,
        "risk_reward": round((volatility * 3.0) / stop_distance, 2),
        "atr_pct": round(volatility / price * 100, 3),
        "orderbook_imbalance": round(imbalance, 3), "funding": funding,
        "spread_pct": round(snapshot.get("spread_pct", 0), 4),
        "votes": votes, "metrics": detail,
        "reason": "Çoxzamanlı trend, momentum, həcm, order-book və funding yoxlaması."
    }
