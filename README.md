<div align="center">

<img src="https://img.shields.io/badge/Python-3.13-3776AB?style=for-the-badge&logo=python&logoColor=white"/>
<img src="https://img.shields.io/badge/Gemini_2.5_Flash-4285F4?style=for-the-badge&logo=google&logoColor=white"/>
<img src="https://img.shields.io/badge/PostgreSQL-316192?style=for-the-badge&logo=postgresql&logoColor=white"/>
<img src="https://img.shields.io/badge/Redis-DC382D?style=for-the-badge&logo=redis&logoColor=white"/>
<img src="https://img.shields.io/badge/Docker-2496ED?style=for-the-badge&logo=docker&logoColor=white"/>
<img src="https://img.shields.io/badge/License-MIT-green?style=for-the-badge"/>

# 🧠 ProvenMesh

### *The Bloomberg Terminal for the AI Ecosystem*

**An autonomous, real-time intelligence pipeline that crawls, extracts, verifies, and maps the entire AI industry — startups, research papers, products, jobs, and news — into a live Google Sheets dashboard. Runs 24/7. Costs $0.**

[📊 Live Dashboard](https://docs.google.com/spreadsheets/d/130p3Bo5gZRBHWt9tK8J8BqVP5YY2ckaoCWW1UeC7vEc) · [🚀 Quick Start](#-quick-start) · [🏗️ Architecture](#%EF%B8%8F-architecture) · [📄 Pitch Deck](ProvenMesh_Architecture_and_Implementation_Plan.pdf)

</div>

---

## 🔴 The Problem

The AI industry produces **500+ papers, 200+ startup announcements, and thousands of job postings every single day.** No human can track it all. Existing tools like Crunchbase cost $500/month, are manually curated, and go stale within days.

**ProvenMesh solves this with a fully autonomous intelligence pipeline.**

---

## ✅ What It Does

```
ArXiv · TechCrunch · LinkedIn · GitHub · YC
          │
          ▼  crawl (async, rate-limited)
    Raw HTML → MinIO Object Store
          │
          ▼  extract (LLM with evidence grounding)
    Gemini 2.5 Flash → Groq → OpenRouter → fallback
          │
          ▼  verify (anti-hallucination)
    Every field requires a direct source quote
          │
          ▼  resolve (entity deduplication)
    "OpenAI" + "Open AI" + "openai.com" → ONE entity
          │
          ▼  export (auto every 20 min)
    📊 Google Sheets — 6 live tabs, always fresh
```

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     PROVENMESH PIPELINE                         │
│                                                                 │
│  Sources          Workers              Storage        Output    │
│  ────────         ──────────           ───────        ──────    │
│  ArXiv API   →   Crawler (3x)  →   MinIO (S3)         │        │
│  TechCrunch  →   Extractor(2x) →   PostgreSQL  →  Google       │
│  LinkedIn    →   Resolver (2x) →   Redis Queue     Sheets      │
│  GitHub      →                                    (6 tabs)     │
│  YC/PH       →   LLM Fallback Chain:                           │
│                  1. Gemini 2.5 Flash (12 RPM, free)            │
│                  2. Groq Llama 3.3 70B (14K req/day)           │
│                  3. Nemotron 120B via OpenRouter (free)         │
│                  4. Gemma 4 31B via OpenRouter (backup)         │
└─────────────────────────────────────────────────────────────────┘
```

---

## 🛠️ Tech Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **Language** | Python 3.13 + asyncio | Async-native, 50+ concurrent crawls |
| **LLM Primary** | Gemini 2.5 Flash | Evidence-first extraction, JSON mode |
| **LLM Fallback** | Groq · OpenRouter · DeepSeek | Zero-downtime provider switching |
| **Queue** | Redis Streams | Reliable async message passing |
| **Database** | PostgreSQL + asyncpg | Entity graph with vector embeddings |
| **Object Store** | MinIO (S3-compatible) | Raw HTML archival, full audit trail |
| **Entity Match** | RapidFuzz + sentence-transformers | Fuzzy + semantic deduplication |
| **Containers** | Docker Compose | One-command full stack |
| **Export** | Google Sheets API v4 | Live auto-updating dashboard |
| **Observability** | Structlog + Prometheus | JSON logs + metrics |
| **Reliability** | Circuit Breaker + Rate Limiter | Self-healing, never crashes |

---

## 🔑 Key Innovations

### 1. Evidence-First Extraction (Zero Hallucinations)
Every LLM-extracted field requires a direct quote from the source:
```json
{
  "entityName": {
    "value": "Anthropic",
    "evidence": "Anthropic, the AI safety company founded in 2021...",
    "confidence": 0.97
  }
}
```
No evidence → field is null. The model cannot make up data.

### 2. Self-Throttling Rate Limiter
Custom sliding-window rate limiter in pure asyncio — automatically waits when approaching API quotas instead of crashing. No external libraries.

### 3. 4-Provider Fallback Chain with Circuit Breakers
When any provider fails 5 times → circuit breaker opens → next provider activates automatically. Recovers in 30 seconds. Zero manual intervention.

### 4. Autonomous Entity Resolution
```
"OpenAI"  ┐
"Open AI" ├─→ canonical: startup_openai (OpenAI)
"openai.com" ┘
```
Uses fuzzy matching (RapidFuzz) + semantic embeddings (sentence-transformers) + rule-based dedup.

---

## 📊 Live Dashboard

**[📊 Open Google Sheet](https://docs.google.com/spreadsheets/d/130p3Bo5gZRBHWt9tK8J8BqVP5YY2ckaoCWW1UeC7vEc)**

| Tab | What's Inside | Auto-Updates |
|-----|--------------|-------------|
| **Startups** | AI companies — name, funding, founders, HQ | ✅ Every 20 min |
| **Products** | AI tools — pricing, features, GitHub URL | ✅ Every 20 min |
| **Papers** | ArXiv research — abstract, authors, citations | ✅ Every 20 min |
| **Jobs** | AI job listings — salary, skills, remote policy | ✅ Every 20 min |
| **News** | AI news — summary, entities, topics | ✅ Every 20 min |
| **Entity Mapping Log** | Full audit trail of every resolution | ✅ Every 20 min |

---

## 🚀 Quick Start

### Prerequisites
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (includes Docker Compose)
- Python 3.11+
- Free API keys (see [Getting API Keys](#-getting-api-keys))

### 1. Clone & Configure
```bash
git clone https://github.com/YOUR_USERNAME/provenmesh.git
cd provenmesh

# Copy the environment template
cp .env.example .env
# Edit .env and add your API keys
```

### 2. Start Infrastructure
```bash
docker compose up -d
```
This starts: **PostgreSQL** · **Redis** · **MinIO**

### 3. Install Dependencies
```bash
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

### 4. Run Database Migrations
```bash
alembic upgrade head
```

### 5. Seed Initial Entities
```bash
python scripts/seed_entities.py
```

### 6. Launch the Pipeline 🚀
```bash
python -m provenmesh.main run \
  --crawl-workers 3 \
  --extract-workers 2 \
  --resolve-workers 2 \
  --auto-export \
  --export-interval 20
```

**That's it. Your Google Sheet updates automatically every 20 minutes.**

---

## 🔑 Getting API Keys

All providers have **free tiers** — no credit card required:

| Provider | Free Tier | Get Key |
|----------|-----------|---------|
| **Gemini** | 15 req/min, Gemini 2.5 Flash | [aistudio.google.com](https://aistudio.google.com/app/apikey) |
| **Groq** | 14,400 req/day, Llama 3.3 70B | [console.groq.com](https://console.groq.com/keys) |
| **OpenRouter** | Nemotron 120B, Gemma 4 31B | [openrouter.ai](https://openrouter.ai/keys) |

---

## 🚂 Deploy to Railway (Run 24/7 in Cloud)

[![Deploy on Railway](https://railway.app/button.svg)](https://railway.app/new/template)

```bash
# Install Railway CLI
npm install -g @railway/cli

# Login and deploy
railway login
railway init
railway up
```

Set environment variables in Railway dashboard from your `.env` file.

---

## 📁 Project Structure

```
provenmesh/
├── src/provenmesh/
│   ├── crawling/           # Async HTTP + 5 source producers
│   ├── extraction/
│   │   ├── providers/      # gemini.py · groq.py · openrouter.py
│   │   ├── orchestrator.py # Fallback chain + circuit breakers + rate limiter
│   │   ├── prompts.py      # Evidence-first prompt templates
│   │   └── parser.py       # Robust JSON parsing (handles malformed LLM output)
│   ├── grounding/          # Hallucination prevention + schema validation
│   ├── resolution/         # Entity deduplication + fuzzy + semantic matching
│   ├── export/
│   │   └── sheets.py       # Google Sheets API — 6-tab auto-export
│   ├── workers/            # Async queue workers (crawl/extract/resolve)
│   ├── graph/              # PostgreSQL entity repository
│   └── observability/      # Structured logging + Prometheus metrics
├── schemas/                # JSON Schema for all 5 record types
├── scripts/                # Seed data utilities
├── tests/                  # Unit + integration tests
├── docker-compose.yml      # Full stack: Postgres + Redis + MinIO
├── Dockerfile              # Production container
├── .env.example            # Configuration template with docs
└── README.md               # You are here
```

---

## 🖥️ CLI Reference

```bash
# Run full pipeline
python -m provenmesh.main run --crawl-workers 3 --extract-workers 2 --resolve-workers 2

# Run with auto Google Sheets export every 20 minutes
python -m provenmesh.main run --auto-export --export-interval 20

# Manual export to Google Sheets (anytime)
python -m provenmesh.main export

# Check pipeline status
python -m provenmesh.main status

# Seed initial AI entities
python scripts/seed_entities.py
```

---

## 🔄 Running Again After Restart

When you restart your laptop:

```bash
# 1. Start infrastructure (takes ~10 seconds)
docker compose up -d

# 2. Run the pipeline
.venv\Scripts\python.exe -m provenmesh.main run ^
  --crawl-workers 3 --extract-workers 2 --resolve-workers 2 ^
  --auto-export --export-interval 20
```

All your previous data is preserved in PostgreSQL. The pipeline picks up from where it left off.

---

## 📈 Performance

| Metric | Value |
|--------|-------|
| Crawl throughput | ~50 pages/min |
| LLM extraction | ~12 extractions/min (Gemini free tier) |
| Papers discovered | 500+ per hour (ArXiv) |
| Jobs discovered | 60+ per session (LinkedIn) |
| API cost | **$0/month** (all free tier) |
| Data freshness | Updated every 20 minutes |

---

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

---

## 📄 License

MIT License — see [LICENSE](LICENSE) for details.

---

<div align="center">

**Built with Python · Powered by AI · Runs for free**

⭐ Star this repo if ProvenMesh helped you!

</div>
