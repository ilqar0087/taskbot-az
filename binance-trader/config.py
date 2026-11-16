import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()

def _bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}

@dataclass(frozen=True)
class Settings:
    telegram_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    owner_id: str = os.getenv("OWNER_TELEGRAM_ID", "")
    trading_mode: str = os.getenv("TRADING_MODE", "testnet").lower()
    auto_trade_testnet: bool = _bool("AUTO_TRADE_TESTNET", False)
    api_key: str = os.getenv("BINANCE_API_KEY", "")
    api_secret: str = os.getenv("BINANCE_API_SECRET", "")
    earn_api_key: str = os.getenv("BINANCE_EARN_API_KEY", "")
    earn_api_secret: str = os.getenv("BINANCE_EARN_API_SECRET", "")
    scan_interval: int = max(60, int(os.getenv("SCAN_INTERVAL_SECONDS", "300")))
    symbols: tuple = tuple(s.strip() for s in os.getenv(
        "SYMBOLS", "BTC/USDT,ETH/USDT,BNB/USDT,SOL/USDT,XRP/USDT"
    ).split(",") if s.strip())
    spot_enabled: bool = _bool("SPOT_ENABLED", True)
    futures_enabled: bool = _bool("FUTURES_ENABLED", True)
    max_leverage: int = min(10, max(3, int(os.getenv("MAX_LEVERAGE", "10"))))
    risk_per_trade_pct: float = min(1.0, max(0.1, float(os.getenv("RISK_PER_TRADE_PCT", "0.5"))))
    daily_loss_limit_pct: float = min(5.0, max(0.5, float(os.getenv("DAILY_LOSS_LIMIT_PCT", "2.0"))))
    max_drawdown_pct: float = min(10.0, max(1.0, float(os.getenv("MAX_DRAWDOWN_PCT", "5.0"))))
    risk_equity_usd: float = max(0.0, float(os.getenv("RISK_EQUITY_USD", "0")))
    database_path: str = os.getenv("DATABASE_PATH", "/data/trader.sqlite3")

    def validate(self) -> None:
        if self.trading_mode != "testnet":
            raise RuntimeError("Only Binance TESTNET mode is permitted in this build.")
        if self.auto_trade_testnet:
            raise RuntimeError("Order execution is not implemented in this release; keep AUTO_TRADE_TESTNET=false.")
        if self.max_leverage > 10:
            raise RuntimeError("Leverage above 10x is not permitted.")
