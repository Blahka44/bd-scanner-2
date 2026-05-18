"""
Crypto BD Lead Scanner — Core Intelligence Engine
Author: @justinbizdev
Optimized for CoinGecko Public Tier Rate Limits & Action Safety
"""

import os
import json
import time
import logging
import requests
import math
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Set

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)
log = logging.getLogger(__name__)

COINGECKO_BASE = "https://api.coingecko.com/api/v3"
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
COINGECKO_API_KEY = os.environ.get("COINGECKO_API_KEY", "")

HEADERS = {"x-cg-demo-api-key": COINGECKO_API_KEY} if COINGECKO_API_KEY else {}

# ─── SCORING WEIGHTS ────────────────────────────────────────────────────────
WEIGHTS = {
    "price_distress":    0.30,
    "volume_decay":      0.25,
    "exchange_count":    0.15,
    "social_activity":   0.15,
    "treasury_risk":     0.15,
}

# ─── RELAXED PRODUCTION FILTER THRESHOLDS ────────────────────────────────────
FILTERS = {
    "max_volume_usd":           5_000_000,
    "min_volume_usd":           5_000,
    "max_price_change_30d":     5.0,
    "max_exchange_count":       12,
    "min_market_cap":           300_000,
    "max_market_cap":           75_000_000,
}


# ─── UTILITY FUNCTIONS ────────────────────────────────────────────────────────

def escape_markdown(text: str) -> str:
    """Escape markdown special characters to prevent Telegram API parsing crashes."""
    if not text:
        return ""
    escape_chars = r'_*`['
    return "".join(f"\\{c}" if c in escape_chars else c for c in text)


# ─── DATA INGESTION ──────────────────────────────────────────────────────────

def get_market_benchmark() -> Dict[str, float]:
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
        log.info(f"Market benchmark 30d baseline calculated: {benchmark:.2f}%")
        return {"benchmark_30d": benchmark, "btc_30d": btc_30d, "eth_30d": eth_30d}
    except Exception as e:
        log.warning(f"Benchmark framework fetch failed, defaulting to 0: {e}")
        return {"benchmark_30d": 0, "btc_30d": 0, "eth_30d": 0}


def fetch_coin_page(page: int, per_page: int = 100) -> List[Dict[str, Any]]:
    """Fetch one page of coins ordered by volume from CoinGecko markets endpoint."""
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
        log.error(f"Page {page} market ingestion failed: {e}")
        return []


def fetch_coin_detail(coin_id: str, retries: int = 0) -> Optional[Dict[str, Any]]:
    """Fetch exchange tickers and social metadata with adaptive backup cooling periods."""
    try:
        # Increased baseline cooldown to prevent hitting the public limits aggressively
        time.sleep(3.5)  
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
        
        if r.status_code == 429:
            if retries >= 3:
                log.error(f"Max pacing cooling retries reached for target {coin_id}. Dropping pipeline node.")
                return None
            # Exponential backoff pacing matrix: 35s, 70s, 140s
            cool_down = 35 * (2 ** retries)
            log.warning(f"Rate limit hit (HTTP 429). Execution pacing backoff engaged. Cooling down for {cool_down}s...")
            time.sleep(cool_down)
            return fetch_coin_detail(coin_id, retries + 1)
            
        r.raise_for_status()
        return r.json()
    except Exception as e:
        log.warning(f"Metadata extraction failed for asset context {coin_id}: {e}")
        return None


# ─── MATH & SCORING INTELLIGENCE ENGINE ───────────────────────────────────────

def score_price_distress(change_30d: float, benchmark_30d: float) -> float:
    relative_pain = (benchmark_30d - change_30d)
    if relative_pain <= 0:
        return 0.0
    return min(100.0, (relative_pain / 50.0) * 100)


def score_volume_decay(volume_24h: float, market_cap: float) -> float:
    if market_cap <= 0:
        return 0.0
    ratio = (volume_24h / market_cap) * 100
    if ratio >= 5.0:
        return 0.0
    if ratio <= 0.05:
        return 100.0
    return min(100.0, (1 - math.log(ratio / 0.05) / math.log(100)) * 100)


