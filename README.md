<div align="center">
<img src="assets/banner.png" width="100%" alt="ProvenMesh — Autonomous AI Ecosystem Intelligence"/>
</div>

<br/>

<div align="center">

**Autonomous intelligence pipeline for the AI ecosystem.**  
Crawls 24+ sources · extracts structured entities · verifies every claim · exports to Google Sheets every 20 minutes.

[![Python](https://img.shields.io/badge/Python-3.13-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-22c55e?style=flat-square)](LICENSE)
[![Cost](https://img.shields.io/badge/Cost-%240%2Fmonth-22c55e?style=flat-square)](https://github.com/Surajsharma0804/provenmesh)
[![Hallucinations](https://img.shields.io/badge/Hallucinations-0%25-22c55e?style=flat-square)](https://github.com/Surajsharma0804/provenmesh)

</div>

---

## Overview

ProvenMesh is an **always-on research pipeline** for the AI ecosystem. It continuously monitors research preprints, startup announcements, product launches, job postings, and news — extracts structured entity data using a multi-provider LLM fallback chain — then publishes everything to a live Google Sheet, refreshed every 20 minutes.

Every extracted field is **evidence-grounded**: the pipeline enforces that each value is accompanied by a verbatim quote from the source document. Fields with no supporting evidence are not written. The AI cannot fabricate.

**[Open Live Dashboard →](https://docs.google.com/spreadsheets/d/130p3Bo5gZRBHWt9tK8J8BqVP5YY2ckaoCWW1UeC7vEc)**

---

## Pipeline

<img src="assets/architecture.png" width="100%" alt="ProvenMesh Pipeline Architecture"/>

The pipeline runs five sequential stages:

1. **Crawl** — async workers fetch content from 24 configured sources (ArXiv, TechCrunch, HuggingFace, OpenAI/Anthropic/DeepMind blogs, Hacker News, Wired, MIT Tech Review, and others). Raw HTML is archived to MinIO.

2. **Extract** — an LLM reads each document and populates a typed entity schema. A 4-provider fallback chain (Gemini 2.5 Flash → Groq 70B → Nemotron 120B → Gemma 31B) ensures extraction continues even when individual providers hit rate limits.

3. **Verify** — the grounding layer checks every extracted field for a supporting evidence quote. Ungrounded fields are rejected and not persisted.

4. **Resolve** — fuzzy matching with sentence embeddings deduplicates entities across sources. `"OpenAI"` in one article and `"openai.com"` in another become a single canonical record.

5. **Export** — verified, resolved entities are written to six Google Sheets tabs on a 20-minute cycle.

---

## Output

| Tab | Contents |
|-----|----------|
| Startups | Company name, funding total, founders, HQ, investors, tech stack |
| Products | Tool name, pricing model, features, GitHub link |
| Papers | Title, abstract, authors, ArXiv ID, affiliations |
| Jobs | Role, company, salary range, skills, remote policy |
| News | Headline, summary, publisher, mentioned entities |
| Entity Mapping Log | Full resolution audit trail for every entity |

---

## Evidence Schema

Each extracted field carries its source evidence:

```json
{
  "fundingTotal": {
    "value": "$7.3B",
    "evidence": "...raised $7.3 billion in total funding as of 2024..."
  }
}
```

Fields without a matching evidence quote are left empty. This schema is enforced at the extraction layer — not as a post-processing filter.

---

## Comparison

| | ProvenMesh | Manual Research | Crunchbase Pro |
|--|:--:|:--:|:--:|
| Cost | **$0/month** | Free | ~$500/month |
| Refresh cadence | **20 minutes** | Manual | Days to weeks |
| Grounding | **Evidence-required** | Human judgment | Human curation |
| Source breadth | **24+ live feeds** | Ad hoc | Proprietary DB |
| Hallucinations | **0% (enforced)** | Possible | Possible |

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Runtime | Python 3.13, asyncio |
| LLM Extraction | Gemini 2.5 Flash / Groq Llama 70B / Nemotron 120B / Gemma 31B |
| Queue | Redis Streams |
| Database | PostgreSQL 16 + pgvector |
| Raw Archive | MinIO (S3-compatible) |
| Entity Matching | RapidFuzz + sentence-transformers |
| Export | Google Sheets API v4 |
| Infrastructure | Docker Compose |

---

## Quick Start

### Requirements

- [Docker Desktop](https://www.docker.com/products/docker-desktop/)
- Python 3.11+
- Free API keys (5 minutes — see [API Keys](#api-keys))

### Install

```bash
git clone https://github.com/Surajsharma0804/provenmesh.git
cd provenmesh
cp .env.example .env
# Add your API keys to .env
docker compose up -d
pip install -e ".[dev]"
alembic upgrade head
python scripts/seed_entities.py
```

### Run

**Windows**
```
start.bat
```

**Linux / macOS**
```bash
python -m provenmesh.main run \
  --crawl-workers 3 \
  --extract-workers 2 \
  --resolve-workers 2 \
  --auto-export \
  --export-interval 20
```

### Manual export
```bash
python -m provenmesh.main export
```

---

## API Keys

All providers have a free tier sufficient to run the pipeline continuously.

| Provider | Model | Free Limit | Link |
|----------|-------|-----------|------|
| Google AI Studio | Gemini 2.5 Flash | 15 req/min | [aistudio.google.com](https://aistudio.google.com/app/apikey) |
| Groq | Llama 3.3 70B | 14,400 req/day | [console.groq.com](https://console.groq.com/keys) |
| OpenRouter | Nemotron 120B + Gemma 31B | Free tier | [openrouter.ai](https://openrouter.ai/keys) |

---

## Project Structure

```
provenmesh/
├── src/provenmesh/
│   ├── crawler/         # Source fetchers — async HTTP + Playwright
│   ├── extraction/      # LLM extraction with 4-provider fallback
│   ├── grounding/       # Evidence verification (anti-hallucination)
│   ├── resolver/        # Entity deduplication + canonicalization
│   ├── export/          # Google Sheets API integration
│   └── graph/           # PostgreSQL repository layer
├── assets/              # Banner, logo, architecture diagrams
├── start.bat            # Windows launcher
├── docker-compose.yml   # PostgreSQL + Redis + MinIO
└── .env.example         # Environment variable template
```

---

## Persistence

All data is stored in Docker volumes and persists across restarts. To resume after shutdown:

1. Start Docker Desktop
2. Run `start.bat` (Windows) or the run command above

---

## License

[MIT](LICENSE) — free to use, modify, and distribute.

---

<div align="center">
<img src="assets/logo.png" width="60" alt="ProvenMesh"/>
<br/><br/>
<sub>Python 3.13 · Free AI APIs · $0/month operating cost</sub>
</div>
