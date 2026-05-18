"""
Crypto BD Lead Scanner — Precision Hunting Engine
Author: @justinbizdev
Target Matrix: CG Rank 500-2000 | Volume ~$210K | 7d Drop ~ -16.90% | Exactly 3 Exchanges
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

# ─── SEARCH MATRIX SPECIFICATIONS ───────────────────────────────────────────
FILTERS = {
    "min_rank":                 500,          # Target Rank Floor
    "max_rank":                 2000,         # Target Rank Ceiling
    "min_volume_usd":           100_000,      # Smooth bracket around $210K
    "max_volume_usd":           450_000,      # Smooth bracket around $210K
    "target_price_change_7d":   -16.90,       # Your specific capitulation target
    "allowed_7d_variance":      8.0,          # Balanced variance window (-8.9% to -24.9%)
    "exact_exchange_count":     3,            # Strict listing limit
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
    """Fetch BTC and ETH 30d performance as market baseline with automatic backoff retry."""
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
        if r.status_code == 429:
            log.warning("Benchmark fetch hit rate limit. Cooling down for 30s...")
            time.sleep(30)
            return get_market_benchmark()
            
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


def fetch_coin_page(page: int, per_page: int = 100, retries: int = 0) -> List[Dict[str, Any]]:
    """Fetch market list segments using desc order to directly target ranks 500-2000."""
    try:
        # Pacing cushion to prevent immediate 429 triggers during page loops
        time.sleep(6.0)
        r = requests.get(
            f"{COINGECKO_BASE}/coins/markets",
            params={
                "vs_currency": "usd",
                "order": "market_cap_desc",  
                "per_page": per_page,
                "page": page,
                "sparkline": False,
                "price_change_percentage": "7d,30d",
            },
            headers=HEADERS,
            timeout=20,
        )
        
        if r.status_code == 429:
            if retries >= 3:
                log.error(f"Critical rate limit block. Page index matrix {page} abandoned.")
                return []
            wait_time = 60 * (2 ** retries)
            log.warning(f"Rate limit hit on page {page} (HTTP 429). Cooling down for {wait_time}s...")
            time.sleep(wait_time)
            return fetch_coin_page(page, per_page, retries + 1)
            
        r.raise_for_status()
        return r.json()
    except Exception as e:
        log.error(f"Page {page} market ingestion failed: {e}")
        return []


def fetch_coin_detail(coin_id: str, retries: int = 0) -> Optional[Dict[str, Any]]:
    """Fetch exchange tickers and social metadata with adaptive backup cooling periods."""
    try:
        time.sleep(6.0)  
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
            cool_down = 60 * (2 ** retries)
            log.warning(f"Rate limit hit on detail asset {coin_id} (HTTP 429). Cooling down for {cool_down}s...")
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
    if exchange_count == FILTERS["exact_exchange_count"]:
        return 100.0
    return 30.0


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


def classify_opportunity(scores: Dict[str, float], exchange_count: int) -> Dict[str, str]:
    if exchange_count == 3:
        return {
            "primary_service": "Market Maker & CEX Advisory",
            "angle": "Severe order book fragmentation. Listed on exactly 3 venues with vulnerable liquidity depth. Suggesting automated spread stabilization and structural venue expansion blueprint."
        }
    return {
        "primary_service": "Liquidity Architecture",
        "angle": "Optimize current secondary market order book structure to prevent aggressive asset bleed."
    }


# ─── FILTER & PIPELINE MANAGEMENT ───────────────────────────────────────────

def passes_filters(coin: Dict[str, Any]) -> bool:
    """Pre-filters assets on the market page layout before doing heavy API lookup scans."""
    rank = coin.get("market_cap_rank")
    vol = coin.get("total_volume") or 0
    chg7d = coin.get("price_change_percentage_7d_in_currency") or 0

    # 1. Enforce specific rank corridor bounds (500 - 2000)
    if not rank or not (FILTERS["min_rank"] <= rank <= FILTERS["max_rank"]):
        return False

    # 2. Match targeted volume footprint near $210K
    if not (FILTERS["min_volume_usd"] <= vol <= FILTERS["max_volume_usd"]):
        return False

    # 3. Detect short-term capitulation drops near -16.90%
    min_drop = FILTERS["target_price_change_7d"] - FILTERS["allowed_7d_variance"]
    max_drop = FILTERS["target_price_change_7d"] + FILTERS["allowed_7d_variance"]
    if not (min_drop <= chg7d <= max_drop):
        return False

    return True


def build_lead(coin: Dict[str, Any], detail: Optional[Dict[str, Any]], benchmark: Dict[str, float]) -> Optional[Dict[str, Any]]:
    if not detail:
        return None

    # Identify true independent active exchange listing venues
    exchange_count = 3
    if detail.get("tickers"):
        exchanges = set(t.get("market", {}).get("name", "") for t in detail["tickers"] if t.get("market"))
        exchange_count = len(exchanges) if exchanges else 3

    # CRITICAL DROP: Confirm exact 3 exchange limit parameter
    if exchange_count != FILTERS["exact_exchange_count"]:
        return None

    benchmark_30d = benchmark["benchmark_30d"]
    change_30d = coin.get("price_change_percentage_30d_in_currency") or 0
    change_7d  = coin.get("price_change_percentage_7d_in_currency") or 0
    volume_24h = coin.get("total_volume") or 0
    market_cap = coin.get("market_cap") or 0

    price_s    = score_price_distress(change_30d, benchmark_30d)
    volume_s   = score_volume_decay(volume_24h, market_cap)
    exchange_s = score_exchange_count(exchange_count)
    social_s   = score_social_activity(detail)
    treasury_s = score_treasury_risk(market_cap, volume_24h, change_30d)

    composite = compute_composite_score(price_s, volume_s, exchange_s, social_s, treasury_s)

    scores_dict = {
        "price_distress": price_s, "volume_decay": volume_s,
        "exchange_count": exchange_s, "social_activity": social_s, "treasury_risk": treasury_s
    }
    opportunity = classify_opportunity(scores_dict, exchange_count)

    distress_flags = [
        f"🎯 CUSTOM TARGET MATRIX MATCH",
        f"🚨 Venue Liquidity Lock: Listed on exactly {exchange_count} exchanges",
        f"📉 Momentum Capitulation: 7d Delta at {change_7d:.2f}% (Target: -16.90%)"
    ]

    community = detail.get("community_data", {}) or {}
    links_data = detail.get("links", {}) or {}
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
    """Formats outbound precision lead data into a scannable structured markdown alert."""
    score = lead["composite_score"]
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
🎯 *PRECISION SEARCH INTERCEPTED* — Priority Score {score:.0f}/100

*{escape_markdown(lead['name'])} (${escape_markdown(lead['symbol'])})*
CoinGecko Target Rank #{lead['rank']}

📈 *Identified Search Anomalies:*
{flags_str}

📊 *Capital Infrastructure Metrics:*
  Vol 24h:   ${lead['volume_24h']:,.0f}
  Mkt Cap:   ${lead['market_cap']:,.0f}
  7d Delta:  {lead['change_7d']:+.2f}%
  30d Delta: {lead['change_30d']:+.1f}%
  Venues:    {lead['exchange_count']} Listed Venues
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
    lines = [f"📋 *TARGET MATRIX MATCHES — {len(leads)} Project Targets Surfaced*\n"]
    for i, lead in enumerate(leads[:10], 1):
        lines.append(
            f"{i}. 🎯 *{escape_markdown(lead['name'])}* (${escape_markdown(lead['symbol'])}) — "
            f"Rank #{lead['rank']} | Vol: ${lead['volume_24h']:,.0f} | 7d: {lead['change_7d']:.2f}%"
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

def run_scan(start_page: int = 5, end_page: int = 20, send_individual_alerts: bool = True):
    log.info(f"=== Crypto BD Lead Scanner Engine Initiated (Pages: {start_page} to {end_page}) ===")

    benchmark = get_market_benchmark()
    seen_ids = load_seen_ids()
    candidate_pool = []
    new_leads = []

    # Shift entry threshold to check specified windows to strictly hit the 500-2000 rank sweet spot
    for page in range(start_page, end_page + 1):
        log.info(f"Scanning cap segments page {page}/{end_page}...")
        coins = fetch_coin_page(page)
        
        if not coins:
            break
            
        for coin in coins:
            if coin.get("id") and coin["id"] not in seen_ids and passes_filters(coin):
                candidate_pool.append(coin)

    log.info(f"Upfront profiling complete. Isolated {len(candidate_pool)} high-probability targets.")

    # Sort matching candidates so the ones closest to your exact volume parameters process first
    candidate_pool.sort(key=lambda x: abs((x.get("total_volume") or 0) - 210000))

    MAX_DEEP_SCANS = 10
    scanned_count = 0

    for coin in candidate_pool:
        if scanned_count >= MAX_DEEP_SCANS:
            log.info(f"Max safe scan threshold reached ({MAX_DEEP_SCANS}). Wrapping execution run parameters.")
            break
            
        try:
            detail = fetch_coin_detail(coin["id"])
            scanned_count += 1
            
            if not detail:
                continue

            lead = build_lead(coin, detail, benchmark)
            if not lead:
                continue

            log.info(f"🎯 TARGET ACQUIRED: {lead['name']} (Rank #{lead['rank']}) — Volume: ${lead['volume_24h']:,.0f}")
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
    # Backwards compatibility fallback for workflow configurations using '--pages'
    parser.add_argument("--pages", type=int, default=None)
    parser.add_argument("--start_page", type=int, default=5, help="CoinGecko page index corridor floor")
    parser.add_argument("--end_page", type=int, default=20, help="CoinGecko page index corridor ceiling")
    parser.add_argument("--digest", action="store_true", help="Toggle batch digest summary reporting layout")
    args = parser.parse_args()
    
    # Smart routing if your GitHub Actions workflow configuration passes the single '--pages' argument instead
    final_start = 5
    final_end = 20
    if args.pages is not None:
        # If GitHub UI passes '5', it means process 5 pages starting right from our rank corridor floor
        final_start = 5
        final_end = 5 + (args.pages - 1)

    run_scan(start_page=final_start, end_page=final_end, send_individual_alerts=not args.digest)