def score_exchange_count(exchange_count: int) -> float:
    if exchange_count >= FILTERS["max_exchange_count"]:
        return 0.0
    if exchange_count <= 1:
        return 100.0
    return ((FILTERS["max_exchange_count"] - exchange_count) / float(FILTERS["max_exchange_count"] - 1)) * 100


def score_social_activity(coin_detail: Optional[Dict[str, Any]]) -> float:
    if not coin_detail:
        return 50.0
    community = coin_detail.get("community_data", {}) or {}
    twitter = community.get("twitter_followers") or 0
    telegram = community.get("telegram_channel_user_count") or 0

    score = 0.0
    if 1_000 <= twitter <= 150_000:
        score += 50.0
    elif twitter > 150_000:
        score += 20.0
    if 500 <= telegram <= 50_000:
        score += 50.0
    elif telegram > 50_000:
        score += 20.0
    return min(100.0, score)


def score_social_activity(coin_detail: Optional[Dict[str, Any]]) -> float:
    if not coin_detail:
        return 50.0
    community = coin_detail.get("community_data", {}) or {}
    twitter = community.get("twitter_followers") or 0
    telegram = community.get("telegram_channel_user_count") or 0

    score = 0.0
    if 1_000 <= twitter <= 150_000:
        score += 50.0
    elif twitter > 150_000:
        score += 20.0
    if 500 <= telegram <= 50_000:
        score += 50.0
    elif telegram > 50_000:
        score += 20.0
    return min(100.0, score)


def score_treasury_risk(market_cap: float, volume_24h: float, change_30d: float) -> float:
    score = 0.0
    if market_cap < 5_000_000 and volume_24h < 100_000:
        score += 60.0
    elif market_cap < 15_000_000 and volume_24h < 500_000:
        score += 30.0
    if change_30d < -30:
        score += 40.0
    elif change_30d < -15:
        score += 20.0
    return min(100.0, score)


def compute_composite_score(p_s: float, v_s: float, e_s: float, s_s: float, t_s: float) -> float:
    return (
        p_s * WEIGHTS["price_distress"] +
        v_s * WEIGHTS["volume_decay"] +
        e_s * WEIGHTS["exchange_count"] +
        s_s * WEIGHTS["social_activity"] +
        t_s * WEIGHTS["treasury_risk"]
    )


def classify_opportunity(scores: Dict[str, float]) -> Dict[str, str]:
    primary_service = "CEX Listing Strategy"
    angle = "Expand secondary market listing layout to counter order book fragmentation and support price discovery."

    if scores["volume_decay"] > 70 and scores["price_distress"] > 55:
        primary_service = "Market Maker Advisory"
        angle = "Advanced order book liquidity decay observed. Spread gap optimization and depth restructuring required."
    elif scores["treasury_risk"] > 60:
        primary_service = "Treasury Management"
        angle = "Low volume profile combined with capital bleed indicates runway pressures. Structural treasury architecture suggested."
    elif scores["exchange_count"] > 75:
        primary_service = "CEX Listing Strategy"
        angle = "Asset is localized on thin venues. Broader exchange access required to preserve long term token survival."

    return {"primary_service": primary_service, "angle": angle}


# ─── FILTER & PIPELINE MANAGEMENT ───────────────────────────────────────────

def passes_filters(coin: Dict[str, Any]) -> bool:
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


