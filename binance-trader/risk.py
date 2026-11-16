def approve_trade(signal: dict, equity: float, settings, daily_pnl_pct: float = 0.0) -> tuple[bool, str, dict]:
    if signal.get("action") not in {"LONG", "SHORT"}:
        return False, "Ticarət siqnalı yoxdur.", {}
    if signal.get("confidence", 0) < 76:
        return False, "Siqnalın etibarlılığı tələb olunan həddən aşağıdır.", {}
    if signal.get("risk_reward", 0) < 1.5:
        return False, "Mənfəət/zərər nisbəti uyğun deyil.", {}
    if daily_pnl_pct <= -settings.daily_loss_limit_pct:
        return False, "Gündəlik zərər limiti dolub; yeni ticarət dayandırıldı.", {}
    if equity <= 0:
        return False, "Balans müəyyən edilməyib.", {}
    entry, stop = signal["price"], signal["stop_loss"]
    stop_gap = abs(entry - stop)
    if stop_gap <= 0:
        return False, "Stop-Loss məsafəsi yanlışdır.", {}
    risk_usd = equity * settings.risk_per_trade_pct / 100
    quantity = risk_usd / stop_gap
    notional_cap = equity * 0.10 * signal["leverage"]
    quantity = min(quantity, notional_cap / entry)
    if quantity * entry < 10:
        return False, "Hesablanmış mövqe Binance minimum sifarişindən kiçikdir.", {}
    return True, "Risk yoxlaması keçildi.", {
        "risk_usd": round(risk_usd, 2),
        "quantity": quantity,
        "notional": round(quantity * entry, 2),
        "leverage": signal["leverage"],
    }
