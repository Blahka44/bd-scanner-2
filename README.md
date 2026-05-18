# Crypto BD Lead Intelligence Scanner
### Built for @justinbizdev | CEX Listing · MM Advisory · Treasury Management

---

## What This Is

A fully automated, GitHub Actions-powered lead generation system that
continuously scans crypto markets for distressed projects most likely to
need your services — and delivers qualified, scored leads directly to
your Telegram, before your competitors even notice them.

---

## System Architecture

```
┌─────────────────────────────────────────────────────────┐
│                   GITHUB ACTIONS (CRON)                 │
│  06:00 UTC daily · 14:00 UTC daily · Sunday deep scan   │
└──────────────────────────┬──────────────────────────────┘
                           │
            ┌──────────────▼──────────────┐
            │      DATA INGESTION LAYER   │
            │  CoinGecko /markets (page 1-N)│
            │  CoinGecko /coins/{id}       │
            │  (tickers, community_data)   │
            └──────────────┬──────────────┘
                           │
            ┌──────────────▼──────────────┐
            │     MARKET CONTEXT LAYER    │
            │  BTC + ETH 30d performance  │
            │  → compute benchmark_30d    │
            │  → detect "market up, coin  │
            │    down" divergence          │
            └──────────────┬──────────────┘
                           │
            ┌──────────────▼──────────────┐
            │       FILTER ENGINE         │
            │  Volume: $10K – $2M         │
            │  Market Cap: $500K – $50M   │
            │  30d change: < -15%         │
            │  Exchange count: ≤ 8        │
            └──────────────┬──────────────┘
                           │
            ┌──────────────▼──────────────┐
            │       SCORING ENGINE        │
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
            │  · MM Advisory              │
            │  · CEX Listing Strategy     │
            │  · Treasury Management      │
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
            │  Individual: score ≥ 45     │
            │  Daily digest at scan end   │
            │  Weekly summary (Sundays)   │
            └──────────────┬──────────────┘
                           │
            ┌──────────────▼──────────────┐
            │      LEAD ARCHIVE           │
            │  data/leads_YYYYMMDD.json   │
            │  GitHub Actions Artifacts   │
            │  30-day retention           │
            └─────────────────────────────┘
```

---

## Repo Structure

```
crypto-bd-scanner/
│
├── .github/
│   └── workflows/
│       └── scanner.yml          ← Cron + manual trigger
│
├── scanner/
│   ├── main.py                  ← Core engine (scan + score + alert)
│   ├── scoring.py               ← (optional: extract scoring logic here)
│   └── telegram.py              ← (optional: extract Telegram logic here)
│
├── data/
│   ├── seen_leads.json          ← Deduplication cache (gitignored)
│   └── leads_*.json             ← Daily lead archives (gitignored)
│
├── .gitignore
├── requirements.txt
└── README.md
```

---

## Setup (48-Hour Deploy)

### Step 1: Create the Telegram Bot (10 min)

1. Open Telegram → search **@BotFather**
2. Send `/newbot` → follow prompts → copy the **bot token**
3. Start a chat with your new bot (send it any message)
4. Get your chat ID:
   ```
   https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates
   ```
   Look for `"chat":{"id": YOUR_CHAT_ID}`

### Step 2: GitHub Secrets (5 min)

In your GitHub repo → Settings → Secrets → Actions → New secret:

| Secret Name          | Value                        |
|----------------------|------------------------------|
| `TELEGRAM_BOT_TOKEN` | Your bot token from BotFather|
| `TELEGRAM_CHAT_ID`   | Your Telegram chat/group ID  |
| `COINGECKO_API_KEY`  | Optional (free tier works)   |

### Step 3: Push & Enable Actions (5 min)

```bash
git init
git add .
git commit -m "feat: initial BD scanner deploy"
git remote add origin https://github.com/YOUR_USERNAME/crypto-bd-scanner
git push -u origin main
```

Go to Actions tab → Enable workflows → Done.

### Step 4: Test Immediately

