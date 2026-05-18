"""
Crypto BD Lead Scanner — Core Intelligence Engine
Author: @justinbizdev
Optimized for CoinGecko Public Tier Rate Limits
"""

import os
import json
import time
import logging
import requests
import math
from datetime import datetime, timezone
from typing import Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)
log = logging.getLogger(__name__)

COINGECKO_BASE = "https://api.coingecko.com/api/v3"
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
COINGECKO_API_KEY = os.environ.get("COINGECKO_API_KEY", "")  # Optional Key

HEADERS = {"x-cg-demo-api-key": COINGECKO_API_KEY} if COINGECKO_API_KEY else {}

# ─── SCORING WEIGHTS ────────────────────────────────────────────────────────
WEIGHTS = {
    "price_distress":    0.30,   # severe price decline vs market
    "volume_decay":      0.25,   # low/declining volume
    "exchange_count":    0.15,   # listed on few exchanges
    "social_activity":   0.15,   # still active (will respond)
    "treasury_risk":     0.15,   # market cap vs volume ratio (burn risk)
}

# ─── FILTER THRESHOLDS ──────────────────────────────────────────────────────
FILTERS = {
    "max_volume_usd":           2_000_000,   # under $2M daily volume
    "min_volume_usd":           10_000,      # not completely dead
    "max_price_change_30d":    -15.0,        # at least -15% in 30d
    "max_exchange_count":       8,           # 8 or fewer exchanges
    "min_market_cap":           500_000,     # above dust threshold
    "max_market_cap":           50_000_000,  # not a top-100 coin (won't respond)
}


# ─── DATA INGESTION ──────────────────────────────────────────────────────────

def get_market_benchmark() -> dict:
    """Fetch BTC and ETH 30d performance as market baseline."""
    try:
        r = requests.get(
            f"{COINGECKO_BASE}/simple/price",
            params={
                "ids": "bitcoin,ethereum",
                "vs_currencies": "usd",
                "include_24hr_change": "true",
                "include_30d_change": "true",
            },
            headers=HEADERS,
            timeout=15,
        )
        r.raise_for_status()
        data = r.json()
        btc_30d = data.get("bitcoin", {}).get("usd_30d_change", 0) or 0
        eth_30d = data.get("ethereum", {}).get("usd_30d_change", 0) or 0
        benchmark = (btc_30d + eth_30d) / 2
        log.info(f"Market benchmark 30d: {benchmark:.2f}%")
        return {"benchmark_30d": benchmark, "btc_30d": btc_30d, "eth_30d": eth_30d}
    except Exception as e:
        log.warning(f"Benchmark fetch failed: {e}")
        return {"benchmark_30d": 0, "btc_30d": 0, "eth_30d": 0}


def fetch_coin_page(page: int, per_page: int = 100) -> list:
    """Fetch one page of coins from CoinGecko markets endpoint."""
    try:
        r = requests.get(
            f"{COINGECKO_BASE}/coins/markets",
            params={
                "vs_currency": "usd",
                "order": "volume_desc",
                "per_page": per_page,
                "page": page,
                "sparkline": False,
                "price_change_percentage": "7d,30d",
            },
            headers=HEADERS,
            timeout=20,
        )
        r.raise_for_status()
        return r.json()
    except Exception as e:
        log.error(f"Page {page} fetch failed: {e}")
        return []


def fetch_coin_detail(coin_id: str) -> Optional[dict]:
    """Fetch exchange count and social data for a specific coin."""
    try:
        # Respect rate limits between detailed single asset calls
        time.sleep(1.5)  
        r = requests.get(
            f"{COINGECKO_BASE}/coins/{coin_id}",
            params={
                "localization": False,
                "tickers": True,
                "market_data": False,
                "community_data": True,
                "developer_data": False,
            },
            headers=HEADERS,
            timeout=20,
        )
        r.raise_for_status()
        return r.json()
    except Exception as e:
        log.warning(f"Detail fetch failed for {coin_id}: {e}")
        return None


# ─── SCORING ENGINE ──────────────────────────────────────────────────────────

def score_price_distress(change_30d: float, benchmark_30d: float) -> float:
    """Score 0–100. Higher = more distressed relative to market."""
    relative_pain = (benchmark_30d - change_30d)
    if relative_pain <= 0:
        return 0.0
    return min(100.0, (relative_pain / 50.0) * 100)


