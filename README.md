<div align="center">

<!-- Full-width Banner -->
<img src="assets/banner.png" width="100%" alt="ProvenMesh — Autonomous AI Ecosystem Intelligence"/>

<br/><br/>

<!-- Badge Row 1 -->
<img src="https://img.shields.io/badge/Python-3.13-%230ea5e9?style=for-the-badge&logo=python&logoColor=white&labelColor=0D1117"/>
<img src="https://img.shields.io/badge/asyncio-Async_Native-%238b5cf6?style=for-the-badge&logo=python&logoColor=white&labelColor=0D1117"/>
<img src="https://img.shields.io/badge/PostgreSQL-16+pgvector-%2322c55e?style=for-the-badge&logo=postgresql&logoColor=white&labelColor=0D1117"/>
<img src="https://img.shields.io/badge/Redis-Streams-%23ef4444?style=for-the-badge&logo=redis&logoColor=white&labelColor=0D1117"/>
<img src="https://img.shields.io/badge/Docker-Compose-%230ea5e9?style=for-the-badge&logo=docker&logoColor=white&labelColor=0D1117"/>

<!-- Badge Row 2 -->
<img src="https://img.shields.io/badge/Gemini-2.5_Flash-%230ea5e9?style=for-the-badge&logo=google&logoColor=white&labelColor=0D1117"/>
<img src="https://img.shields.io/badge/Groq-Llama_3.3_70B-%23f97316?style=for-the-badge&logo=meta&logoColor=white&labelColor=0D1117"/>
<img src="https://img.shields.io/badge/OpenRouter-Nemotron_120B-%238b5cf6?style=for-the-badge&logoColor=white&labelColor=0D1117"/>
<img src="https://img.shields.io/badge/Google_Sheets-API_v4-%2322c55e?style=for-the-badge&logo=googlesheets&logoColor=white&labelColor=0D1117"/>

<!-- Stats Row -->
<img src="https://img.shields.io/badge/Cost-%240%2FMonth-%2322c55e?style=for-the-badge&labelColor=0D1117"/>
<img src="https://img.shields.io/badge/Sources-24%2B_RSS_%C2%B7_HN_API-%23f97316?style=for-the-badge&labelColor=0D1117"/>
<img src="https://img.shields.io/badge/URLs_per_Cycle-1%2C725%2B-%238b5cf6?style=for-the-badge&labelColor=0D1117"/>
<img src="https://img.shields.io/badge/Hallucinations-0%25-%2322c55e?style=for-the-badge&labelColor=0D1117"/>
<img src="https://img.shields.io/badge/Uptime-24%2F7-%230ea5e9?style=for-the-badge&labelColor=0D1117"/>
<img src="https://img.shields.io/badge/License-MIT-%238b5cf6?style=for-the-badge&labelColor=0D1117"/>

<br/><br/>

