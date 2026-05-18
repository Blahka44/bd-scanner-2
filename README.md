# Crypto BD Lead Intelligence Scanner
### Built for Independent BD Advisors | CEX Listing · MM Advisory · Liquidity Architecture

---

## What This Is

A fully automated, GitHub Actions-powered lead generation system that continuously scans crypto secondary markets for structurally distressed projects most likely to need strategic advisory—and delivers qualified, scored leads directly to your Telegram before your competitors even notice them.

---

## System Architecture

┌─────────────────────────────────────────────────────────┐
│                    GITHUB ACTIONS (CRON)                │
│   06:00 UTC daily · 14:00 UTC daily · Sunday deep scan  │
└──────────────────────────┬──────────────────────────────┘
│
┌──────────────▼──────────────┐
│      DATA INGESTION LAYER   │
│  CoinGecko /markets (Page 5+)│
│  CoinGecko /coins/{id}      │
│  (tickers, community_data)  │
└──────────────┬──────────────┘
│
┌──────────────▼──────────────┐
│     MARKET CONTEXT LAYER    │
│  BTC + ETH 30d performance  │
│  → compute benchmark_30d    │
│  → detect "market up, coin  │
│    down" divergence         │
└──────────────┬──────────────┘
│
┌──────────────▼──────────────┐
│        FILTER ENGINE        │
│  Rank Target: 500 – 2000    │
│  Volume Matrix: ~$210K      │
│  7d Change Target: -16.90%  │
│  Exchange Limit: Exactly 3  │
└──────────────┬──────────────┘
│
┌──────────────▼──────────────┐
│        SCORING ENGINE       │
│  Price Distress   (30%)     │
│  Volume Decay     (25%)     │
│  Exchange Count   (15%)     │
│  Social Activity  (15%)     │
│  Treasury Risk    (15%)     │
│  → Composite 0-100          │
└──────────────┬──────────────┘
│
┌──────────────▼──────────────┐
│    OPPORTUNITY CLASSIFIER   │
│  Score profile → service:   │
│  · MM & CEX Advisory        │
│  · Liquidity Architecture   │
│  + Outreach angle generated │
└──────────────┬──────────────┘
│
┌──────────────▼──────────────┐
│     DEDUPLICATION LAYER     │
│  seen_leads.json cache      │
│  Never alert same lead 2x   │
└──────────────┬──────────────┘
│
┌──────────────▼──────────────┐
│       TELEGRAM ALERTS       │
│  Live Mode: Real-time Ping  │
│  Digest Mode: Batch Summary │
└──────────────┬──────────────┘
│
┌──────────────▼──────────────┐
│         LEAD ARCHIVE        │
│  data/leads_YYYYMMDD.json   │
│  GitHub Actions Artifacts   │
└─────────────────────────────┘


---

## Repo Structure

crypto-bd-scanner/
│
├── .github/
│   └── workflows/
│       ├── scanner.yml          ← Cron + Manual UI Input Core
│       └── keepalive.yml        ← Automatic Anti-Dormancy Engine
│
├── scanner/
│   └── main.py                  ← Monolithic Production Processing Unit
│
├── data/
│   ├── seen_leads.json          ← Deduplication Registry (Cached via GHA)
│   └── leads_*.json             ← Runtime Session Output Logs (Gitignored)
│
├── .gitignore
├── requirements.txt
└── README.md


---

## Setup & Production Deployment

### Step 1: Create the Telegram Bot (10 min)

1. Open Telegram and search for **@BotFather**.
2. Send `/newbot` → complete the naming steps → copy your secure **Bot Token**.
3. Initialize the chat matrix by opening a message stream with your newly generated bot.
4. Extract your explicit User/Group Chat ID via the updates tunnel:
https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates

Locate the structural JSON segment: `"chat":{"id": YOUR_CHAT_ID}`.

### Step 2: Configure GitHub Actions Secrets (5 min)

Navigate to your GitHub Repository → **Settings** → **Secrets and variables** → **Actions** → Create the following parameters:

| Secret Name          | Required Value Matrix                        |
|----------------------|----------------------------------------------|
| `TELEGRAM_BOT_TOKEN` | Secret alphanumeric token from BotFather     |
| `TELEGRAM_CHAT_ID`   | Destination Telegram channel/group/user ID   |
| `COINGECKO_API_KEY`  | Recommended (Demo/Pro key prevents 429 drops)|

### Step 3: Run the Engine Manually

1. Click on the **Actions** tab inside your repository.
2. Select **Crypto BD Lead Scanner** from the left sidebar.
3. Click the **Run workflow** dropdown menu.
4. Set your parameters via the UI panel:
* **CoinGecko pages to scan:** Choose depth (Default: 5 pages, processing starting at page 5 to target rank 500+ directly).
* **Mode:** Select `live` for instant Telegram pings or `digest` for a clean, aggregated matrix breakdown text.

