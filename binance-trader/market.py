import ccxt

from config import Settings

def make_exchange(settings: Settings, futures: bool = True):
    cls = ccxt.binanceusdm if futures else ccxt.binance
    params = {
        "enableRateLimit": True,
        "timeout": 20000,
        "options": {"defaultType": "future" if futures else "spot"},
    }
    if settings.api_key and settings.api_secret:
        params.update({"apiKey": settings.api_key, "secret": settings.api_secret})
    exchange = cls(params)
    # This project deliberately refuses live mode.
    exchange.set_sandbox_mode(True)
    return exchange

def get_snapshot(exchange, symbol: str) -> dict:
    markets = exchange.load_markets()
    if symbol not in markets:
        raise ValueError(f"{symbol} is not available on this Binance market.")
    candles = {}
    for timeframe in ("15m", "1h", "4h", "1d", "1w"):
        candles[timeframe] = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=120)
    book = exchange.fetch_order_book(symbol, limit=20)
    ticker = exchange.fetch_ticker(symbol)
    snapshot = {
        "symbol": symbol,
        "candles": candles,
        "orderbook": book,
        "last": float(ticker.get("last") or 0),
        "spread_pct": 0.0,
    }
    bid, ask = ticker.get("bid"), ticker.get("ask")
    if bid and ask and (bid + ask):
        snapshot["spread_pct"] = ((ask - bid) / ((ask + bid) / 2)) * 100
    if exchange.has.get("fetchFundingRate"):
        try:
            snapshot["funding"] = exchange.fetch_funding_rate(symbol).get("fundingRate")
        except Exception:
            snapshot["funding"] = None
    else:
        snapshot["funding"] = None
    if exchange.has.get("fetchOpenInterest"):
        try:
            oi = exchange.fetch_open_interest(symbol)
            snapshot["open_interest"] = oi.get("openInterestAmount") or oi.get("openInterestValue")
        except Exception:
            snapshot["open_interest"] = None
    else:
        snapshot["open_interest"] = None
    return snapshot