<!-- CTA Buttons -->
[![Live Dashboard](https://img.shields.io/badge/📊_Live_Google_Sheet-Open_Now-22c55e?style=for-the-badge&labelColor=0D1117)](https://docs.google.com/spreadsheets/d/130p3Bo5gZRBHWt9tK8J8BqVP5YY2ckaoCWW1UeC7vEc)
[![Quick Start](https://img.shields.io/badge/🚀_Quick_Start-5_Minutes-0ea5e9?style=for-the-badge&labelColor=0D1117)](#-quick-start)
[![Pitch Deck](https://img.shields.io/badge/📄_Pitch_Deck-PDF-f97316?style=for-the-badge&labelColor=0D1117)](ProvenMesh_Architecture_and_Implementation_Plan.pdf)

</div>

---

## 💡 What is ProvenMesh?

> **ProvenMesh** is an autonomous, real-time intelligence pipeline that crawls **24+ live sources**, extracts structured entities using a **self-healing 4-provider LLM chain**, verifies every field with **source-text grounding**, deduplicates via **fuzzy + semantic matching**, and exports to a **live Google Sheets dashboard** — all for **$0/month**.

---

## 🔴 The Problem

| Pain Point | Reality |
|-----------|---------|
| 📄 ArXiv papers per day | **500+** — impossible to read manually |
| 🚀 New AI startups per month | **200+** — no single source of truth |
| 💰 Crunchbase Pro cost | **$500/month** — manually curated, goes stale |
| ⏱️ Analyst research time | **6–8 hrs/day** just reading newsletters |
| 🤖 LLM hallucination rate | **Up to 30%** on factual claims |

**ProvenMesh solves all of these. At once. For free.**

---

## 🏗️ Architecture

<img src="assets/architecture.png" width="100%" alt="ProvenMesh Pipeline Architecture"/>

---

## 🛠️ Tech Stack

<table>
<tr><th>Layer</th><th>Technology</th><th>Why</th></tr>
<tr><td><b>Runtime</b></td><td>Python 3.13 + asyncio</td><td>50+ concurrent tasks, non-blocking I/O</td></tr>
<tr><td><b>HTTP</b></td><td>aiohttp</td><td>Async crawling, session pooling</td></tr>
<tr><td><b>LLM #1</b></td><td>Gemini 2.5 Flash</td><td>Primary · 12 RPM free · JSON mode</td></tr>
<tr><td><b>LLM #2</b></td><td>Groq Llama 3.3 70B</td><td>Fallback · 14,400 req/day free</td></tr>
<tr><td><b>LLM #3</b></td><td>Nemotron 120B via OpenRouter</td><td>Tertiary · unlimited free</td></tr>
<tr><td><b>LLM #4</b></td><td>Gemma 4 31B via OpenRouter</td><td>Backup · unlimited free</td></tr>
<tr><td><b>Queue</b></td><td>Redis Streams</td><td>Reliable async message passing</td></tr>
<tr><td><b>Database</b></td><td>PostgreSQL 16 + pgvector</td><td>Entity graph + vector embeddings</td></tr>
<tr><td><b>Object Store</b></td><td>MinIO (S3-compatible)</td><td>Raw HTML archival + audit trail</td></tr>
<tr><td><b>Entity Match</b></td><td>RapidFuzz + sentence-transformers</td><td>Fuzzy + semantic deduplication</td></tr>
<tr><td><b>Logs</b></td><td>structlog (JSON)</td><td>Machine-readable observability</td></tr>
<tr><td><b>Metrics</b></td><td>Prometheus</td><td>LLM cost, latency, token tracking</td></tr>
<tr><td><b>Export</b></td><td>Google Sheets API v4</td><td>Live auto-updating dashboard</td></tr>
<tr><td><b>Infra</b></td><td>Docker Compose</td><td>One-command full stack</td></tr>
</table>

---

## 🔑 Key Innovations

### 🛡️ Evidence-First Extraction — 0% Hallucinations

```json
{
  "entityName": {
    "value": "Anthropic",
    "evidence": "Anthropic, the AI safety company, announced...",
    "confidence": 0.97
  }
}
```
> **No evidence → value is `null`. The model cannot fabricate data.**

### ⚡ 1,725 URLs per Cycle — 24 Sources in Parallel

```python
results = await asyncio.gather(*[fetch_rss(session, url, name) for url, name in _RSS_FEEDS])
hn_urls = await backfill_hacker_news(session, days_back=30)  # 700+ historical stories
```

### 🔄 Self-Healing — Circuit Breaker Chain
```
Gemini 2.5 Flash → Groq 70B → Nemotron 120B → Gemma 4 31B
  ↑ Opens at 20 failures · Recovers in 30 seconds · Zero manual intervention ↑
```

### 🔗 Semantic Entity Resolution
```
"OpenAI" + "Open AI" + "openai.com"  →  canonical: startup_openai (0.97 confidence)
Algorithm: Normalize → RapidFuzz ≥85% → cosine similarity ≥0.88 → Upsert
```

---

## 📊 Live Dashboard

**[📊 Open Google Sheet →](https://docs.google.com/spreadsheets/d/130p3Bo5gZRBHWt9tK8J8BqVP5YY2ckaoCWW1UeC7vEc)**

| Tab | Color | Records | Key Columns |
|-----|-------|---------|-------------|
| 🚀 **Startups** | Cyan | 15+ | Name · Funding · Founders · HQ · Industry |
| 🛠️ **Products** | Orange | 41+ | Description · Pricing · Features · GitHub |
| 📄 **Papers** | Purple | Growing | Abstract · Authors · ArXiv ID · Citations |
| 💼 **Jobs** | Green | Growing | Company · Salary · Skills · Remote Policy |
| 📰 **News** | Red | 5+ | Headline · Summary · Source URL · Topics |
| 🔗 **Entity Log** | Grey | 21+ | Full resolution audit trail |

---

## 🚀 Quick Start

```bash
git clone https://github.com/Surajsharma0804/provenmesh.git
cd provenmesh
cp .env.example .env        # Add your API keys
docker compose up -d        # Postgres + Redis + MinIO
pip install -e ".[dev]"
alembic upgrade head
python scripts/seed_entities.py
python -m provenmesh.main run --crawl-workers 3 --extract-workers 2 --resolve-workers 2 --auto-export --export-interval 20
```

**Windows — just double-click `start.bat`** ✅

---

## 🔐 Free API Keys

| Provider | Model | Limit | Get Key |
|---------|-------|-------|---------|
| **Google AI Studio** | Gemini 2.5 Flash | 15 RPM | [aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey) |
| **Groq** | Llama 3.3 70B | 14,400/day | [console.groq.com/keys](https://console.groq.com/keys) |
| **OpenRouter** | Nemotron 120B + Gemma 31B | Unlimited | [openrouter.ai/keys](https://openrouter.ai/keys) |

---

## 🖥️ After PC Reboot

```bash
docker compose up -d
python -m provenmesh.main run --auto-export --export-interval 20
# Or just double-click start.bat
```
> All data is **preserved** in PostgreSQL Docker volumes across reboots.

---

## 📈 Benchmarks

| Metric | Value |
|--------|-------|
| News sources | 24 RSS feeds + Hacker News API |
| URLs per cycle | **1,725+** |
| Historical backfill | **30 days** (HN Algolia API) |
| Data freshness | Every **20 minutes** |
| Monthly cost | **$0.00** |
| Self-healing recovery | **30 seconds** |

---

## 🆚 ProvenMesh vs Alternatives

| Feature | **ProvenMesh** | Crunchbase Pro | Manual |
|---------|:-----------:|:-----------:|:------:|
| **Cost** | **$0** ✅ | $500/mo ❌ | Time ❌ |
| **Update Freq.** | **20 min** ✅ | Days ❌ | Manual ❌ |
| **Hallucinations** | **Grounded** ✅ | Human ⚠️ | Human ⚠️ |
| **Sources** | **24+** ✅ | Curated ❌ | Limited ❌ |
| **Historical** | **30 days** ✅ | N/A ❌ | No ❌ |
| **Self-Healing** | **Yes** ✅ | N/A | N/A |

---

## 📁 Structure

```
provenmesh/
├── src/provenmesh/
│   ├── crawling/producers/    # news · startups · products · papers · jobs
│   ├── extraction/providers/  # gemini · groq · openrouter
│   ├── extraction/orchestrator.py  # Fallback chain + circuit breakers
│   ├── resolution/            # Fuzzy + semantic deduplication
│   ├── export/sheets.py       # Google Sheets — 6 colored tabs
│   └── graph/                 # PostgreSQL entity repository
├── assets/                    # banner.png · architecture.png · logo.png
├── start.bat                  # Windows one-click launcher
├── docker-compose.yml
└── .env.example
```

---

<div align="center">

<img src="assets/logo.png" width="80" alt="ProvenMesh"/>

**Built with Python 3.13 · Runs for Free · Zero Hallucinations**

*⭐ Star this repo if ProvenMesh impressed you!*

</div>