def score_volume_decay(volume_24h: float, market_cap: float) -> float:
    """Score 0–100. Low volume relative to market cap = liquidity decay."""
    if market_cap <= 0:
        return 0.0
    ratio = (volume_24h / market_cap) * 100
    if ratio >= 5.0:
        return 0.0
    if ratio <= 0.05:
        return 100.0
    return min(100.0, (1 - math.log(ratio / 0.05) / math.log(100)) * 100)


def score_exchange_count(exchange_count: int) -> float:
    """Score 0–100. Fewer exchanges = higher advisory need."""
    if exchange_count >= 10:
        return 0.0
    if exchange_count <= 1:
        return 100.0
    return ((10 - exchange_count) / 9.0) * 100


def score_social_activity(coin_detail: Optional[dict]) -> float:
    """Proxy: community data signals the team still cares / will respond."""
    if not coin_detail:
        return 50.0
    community = coin_detail.get("community_data", {}) or {}
    twitter = community.get("twitter_followers") or 0
    telegram = community.get("telegram_channel_user_count") or 0

    score = 0.0
    if 1_000 <= twitter <= 100_000:
        score += 50.0
    elif twitter > 0:
        score += 20.0
    if 500 <= telegram <= 50_000:
        score += 50.0
    elif telegram > 0:
        score += 20.0
    return min(100.0, score)


def score_treasury_risk(market_cap: float, volume_24h: float, change_30d: float) -> float:
    """Urgency scoring reflecting burn risk and runway pressures."""
    score = 0.0
    if market_cap < 5_000_000 and volume_24h < 100_000:
        score += 60.0
    elif market_cap < 10_000_000 and volume_24h < 500_000:
        score += 30.0
    if change_30d < -40:
        score += 40.0
    elif change_30d < -25:
        score += 20.0
    return min(100.0, score)


def compute_composite_score(p_s, v_s, e_s, s_s, t_s) -> float:
    return (
        p_s * WEIGHTS["price_distress"] +
        v_s * WEIGHTS["volume_decay"] +
        e_s * WEIGHTS["exchange_count"] +
        s_s * WEIGHTS["social_activity"] +
        t_s * WEIGHTS["treasury_risk"]
    )


def classify_opportunity(scores: dict, coin: dict) -> dict:
    """Map score profile to primary service opportunity."""
    primary_service = "CEX Listing Strategy"
    angle = "Expand exchange presence to recover liquidity and price discovery"

    if scores["volume_decay"] > 70 and scores["price_distress"] > 60:
        primary_service = "Market Maker Advisory"
        angle = "Visible liquidity decay — order book likely thin or manipulated. MM audit would expose structural issues."
    elif scores["treasury_risk"] > 60:
        primary_service = "Treasury Management"
        angle = "Market cap declining fast with low volume suggests runway pressure. Treasury strategy is urgent."
    elif scores["exchange_count"] > 70:
        primary_service = "CEX Listing Strategy"
        angle = "Only on a few exchanges. Wider listing = more liquidity, better price support, more visibility."

    return {"primary_service": primary_service, "angle": angle}


# ─── LEAD QUALIFICATION ──────────────────────────────────────────────────────

def passes_filters(coin: dict, benchmark_30d: float) -> bool:
    vol = coin.get("total_volume") or 0
    mc  = coin.get("market_cap") or 0
    chg30 = coin.get("price_change_percentage_30d_in_currency") or 0

    if not (FILTERS["min_volume_usd"] <= vol <= FILTERS["max_volume_usd"]):
        return False
    if not (FILTERS["min_market_cap"] <= mc <= FILTERS["max_market_cap"]):
        return False
    if chg30 >= FILTERS["max_price_change_30d"]:
        return False
    return True


