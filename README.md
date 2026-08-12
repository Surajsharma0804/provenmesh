# ProvenMesh

> Evidence-first Intelligence Graph Pipeline for GraphOne/FrontierAtlas

ProvenMesh is an async-first, distributed ingestion and intelligence-graph pipeline that discovers AI ecosystem data across **Startups, Products, Research Papers, Jobs, and News** — extracts structured records through a multi-provider LLM pipeline — grounds every field against source evidence — resolves entities deterministically and semantically — and exports only validated records to a six-tab Google Sheet.

## Architecture

```
┌──────────────┐     ┌──────────────┐     ┌──────────────────┐
│   Producers  │────▶│ Redis Streams │────▶│  Crawl Workers   │
│  (5 verticals│     │   (Queues)    │     │  (Tiered Fetch)  │
└──────────────┘     └──────────────┘     └────────┬─────────┘
                                                    │
                                          ┌─────────▼─────────┐
                                          │    MinIO / S3      │
                                          │  (Raw Evidence)    │
                                          └─────────┬─────────┘
                                                    │
                                          ┌─────────▼─────────┐
                                          │ Extraction Workers │
                                          │ Gemini→Groq→Deep  │
                                          │ + Grounding Engine │
                                          └─────────┬─────────┘
                                                    │
                                          ┌─────────▼─────────┐
                                          │ Resolution Workers │
                                          │ Exact→Fuzzy→Embed  │
                                          │ + Review Queue     │
                                          └─────────┬─────────┘
                                                    │
                                     ┌──────────────▼──────────────┐
                                     │   PostgreSQL + pgvector     │
                                     │  (Entities, Relationships,  │
                                     │   Evidence, Provenance)     │
                                     └──────────────┬──────────────┘
                                                    │
                                          ┌─────────▼─────────┐
                                          │  Google Sheets     │
                                          │  (6-Tab Export)    │
                                          └───────────────────┘
```

## Key Design Principles

| Principle | Implementation |
|-----------|----------------|
| **Evidence-First** | Every extracted field carries `{value, evidence, confidence}` — grounding verifies evidence exists in source text |
| **Immutable Raw Store** | Every fetched page stored in S3 before extraction — enables re-extraction without re-scraping |
| **Idempotent Workers** | PostgreSQL `ON CONFLICT DO UPDATE` + Redis atomic SADD + consumer group ACK-after-commit |
| **Fault Tolerant** | Dead Letter Queue for failed messages, circuit breakers for LLM providers, poison message detection |
| **Cost Governed** | Token budget reservation before LLM calls, 80%/90%/100% threshold enforcement |
| **Ethical Crawling** | robots.txt enforcement, per-domain rate limiting, Crawl-delay honor |

## Six-Phase Evaluation Structure

1. **Discovery** — Producers enumerate listing pages across 5 verticals
2. **Acquisition** — Tiered fetching (aiohttp → Playwright → Playwright+Proxy)
3. **Extraction** — LLM pipeline with fallback chain and evidence-first prompts
4. **Grounding** — Post-extraction verification of every field against source text
5. **Resolution** — Entity disambiguation (Exact → Normalized → Fuzzy → Embedding → Review)
6. **Export** — Triple quality gate (grounded + schema-valid + resolved) → Google Sheets

## Quick Start

### Prerequisites

- Python 3.12+
- Docker & Docker Compose
- API keys for Gemini, Groq, and/or DeepSeek

### Setup

```bash
# Clone and install
git clone https://github.com/Surajsharma0804/provenmesh.git
cd provenmesh

# Copy environment config
cp .env.example .env
# Edit .env with your API keys

# Start infrastructure
docker compose up -d

# Install Python dependencies
pip install -e ".[dev]"

# Run database migrations
alembic upgrade head

# Install Playwright browsers
playwright install chromium
```

### Running the Pipeline