---

## High-Precision Scoring Framework

The scoring matrix breaks down data points to isolate structural vulnerabilities within a token's order book:

| Dimension | Weight | What It Measures |
|-----------|--------|------------------|
| **Price Distress** | 30% | Deep divergence or market capitulation vs general BTC/ETH 30d baselines. |
| **Volume Decay** | 25% | Sudden drops in the $V/MC$ ratio, revealing severe order book illiquidity. |
| **Exchange Count** | 15% | Identifies liquidity locked on exactly 3 venues—leaving them vulnerable to sudden spread gaps. |
| **Social Activity** | 15% | Community activity check to ensure the project isn't completely abandoned. |
| **Treasury Risk** | 15% | Accelerated price decline combined with an illiquidity cliff, indicating runaway pressure. |

* **75–100: 🔴 URGENT MATRIX MATCH** — Immediate Outreach Opportunity. Structural leaks verified.
* **60–74:  🟠 HOT ANOMALY** — Clear order book friction points. Action within the weekly pipeline.
* **45–59:  🟡 WARM TARGET** — Fragile liquidity. Monitor and sequence.

---

## Production Alert Template

🎯 PRECISION SEARCH INTERCEPTED — Priority Score 82/100

BitYuan ($BTY)
CoinGecko Target Rank #1174

📈 Identified Search Anomalies:
⚠️ CUSTOM TARGET MATRIX MATCH
⚠️ Venue Liquidity Lock: Listed on exactly 3 exchanges
⚠️ Momentum Capitulation: 7d Delta at -16.90% (Target: -16.90%)

📊 Capital Infrastructure Metrics:
Vol 24h:   $210,000
Mkt Cap:   $3,200,000
7d Delta:  -16.90%
30d Delta: -42.0%
Venues:    3 Listed Venues
Baseline:  +8.0% (Global Benchmark)

🎯 Target Framework Match: Market Maker & CEX Advisory
💬 Recommended Outreach Stance:
Severe order book fragmentation. Listed on exactly 3 venues with vulnerable liquidity depth. Suggesting automated spread stabilization and structural venue expansion blueprint.

📡 Multi-Dimensional Scoring Core:

  Price Distress:  91/100
  Volume Decay:    78/100
  Exchange Gap:    100/100
  Social Active:   60/100
  Treasury Risk:   70/100
🔗 Surfaced Outreach Anchors:
X: @bityuan | TG: t.me/bityuan | Web: bityuan.com

🕐 2026-05-18 12:15 UTC


---

## Defensive API Rate Limiting Architecture

To reliably process high-density market loops without exhausting API tokens, the script runs an adaptive pacing mechanism:
* **Pre-Filtering Optimization:** Performs upfront checks on lightweight market data parameters before running resource-intensive API detail queries.
* **Corridor Scanning:** Bypasses pages 1–4 entirely (the top 500 tokens) to avoid wasting rate limits on over-brokered assets.
* **Adaptive Backoff Buffering:** Implements a strict 6.0-second delay between deep token metadata calls, accompanied by automated multi-stage exponential cool-downs if a `429 Too Many Requests` status code is encountered.

---

## Strategic System Evolution Roadmap

* **Phase 1 (Active): MVP Precision Scanner** — Monolithic filter engine, stateful deduplication cache via GitHub cache, targeted UI configuration options, and Telegram delivery routing.
* **Phase 2 (+30 Days): Signal Enrichment** — Integration of exchange-side order book depth validation (LBank/Hotcoin metrics) and tracking of exchange listing applications.
* **Phase 3 (+60 Days): Automated Context Building** — Programmatic extraction of key team handles from public repository metadata and automated drafting of tailored outreach angles mapped to specific scoring data.
* **Phase 4 (+90 Days): Proprietary Asymmetric Moat** — Building an internal database of distress timelines to model which liquidity indicators show the highest conversion rate for advisory services.

---

## Advanced Distress Patterns Tracked

1. **Market Divergence Plays:** Tracking assets moving downward while the global benchmark ($BTC$ & $ETH$) shows positive trends. This highlights severe structural or internal liquidity management issues.
2. **Velocity Multipliers:** Isolating tokens where the short-term 7-day capitulation trend matches or accelerates past the 30-day downside trend, indicating active panic or token dumping.
3. **Liquidity Fragmentation:** Monitoring projects listed on exactly 3 venues, where shallow order books lead to rapid asset bleeding and wide bid-ask spreads.

---

## .gitignore

data/
.env
pycache/
*.pyc
.DS_Store
.idea/
.vscode/


---
*Built for Independent BD Advisors — Asymmetric business intelligence infrastructure.*