def build_lead(coin: dict, detail: Optional[dict], benchmark: dict) -> Optional[dict]:
    benchmark_30d = benchmark["benchmark_30d"]
    change_30d = coin.get("price_change_percentage_30d_in_currency") or 0
    change_7d  = coin.get("price_change_percentage_7d_in_currency") or 0
    volume_24h = coin.get("total_volume") or 0
    market_cap = coin.get("market_cap") or 0

    exchange_count = 3
    if detail and detail.get("tickers"):
        exchanges = set(t.get("market", {}).get("name", "") for t in detail["tickers"])
        exchange_count = len(exchanges)

    price_s    = score_price_distress(change_30d, benchmark_30d)
    volume_s   = score_volume_decay(volume_24h, market_cap)
    exchange_s = score_exchange_count(exchange_count)
    social_s   = score_social_activity(detail)
    treasury_s = score_treasury_risk(market_cap, volume_24h, change_30d)

    composite = compute_composite_score(price_s, volume_s, exchange_s, social_s, treasury_s)

    if composite < 45:
        return None

    opportunity = classify_opportunity(
        {"volume_decay": volume_s, "price_distress": price_s,
         "treasury_risk": treasury_s, "exchange_count": exchange_s},
        coin
    )

    distress_flags = []
    if change_30d < -30 and benchmark_30d > 0:
        distress_flags.append(f"DOWN {abs(change_30d):.0f}% while market UP {benchmark_30d:.0f}%")
    if volume_24h < 100_000:
        distress_flags.append("CRITICAL volume ($<100K/day)")
    elif volume_24h < 500_000:
        distress_flags.append("LOW volume (<$500K/day)")
    if exchange_count <= 3:
        distress_flags.append(f"ONLY {exchange_count} exchange(s)")
    if treasury_s > 60:
        distress_flags.append("TREASURY risk detected")
    if change_7d < -15:
        distress_flags.append(f"ACCELERATING decline ({change_7d:.0f}% 7d)")

    community = (detail or {}).get("community_data", {}) or {}
    links_data = (detail or {}).get("links", {}) or {}
    twitter_url = links_data.get("twitter_screen_name", "")
    telegram_handle = links_data.get("telegram_channel_identifier", "")
    homepage_list = links_data.get("homepage", []) or [""]
    website = homepage_list[0] if homepage_list else None

    return {
        "id": coin["id"],
        "name": coin["name"],
        "symbol": coin["symbol"].upper(),
        "rank": coin.get("market_cap_rank"),
        "price_usd": coin.get("current_price"),
        "change_7d": change_7d,
        "change_30d": change_30d,
        "volume_24h": volume_24h,
        "market_cap": market_cap,
        "exchange_count": exchange_count,
        "composite_score": round(composite, 1),
        "scores": {
            "price_distress": round(price_s, 1),
            "volume_decay": round(volume_s, 1),
            "exchange_count": round(exchange_s, 1),
            "social_activity": round(social_s, 1),
            "treasury_risk": round(treasury_s, 1),
        },
        "distress_flags": distress_flags,
        "primary_service": opportunity["primary_service"],
        "outreach_angle": opportunity["angle"],
        "twitter": f"@{twitter_url}" if twitter_url else None,
        "telegram": f"t.me/{telegram_handle}" if telegram_handle else None,
        "website": website or None,
        "twitter_followers": community.get("twitter_followers"),
        "benchmark_30d": round(benchmark_30d, 2),
        "scanned_at": datetime.now(timezone.utc).isoformat(),
    }


# ─── TELEGRAM ALERT ──────────────────────────────────────────────────────────

def format_alert(lead: dict) -> str:
    score = lead["composite_score"]
    urgency_bar = "🔴" if score >= 75 else "🟠" if score >= 60 else "🟡"
    flags_str = "\n".join(f"  ⚠️ {f}" for f in lead["distress_flags"])

    score_breakdown = (
        f"  Price Distress:  {lead['scores']['price_distress']:.0f}/100\n"
        f"  Volume Decay:    {lead['scores']['volume_decay']:.0f}/100\n"
        f"  Exchange Gap:    {lead['scores']['exchange_count']:.0f}/100\n"
        f"  Social Active:   {lead['scores']['social_activity']:.0f}/100\n"
        f"  Treasury Risk:   {lead['scores']['treasury_risk']:.0f}/100"
    )

    contacts = []
    if lead.get("twitter"):
        contacts.append(f"X: {lead['twitter']}")
    if lead.get("telegram"):
        contacts.append(f"TG: {lead['telegram']}")
    if lead.get("website"):
        contacts.append(f"Web: {lead['website']}")
    contacts_str = " | ".join(contacts) if contacts else "Not found"

    volume_fmt = f"${lead['volume_24h']:,.0f}"
    mc_fmt = f"${lead['market_cap']:,.0f}"

    return f"""
{urgency_bar} *NEW BD LEAD* — Confidence {score:.0f}/100

*{lead['name']} (${lead['symbol']})*
Rank #{lead['rank']} on CoinGecko

📉 *Distress Signals:*
{flags_str}

📊 *Metrics:*
  Vol 24h:   {volume_fmt}
  Mkt Cap:   {mc_fmt}
  7d Change: {lead['change_7d']:+.1f}%
  30d Change:{lead['change_30d']:+.1f}%
  Exchanges: {lead['exchange_count']}
  Market 30d:{lead['benchmark_30d']:+.1f}% (benchmark)

🎯 *Primary Opportunity:* {lead['primary_service']}
💬 *Outreach Angle:*
_{lead['outreach_angle']}_

📡 *Score Breakdown:*
{score_breakdown}

🔗 *Contact Points:*
{contacts_str}

🕐 _{lead['scanned_at'][:16].replace('T',' ')} UTC_
""".strip()


