import hashlib
import hmac
import os
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

BASE = "https://api.binance.com"
COUPON_WORDS = ("coupon", "voucher", "promo code", "redemption code", "kupon", "kupon kodu")
CAMPAIGN_WORDS = ("launchpool", "megadrop", "hodler", "airdrop", "rewards", "bonus", "staking")

def _signed_get(path: str, params: dict, api_key: str, secret: str):
    query = urllib.parse.urlencode({**params, "timestamp": int(time.time() * 1000), "recvWindow": 5000})
    signature = hmac.new(secret.encode(), query.encode(), hashlib.sha256).hexdigest()
    url = f"{BASE}{path}?{query}&signature={signature}"
    request = urllib.request.Request(url, headers={"X-MBX-APIKEY": api_key, "User-Agent": "AI-Binance-Trader/0.1"})
    with urllib.request.urlopen(request, timeout=15) as response:
        return __import__("json").loads(response.read().decode("utf-8"))

def fetch_earn_products(api_key: str, secret: str, size: int = 100) -> list:
    if not api_key or not secret:
        return [{"type": "Earn", "error": "Məhsul APR siyahısı üçün ayrıca Binance MAINNET read-only API açarı tələb olunur."}]
    products = []
    for kind, path in (
        ("Flexible", "/sapi/v1/simple-earn/flexible/list"),
        ("Locked", "/sapi/v1/simple-earn/locked/list"),
    ):
        try:
            data = _signed_get(path, {"current": 1, "size": size}, api_key, secret)
            for item in data.get("rows", []):
                apr_raw = item.get("latestAnnualPercentageRate") or item.get("annualPercentageRate") or 0
                try:
                    apr = float(apr_raw) * 100
                except (TypeError, ValueError):
                    apr = 0.0
                products.append({
                    "type": kind,
                    "asset": item.get("asset", "?"),
                    "apr": apr,
                    "min": item.get("minPurchaseAmount"),
                    "max": item.get("maxPurchaseAmount"),
                    "days": item.get("duration"),
                    "can_redeem_early": item.get("canRedeemEarly"),
                    "sold_out": item.get("soldOut", False),
                    "product_id": item.get("productId"),
                })
        except Exception as exc:
            products.append({"type": kind, "error": str(exc)[:180]})
    return products

def fetch_campaign_headlines(feed_url: str) -> list:
    if not feed_url:
        return []
    if not feed_url.startswith("https://"):
        raise ValueError("Kampaniya RSS ünvanı HTTPS olmalıdır.")
    request = urllib.request.Request(feed_url, headers={"User-Agent": "AI-Binance-Trader/0.1"})
    with urllib.request.urlopen(request, timeout=15) as response:
        root = ET.fromstring(response.read())
    found = []
    for item in root.findall(".//item")[:50]:
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        lower = title.lower()
        if not title or any(word in lower for word in COUPON_WORDS):
            continue
        if any(word in lower for word in CAMPAIGN_WORDS):
            found.append({"title": title[:220], "link": link})
    return found[:10]

def format_earn_report(products: list, campaigns: list) -> str:
    lines = ["💰 BINANCE EARN / BONUS İCMALI"]
    valid = [p for p in products if not p.get("error") and not p.get("sold_out")]
    valid.sort(key=lambda p: p.get("apr", 0), reverse=True)
    if valid:
        lines.append("\nEarn məhsulları (APR illik göstəricidir, dəyişə bilər):")
        for p in valid[:12]:
            duration = f", müddət: {p['days']} gün" if p.get("days") else ""
            early = "erkən çıxarış var" if p.get("can_redeem_early") else "erkən çıxarış təsdiqlənməyib"
            lines.append(f"• {p['asset']} — {p['type']} — {p['apr']:.2f}% APR{duration}; {early}")
    else:
        lines.append("\nHazırda Earn məhsul siyahısı alınmadı və ya API icazəsi yoxdur.")
    errors = [p for p in products if p.get("error")]
    if errors:
        lines.append("Earn API qeydi: " + "; ".join(f"{p['type']}: {p['error']}" for p in errors[:2]))
    if campaigns:
        lines.append("\nRəsmi kampaniya lentində tapılan fürsətlər:")
        for c in campaigns:
            lines.append(f"• {c['title']}\n  {c['link']}")
    else:
        lines.append("\nRəsmi bonus səhifələri (aktiv layihə və uyğunluq Binance hesabında yoxlanmalıdır):")
        lines.append("• Launchpool / HODLer Airdrops: https://www.binance.com/en/launchpool")
        lines.append("• Megadrop: https://www.binance.com/en/megadrop/")
        lines.append("Kupon/voucher tələb edən təkliflər qəbul edilmir.")
    lines.append("\n⚠️ APR zəmanətli qazanc deyil. Bot yalnız məlumat verir; sənin təsdiqin olmadan abunəlik, köçürmə və ya alış etmir.")
    return "\n".join(lines)[:3900]