def build_lead(coin: Dict[str, Any], detail: Optional[Dict[str, Any]], benchmark: Dict[str, float]) -> Optional[Dict[str, Any]]:
    benchmark_30d = benchmark["benchmark_30d"]
    change_30d = coin.get("price_change_percentage_30d_in_currency") or 0
    change_7d  = coin.get("price_change_percentage_7d_in_currency") or 0
    volume_24h = coin.get("total_volume") or 0
    market_cap = coin.get("market_cap") or 0

    exchange_count = 3
    if detail and detail.get("tickers"):
        exchanges = set(t.get("market", {}).get("name", "") for t in detail["tickers"] if t.get("market"))
        exchange_count = len(exchanges) if exchanges else 3

    price_s    = score_price_distress(change_30d, benchmark_30d)
    volume_s   = score_volume_decay(volume_24h, market_cap)
    exchange_s = score_exchange_count(exchange_count)
    social_s   = score_social_activity(detail)
    treasury_s = score_treasury_risk(market_cap, volume_24h, change_30d)

    composite = compute_composite_score(price_s, volume_s, exchange_s, social_s, treasury_s)

    if composite < 45:
        return None

    scores_dict = {
        "price_distress": price_s, "volume_decay": volume_s,
        "exchange_count": exchange_s, "social_activity": social_s, "treasury_risk": treasury_s
    }
    opportunity = classify_opportunity(scores_dict)

    distress_flags = []
    if change_30d < -20 and benchmark_30d > 0:
        distress_flags.append(f"Divergent Bleed: DOWN {abs(change_30d):.0f}% vs Strong Market")
    if volume_24h < 100_000:
        distress_flags.append("CRITICAL Liquidity: Sub-$100K daily volume depth")
    elif volume_24h < 500_000:
        distress_flags.append("Low Volume Depth: Sub-$500K daily activity profile")
    if exchange_count <= 3:
        distress_flags.append(f"Venue Concentration: Only listed on {exchange_count} CEX/DEX")
    if treasury_s > 60:
        distress_flags.append("High Treasury Pressure Pattern")
    if change_7d < -10:
        distress_flags.append(f"Accelerating Momentum Breakdown ({change_7d:.0f}% 7d)")

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
        "scores": {k: round(v, 1) for k, v in scores_dict.items()},
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


# ─── TELEGRAM COMMUNICATIONS DELIVERY LAYER ───────────────────────────────────

def format_alert(lead: dict) -> str:
    """Formats outbound diagnostic lead data into readable, structured copy blocks."""
    score = lead["composite_score"]
    urgency_bar = "🔴" if score >= 75 else "🟠" if score >= 60 else "🟡"
    flags_str = "\n".join(f"  ⚠️ {escape_markdown(f)}" for f in lead["distress_flags"])

    score_breakdown = (
        f"  Price Distress:  {lead['scores']['price_distress']:.0f}/100\n"
        f"  Volume Decay:    {lead['scores']['volume_decay']:.0f}/100\n"
        f"  Exchange Gap:    {lead['scores']['exchange_count']:.0f}/100\n"
        f"  Social Active:   {lead['scores']['social_activity']:.0f}/100\n"
        f"  Treasury Risk:   {lead['scores']['treasury_risk']:.0f}/100"
    )

    contacts = []
    if lead.get("twitter"):
        contacts.append(f"X: {escape_markdown(lead['twitter'])}")
    if lead.get("telegram"):
        contacts.append(f"TG: {escape_markdown(lead['telegram'])}")
    if lead.get("website"):
        contacts.append(f"Web: {escape_markdown(lead['website'])}")
    contacts_str = " | ".join(contacts) if contacts else "None surfaced"

    return f"""
{urgency_bar} *CRITICAL BD SIGNAL FOUND* — Score {score:.0f}/100

*{escape_markdown(lead['name'])} (${escape_markdown(lead['symbol'])})*
CoinGecko Structural Rank #{lead['rank']}

📉 *Identified Market Anomalies:*
{flags_str}

📊 *Capital Infrastructure Metrics:*
  Vol 24h:   ${lead['volume_24h']:,.0f}
  Mkt Cap:   ${lead['market_cap']:,.0f}
  7d Delta:  {lead['change_7d']:+.1f}%
  30d Delta: {lead['change_30d']:+.1f}%
  Venues:    {lead['exchange_count']} Listed
  Baseline:  {lead['benchmark_30d']:+.1f}% (Global Benchmark)

🎯 *Target Framework Match:* {escape_markdown(lead['primary_service'])}
💬 *Recommended Outreach Stance:*
_{escape_markdown(lead['outreach_angle'])}_

📡 *Multi-Dimensional Scoring Core:*
{score_breakdown}


🔗 *Surfaced Outreach Anchors:*
{contacts_str}

🕐 _{lead['scanned_at'][:16].replace('T',' ')} UTC_
""".strip()