Actions tab → "Crypto BD Lead Scanner" → "Run workflow" → Run.
Within 3-5 minutes, leads will appear in your Telegram.

---

## Scoring Framework

| Dimension      | Weight | What It Measures |
|----------------|--------|-----------------|
| Price Distress | 30%    | Relative decline vs BTC/ETH benchmark |
| Volume Decay   | 25%    | V/MC ratio — proxy for order book health |
| Exchange Count | 15%    | Listing gap = advisory opportunity |
| Social Active  | 15%    | Twitter + Telegram presence (will they respond?) |
| Treasury Risk  | 15%    | MC decline vs volume = runway pressure |

**Score interpretation:**
- 75–100: 🔴 URGENT — reach out today
- 60–74:  🟠 HOT — reach out this week
- 45–59:  🟡 WARM — monitor and reach out

---

## Alert Format

```
🔴 NEW BD LEAD — Confidence 82/100

BitYuan ($BTY)
Rank #1174 on CoinGecko

📉 Distress Signals:
  ⚠️ DOWN 42% while market UP 8%
  ⚠️ CRITICAL volume ($210K/day)
  ⚠️ ONLY 3 exchange(s)
  ⚠️ TREASURY risk detected

📊 Metrics:
  Vol 24h:    $210,000
  Mkt Cap:    $3,200,000
  7d Change:  -16.9%
  30d Change: -42.0%
  Exchanges:  3
  Market 30d: +8.0% (benchmark)

🎯 Primary Opportunity: Market Maker Advisory
💬 Outreach Angle:
Visible liquidity decay — order book likely thin or manipulated. MM audit would expose structural issues.

📡 Score Breakdown:
  Price Distress:  91/100
  Volume Decay:    78/100
  Exchange Gap:    80/100
  Social Active:   60/100
  Treasury Risk:   70/100

🔗 Contact Points:
X: @bityuan | t.me/bityuan | bityuan.com
```

---

## Rate Limiting Strategy

- CoinGecko free tier: 30 calls/min
- Scanner sleeps 1.2s between detail calls
- Pages fetched with 2s buffer
- At 5 pages × 100 coins = 500 coins reviewed
- Detail calls only for filter-passing coins (~20-50)
- Total runtime: ~10-15 minutes per scan

**To avoid hitting limits:**
- Use CoinGecko Demo API key (free) for 30→50 calls/min
- Use Pro key for unlimited (not needed for this volume)

---

## Evolving Into a Proprietary Intelligence System

### Phase 1 (Now): MVP Scanner
- CoinGecko markets + detail
- Score + alert to Telegram
- GitHub Actions cron

### Phase 2 (+30 days): Signal Enrichment
- Add LBank/Hotcoin volume as secondary verification
- Cross-reference MEXC listing data (detect listing candidates)
- Twitter/X social scraping via nitter or Apify

### Phase 3 (+60 days): Outreach Automation
- Auto-extract founder Twitter from CoinGecko links
- Draft personalized first-line outreach using score profile
- Track lead status in Notion/Airtable via API

### Phase 4 (+90 days): Proprietary Dataset
- 90 days of daily scans = pattern library
- Identify which distress profiles → which service need → which responded
- Build historical "distress-to-close" model
- This data is YOUR moat. No competitor can buy it.

---

## Hidden Distress Pattern Detection

Beyond the obvious (price down, volume low), the scanner detects:

1. **Divergence plays**: Coin DOWN when BTC/ETH UP = structural issue, not market
2. **Velocity acceleration**: 30d bad + 7d worse = problem deepening
3. **Liquidity Mirage**: High MC, very low volume = paper value, real illiquidity
4. **Exchange desert**: 1-2 exchanges + low volume = near-death spiral risk
5. **Treasury burn cliff**: MC declining + volume under $100K = runway months away

---

## .gitignore

```
data/
.env
__pycache__/
*.pyc
.DS_Store
```

---

*Built for @justinbizdev — asymmetric BD intelligence for independent crypto advisors.*
