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
    """
    Score 0–100. Higher = more distressed relative to market.
    Coin down 40% when market is up 10% = maximum signal.
    """
    relative_pain = (benchmark_30d - change_30d)   # positive = underperforming
    if relative_pain <= 0:
        return 0.0
    # 50pp relative underperformance = perfect score
    return min(100.0, (relative_pain / 50.0) * 100)


def score_volume_decay(volume_24h: float, market_cap: float) -> float:
    """
    Score 0–100. Low volume relative to market cap = liquidity decay.
    V/MC ratio < 0.5% is concerning; < 0.1% is crisis-level.
    """
    if market_cap <= 0:
        return 0.0
    ratio = (volume_24h / market_cap) * 100
    if ratio >= 5.0:
        return 0.0
    if ratio <= 0.05:
        return 100.0
    # Logarithmic decay scoring
    return min(100.0, (1 - math.log(ratio / 0.05) / math.log(100)) * 100)


def score_exchange_count(exchange_count: int) -> float:
    """Score 0–100. Fewer exchanges = higher advisory need."""
    if exchange_count >= 10:
        return 0.0
    if exchange_count <= 1:
        return 100.0
    return ((10 - exchange_count) / 9.0) * 100


def score_social_activity(coin_detail: Optional[dict]) -> float:
    """
    Proxy: community data signals the team still cares / will respond.
    Twitter followers, Telegram members used as proxies.
    """
    if not coin_detail:
        return 50.0  # neutral when data missing
    community = coin_detail.get("community_data", {}) or {}
    twitter = community.get("twitter_followers") or 0
    telegram = community.get("telegram_channel_user_count") or 0

    # Goldilocks zone: active but not massive (1K–100K Twitter)
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
    """
    Projects bleeding market cap with low volume face runway pressure.
    This maps to treasury management urgency.
    """
    score = 0.0
    # MC under $5M with volume under $100K = treasury alarm
    if market_cap < 5_000_000 and volume_24h < 100_000:
        score += 60.0
    elif market_cap < 10_000_000 and volume_24h < 500_000:
        score += 30.0
    # Severe 30d decline accelerates treasury burn
    if change_30d < -40:
        score += 40.0
    elif change_30d < -25:
        score += 20.0
    return min(100.0, score)


def compute_composite_score(
    price_score: float,
    volume_score: float,
    exchange_score: float,
    social_score: float,
    treasury_score: float,
) -> float:
    return (
        price_score    * WEIGHTS["price_distress"] +
        volume_score   * WEIGHTS["volume_decay"] +
        exchange_score * WEIGHTS["exchange_count"] +
        social_score   * WEIGHTS["social_activity"] +
        treasury_score * WEIGHTS["treasury_risk"]
    )


def classify_opportunity(scores: dict, coin: dict) -> dict:
    """Map score profile to primary service opportunity."""
    primary_service = "CEX Listing Strategy"
    angle = "Expand exchange presence to recover liquidity and price discovery"

    volume_s = scores["volume_decay"]
    price_s  = scores["price_distress"]
    treasury_s = scores["treasury_risk"]
    exchange_s = scores["exchange_count"]

    if volume_s > 70 and price_s > 60:
        primary_service = "Market Maker Advisory"
        angle = "Visible liquidity decay — order book likely thin or manipulated. MM audit would expose structural issues."
    elif treasury_s > 60:
        primary_service = "Treasury Management"
        angle = "Market cap declining fast with low volume suggests runway pressure. Treasury strategy is urgent."
    elif exchange_s > 70:
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

    # Exchange count from tickers
    exchange_count = 3  # default fallback
    if detail and detail.get("tickers"):
        exchanges = set(t.get("market", {}).get("name", "") for t in detail["tickers"])
        exchange_count = len(exchanges)

    # Score each dimension
    price_s    = score_price_distress(change_30d, benchmark_30d)
    volume_s   = score_volume_decay(volume_24h, market_cap)
    exchange_s = score_exchange_count(exchange_count)
    social_s   = score_social_activity(detail)
    treasury_s = score_treasury_risk(market_cap, volume_24h, change_30d)

    composite = compute_composite_score(price_s, volume_s, exchange_s, social_s, treasury_s)

    # Only surface high-signal leads
    if composite < 45:
        return None

    opportunity = classify_opportunity(
        {"volume_decay": volume_s, "price_distress": price_s,
         "treasury_risk": treasury_s, "exchange_count": exchange_s},
        coin
    )

    # Detect hidden distress patterns
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
    twitter_url = (detail or {}).get("links", {}).get("twitter_screen_name", "")
    telegram_handle = (detail or {}).get("links", {}).get("telegram_channel_identifier", "")
    website = ((detail or {}).get("links