def send_telegram_alert(lead: dict) -> bool:
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        log.warning("Telegram configuration markers missing — outputting direct logs")
        print(format_alert(lead))
        return True
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": format_alert(lead),
                "parse_mode": "Markdown",
                "disable_web_page_preview": True,
            },
            timeout=10,
        )
        r.raise_for_status()
        return True
    except Exception as e:
        log.error(f"Inbound alert routing failed for token context {lead['id']}: {e}")
        return False


def send_summary_alert(leads: list) -> None:
    if not leads:
        return
    lines = [f"📋 *PRODUCTION LEAD DISCOVERY SUMMARY — {len(leads)} Targets Surfaced*\n"]
    for i, lead in enumerate(leads[:10], 1):
        score = lead["composite_score"]
        icon = "🔴" if score >= 75 else "🟠" if score >= 60 else "🟡"
        lines.append(
            f"{i}. {icon} *{escape_markdown(lead['name'])}* (${escape_markdown(lead['symbol'])}) — "
            f"Score: {score:.0f} | {escape_markdown(lead['primary_service'])}"
        )
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": "\n".join(lines), "parse_mode": "Markdown"},
            timeout=10,
        )
    except Exception as e:
        log.error(f"Summary framework delivery failed: {e}")


# ─── DATA PERSISTENCE & DEDUPLICATION ────────────────────────────────────────

def load_seen_ids() -> Set[str]:
    path = "data/seen_leads.json"
    if os.path.exists(path):
        try:
            with open(path) as f:
                return set(json.load(f))
        except Exception:
            return set()
    return set()


def save_seen_ids(seen: Set[str]) -> None:
    os.makedirs("data", exist_ok=True)
    with open("data/seen_leads.json", "w") as f:
        json.dump(list(seen), f)


def save_leads_log(leads: List[Dict[str, Any]]) -> None:
    os.makedirs("data", exist_ok=True)
    path = f"data/leads_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M')}.json"
    with open(path, "w") as f:
        json.dump(leads, f, indent=2)


# ─── EXECUTION TUNNEL ────────────────────────────────────────────────────────

def run_scan(pages: int = 5, send_individual_alerts: bool = True):
    log.info("=== Crypto BD Lead Scanner Engine Initiated ===")

    benchmark = get_market_benchmark()
    seen_ids = load_seen_ids()
    candidate_pool = []
    new_leads = []

    for page in range(1, pages + 1):
        log.info(f"Ingesting market page matrix {page}/{pages}...")
        coins = fetch_coin_page(page)
        
        for coin in coins:
            if coin.get("id") and passes_filters(coin):
                candidate_pool.append(coin)
        
        if page < pages:
            time.sleep(6)

    log.info(f"Filtration framework passed. Surfaced {len(candidate_pool)} candidate targets.")

    # Sort candidates by total_volume ascending to handle highest-priority distress profiles first
    candidate_pool.sort(key=lambda x: x.get("total_volume", 0))

    # Capping max asset metadata hits per run to prevent public API execution gridlocks
    MAX_DEEP_SCANS = 15
    scanned_count = 0

    for coin in candidate_pool:
        if scanned_count >= MAX_DEEP_SCANS:
            log.info(f"Reached execution threshold limit ({MAX_DEEP_SCANS}) for this run cycle. Stopping.")
            break
            
        try:
            if coin["id"] in seen_ids:
                continue

            detail = fetch_coin_detail(coin["id"])
            scanned_count += 1
            
            if not detail:
                continue

            lead = build_lead(coin, detail, benchmark)
            if not lead:
                continue

            log.info(f"✅ HIGH SIGNAL DETECTED: {lead['name']} — Composite Vector Score: {lead['composite_score']}")
            new_leads.append(lead)
            seen_ids.add(lead["id"])

            if send_individual_alerts:
                send_telegram_alert(lead)

        except Exception as item_error:
            log.error(f"Execution failed on isolation token {coin.get('id')}: {item_error}")
            continue

    log.info(f"Scan cycles wrapped. Extracted {len(new_leads)} actionable leads.")

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
    parser.add_argument("--pages", type=int, default=5, help="Total CoinGecko endpoint index pages to traverse")
    parser.add_argument("--digest", action="store_true", help="Toggle batch digest summary reporting layout")
    args = parser.parse_args()
    run_scan(pages=args.pages, send_individual_alerts=not args.digest)