def send_telegram_alert(lead: dict) -> bool:
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        log.warning("Telegram credentials not set — printing to console")
        print(format_alert(lead))
        return True
    try:
        msg = format_alert(lead)
        r = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": msg,
                "parse_mode": "Markdown",
                "disable_web_page_preview": True,
            },
            timeout=10,
        )
        r.raise_for_status()
        return True
    except Exception as e:
        log.error(f"Telegram send failed: {e}")
        return False


def send_summary_alert(leads: list[dict]) -> None:
    if not leads:
        return
    lines = [f"📋 *DAILY SCAN SUMMARY — {len(leads)} leads found*\n"]
    for i, lead in enumerate(leads[:10], 1):
        score = lead["composite_score"]
        icon = "🔴" if score >= 75 else "🟠" if score >= 60 else "🟡"
        lines.append(
            f"{i}. {icon} *{lead['name']}* (${lead['symbol']}) — "
            f"Score: {score:.0f} | {lead['primary_service']}"
        )
    msg = "\n".join(lines)
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "Markdown"},
            timeout=10,
        )
    except Exception as e:
        log.error(f"Summary send failed: {e}")


# ─── DEDUPLICATION ───────────────────────────────────────────────────────────

def load_seen_ids() -> set:
    path = "data/seen_leads.json"
    if os.path.exists(path):
        try:
            with open(path) as f:
                return set(json.load(f))
        except Exception:
            return set()
    return set()


def save_seen_ids(seen: set) -> None:
    os.makedirs("data", exist_ok=True)
    with open("data/seen_leads.json", "w") as f:
        json.dump(list(seen), f)


def save_leads_log(leads: list[dict]) -> None:
    os.makedirs("data", exist_ok=True)
    path = f"data/leads_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M')}.json"
    with open(path, "w") as f:
        json.dump(leads, f, indent=2)
    log.info(f"Saved {len(leads)} leads to {path}")


# ─── MAIN SCAN LOOP ──────────────────────────────────────────────────────────

def run_scan(pages: int = 5, send_individual_alerts: bool = True):
    log.info("=== Crypto BD Lead Scanner starting ===")

    benchmark = get_market_benchmark()
    seen_ids = load_seen_ids()
    new_leads = []
    total_scanned = 0

    for page in range(1, pages + 1):
        log.info(f"Scanning page {page}/{pages}...")
        coins = fetch_coin_page(page)
        
        if page < pages:
            time.sleep(12)  # Cooldown block to avoid Public HTTP 429 filters

        if not coins:
            log.warning(f"No data returned for page {page}, skipping.")
            continue

        for coin in coins:
            total_scanned += 1
            try:
                if not passes_filters(coin, benchmark["benchmark_30d"]):
                    continue

                detail = fetch_coin_detail(coin["id"])
                lead = build_lead(coin, detail, benchmark)

                if lead is None:
                    continue

                if lead["id"] in seen_ids:
                    log.info(f"Skipping already-seen: {lead['name']}")
                    continue

                log.info(f"✅ LEAD: {lead['name']} — Score {lead['composite_score']}")
                new_leads.append(lead)
                seen_ids.add(lead["id"])

                if send_individual_alerts:
                    send_telegram_alert(lead)
                    time.sleep(1.5)

            except Exception as item_error:
                log.error(f"Error processing item token {coin.get('id', 'unknown')}: {item_error}")
                continue

    log.info(f"Scan complete. {total_scanned} coins scanned. {len(new_leads)} new leads.")

    if new_leads:
        save_leads_log(new_leads)
        save_seen_ids(seen_ids)
        if not send_individual_alerts:
            for lead in new_leads:
                send_telegram_alert(lead)
        send_summary_alert(sorted(new_leads, key=lambda x: -x["composite_score"]))

    return new_leads


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--pages", type=int, default=5, help="CoinGecko pages to scan")
    parser.add_argument("--digest", action="store_true", help="Batch mode: send summary only")
    args = parser.parse_args()
    run_scan(pages=args.pages, send_individual_alerts=not args.digest)