```bash
# Run discovery producers (all verticals)
python -m provenmesh crawl

# Start crawl workers (parallel)
python -m provenmesh fetch --workers 4

# Start extraction workers
python -m provenmesh extract --workers 2

# Start resolution workers
python -m provenmesh resolve --workers 2

# Export to Google Sheets
python -m provenmesh export

# Or run everything together
python -m provenmesh run --crawl-workers 4 --extract-workers 2 --resolve-workers 2
```

### Running Tests

```bash
# All tests
pytest tests/ -v

# Unit tests only
pytest tests/unit/ -v

# Contract tests (LLM provider interface)
pytest tests/contract/ -v

# With coverage
pytest tests/ --cov=src/provenmesh --cov-report=html
```

## Project Structure

```
ProvenMesh/
├── src/provenmesh/
│   ├── config/          # Settings, constants
│   ├── domain/          # Entities, enums, events, evidence models
│   ├── crawler/         # Producers, fetcher, dedup, rate limiter, robots.txt
│   │   └── producers/   # 5 vertical-specific producers
│   ├── raw_store/       # S3 object storage for raw evidence
│   ├── extraction/      # LLM orchestrator, chunking, prompts, cache, cost guard
│   │   └── providers/   # Gemini, Groq, DeepSeek (interchangeable)
│   ├── grounding/       # Post-extraction evidence verification
│   ├── resolver/        # Entity resolution cascade, seeds, review queue
│   ├── graph/           # SQLAlchemy ORM models, repositories
│   ├── export/          # Google Sheets 6-tab exporter
│   ├── queue/           # Redis Streams wrapper, consumer, producer, DLQ
│   ├── storage/         # Database engine, sessions, transactions
│   ├── workers/         # Crawl, extraction, resolution worker processes
│   ├── observability/   # Structured logging, Prometheus metrics, tracing, health
│   ├── security/        # Secrets management, input sanitization
│   └── main.py          # CLI entry point
├── configs/             # YAML configs (sources, models, thresholds, logging)
├── schemas/             # JSON schemas for all entity types
├── migrations/          # Alembic database migrations
├── tests/
│   ├── unit/            # Pure unit tests
│   ├── contract/        # Provider interface contract tests
│   ├── integration/     # Tests requiring Docker services
│   └── e2e/             # Full pipeline end-to-end tests
├── docker-compose.yml   # Postgres + Redis + MinIO
├── Dockerfile           # Production container
├── pyproject.toml       # Dependencies and tool config
├── Makefile             # Developer workflow automation
└── .env.example         # Environment variable template
```

## Technology Stack

| Component | Technology |
|-----------|-----------|
| Language | Python 3.12+ |
| Async Runtime | asyncio + aiohttp |
| Queue | Redis Streams (consumer groups) |
| Database | PostgreSQL 16 + pgvector |
| Object Store | MinIO (S3-compatible) |
| LLM Providers | Gemini Flash → Groq Llama 3 → DeepSeek |
| Browser Automation | Playwright (Chromium) |
| Entity Resolution | RapidFuzz + Sentence-Transformers |
| Schema Validation | JSON Schema (jsonschema) |
| ORM | SQLAlchemy 2.0 (async) |
| Migrations | Alembic |
| Metrics | Prometheus (prometheus_client) |
| Logging | structlog (JSON) |
| Export | Google Sheets API v4 |

## Configuration

All operational thresholds are externalized in `configs/thresholds.yaml`:

- **Grounding**: fuzzy ratio ≥ 90, number tolerance ±1%, date tolerance ±1 day
- **Resolution**: fuzzy ≥ 85, embedding accept ≥ 0.88, review band [0.75, 0.88)
- **Cost**: daily token budget 5M, warning at 80%, halt at 100%
- **Backpressure**: high water 10K, low water 5K
- **Retry**: 5 attempts, exponential backoff 1s–60s with jitter

## License

MIT

## Author

Suraj Sharma
