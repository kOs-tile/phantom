# PHANTOM — Hermes Agent Stealth Browser Engine

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111%2B-009688.svg)](https://fastapi.tiangolo.com/)
[![Playwright](https://img.shields.io/badge/Playwright-async-45ba4b.svg)](https://playwright.dev/python/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Tests](https://img.shields.io/badge/tests-70%2B-brightgreen.svg)]()

A production-grade stealth browser automation engine designed as a Hermes agent skill. PHANTOM enables Hermes agents to browse the web undetected — scraping prices, monitoring pages, filling forms, and extracting structured data — while mimicking real human behavior to bypass anti-bot systems.

---

## Architecture

```
                        ┌─────────────────────────────────────┐
                        │         PHANTOM FastAPI (8001)       │
                        │  /browse  /scrape  /extract  /jobs   │
                        └────────────────┬────────────────────┘
                                         │
              ┌──────────────────────────▼─────────────────────────────┐
              │                   Core Engine                           │
              │                                                         │
              │  ┌──────────────┐   ┌──────────────┐   ┌───────────┐  │
              │  │  Stealth     │   │   Browser    │   │  Queue    │  │
              │  │  Layer       │   │   Layer      │   │  Layer    │  │
              │  │              │   │              │   │           │  │
              │  │ fingerprint  │   │ session.py   │   │ TaskQueue │  │
              │  │ humanizer    │   │ navigator.py │   │ Scheduler │  │
              │  │ evasion      │   │ extractor.py │   │           │  │
              │  └──────────────┘   └──────────────┘   └───────────┘  │
              │                                                         │
              │  ┌──────────────────────────────────────────────────┐  │
              │  │              Extractors                           │  │
              │  │   price.py    article.py    structured.py         │  │
              │  └──────────────────────────────────────────────────┘  │
              │                                                         │
              │  ┌──────────────┐   ┌─────────────────────────────┐   │
              │  │  Cache       │   │    Hermes Skill              │   │
              │  │  Redis/Mem   │   │    PHANTOM.md (8 tools)      │   │
              │  └──────────────┘   └─────────────────────────────┘   │
              └─────────────────────────────────────────────────────────┘
                                         │
              ┌──────────────────────────▼──────────────────────────────┐
              │                  Playwright (Chromium)                   │
              │   Context per task • Evasion scripts • Fingerprinting    │
              └─────────────────────────────────────────────────────────┘
```

---

## Features

### Stealth Layer
- **Fingerprint randomization** — Realistic Chrome 120–125 User-Agents, weighted viewport sizes (1366×768, 1440×900, 1920×1080, 2560×1440), timezone/locale pairing, full HTTP header sets
- **Human behavior simulation** — Bezier-curve mouse paths, random micro-delays (50–300ms), ease-in-out scroll patterns, typo-and-correct form fill simulation
- **WebDriver evasion** — Hides `navigator.webdriver`, fakes `chrome.runtime`, spoofs `navigator.plugins`, overrides `navigator.languages`, fixes iframe detection, spoofs hardware concurrency

### Browser Engine
- Async Playwright (Chromium) — one browser, isolated contexts per task
- Smart wait strategies: `networkidle`, `domcontentloaded`, custom selector wait
- Screenshot capture on-demand and on error
- JavaScript injection and evaluation

### Extractors
- **Price** — Regex + CSS for USD/EUR/GBP/JPY, Amazon ASIN detection, eBay listings, sale vs. original price, stock status
- **Article** — Readability-style extraction: title, author, date, full content, word count, images
- **Structured** — JSON-LD, OpenGraph, Twitter Cards, Schema.org microdata, product schema

### Task Queue
- Async priority queue (HIGH / MEDIUM / LOW)
- Max 3 concurrent tasks (configurable)
- Exponential backoff retry (max 3 attempts)
- Full lifecycle tracking: `pending → running → done | failed | retrying`

### API
- FastAPI with lifespan management
- Full OpenAPI docs at `/docs`
- Redis cache with transparent in-memory fallback

---

## Quick Start

```bash
# 1. Clone and install
git clone https://github.com/your-org/phantom.git
cd phantom
pip install -r requirements.txt

# 2. Install Chromium
playwright install chromium

# 3. Configure environment
cp .env.example .env
# Edit .env as needed

# 4. Start the API
uvicorn phantom.api.main:app --host 0.0.0.0 --port 8001

# 5. Run the demo (no browser needed)
python scripts/demo.py
```

---

## API Reference

### `POST /browse`
Navigate to a URL and return full page content.

```bash
curl -X POST http://localhost:8001/browse \
  -H "Content-Type: application/json" \
  -d '{"url": "https://news.ycombinator.com", "capture_screenshot": true}'
```

### `POST /scrape`
Extract specific data fields using CSS selectors.

```bash
curl -X POST http://localhost:8001/scrape \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://books.toscrape.com",
    "selectors": {
      "title": "h1",
      "books": ".product_pod h3 a"
    },
    "multiple": {"books": true}
  }'
```

### `POST /extract/price`
Extract product pricing from any e-commerce URL.

```bash
curl -X POST http://localhost:8001/extract/price \
  -H "Content-Type: application/json" \
  -d '{"url": "https://www.amazon.com/dp/B09G9FPHY6"}'
```

### `POST /extract/article`
Extract article content from news and blog pages.

```bash
curl -X POST http://localhost:8001/extract/article \
  -H "Content-Type: application/json" \
  -d '{"url": "https://techcrunch.com/2024/06/15/example/"}'
```

### `POST /screenshot`
Capture a full-page screenshot.

```bash
curl -X POST http://localhost:8001/screenshot \
  -H "Content-Type: application/json" \
  -d '{"url": "https://stripe.com/pricing", "full_page": true}'
```

### `GET /jobs`
List all task queue jobs.

```bash
curl http://localhost:8001/jobs?status_filter=running&limit=10
```

### `GET /jobs/{task_id}`
Get a specific job status and result.

```bash
curl http://localhost:8001/jobs/3f8b2c1a-...
```

### `GET /health`
Service health check.

```bash
curl http://localhost:8001/health
```

---

## Hermes Integration

PHANTOM ships with a complete Hermes skill definition at `hermes_skill/PHANTOM.md`.
It exposes 8 tools to any Hermes agent:

| Tool | Description |
|---|---|
| `browse_url` | Navigate + extract page content |
| `scrape_page` | CSS selector-based extraction |
| `extract_price` | E-commerce price extraction |
| `extract_article` | News/blog article extraction |
| `take_screenshot` | Full-page PNG capture |
| `schedule_monitor` | Recurring scrape jobs (cron) |
| `list_jobs` | View task queue |
| `get_job_result` | Get job result by ID |

```python
# In a Hermes agent
price = phantom.extract_price(url="https://www.amazon.com/dp/B09XS7JWHH")
if price["discount_percent"] > 25:
    oracle.alert(f"Price drop: {price['product_title']} now ${price['current_price']}")
```

---

## DealHarvest Integration

PHANTOM is the stealth browser backbone for **DealHarvest** deal discovery pipelines:

```python
# DealHarvest → PHANTOM integration
deals = phantom.scrape_page(
    url="https://slickdeals.net/deals/",
    selectors={
        "titles": ".bp-c-card-deal-title",
        "prices": ".bp-c-card-deal-price",
        "stores": ".bp-c-card-store-name"
    },
    multiple={"titles": True, "prices": True, "stores": True}
)
```

---

## Configuration

| Variable | Default | Description |
|---|---|---|
| `PHANTOM_API_URL` | `http://localhost:8001` | Base URL of PHANTOM service |
| `PHANTOM_API_KEY` | (empty) | Optional API key |
| `REDIS_URL` | `redis://localhost:6379/1` | Redis connection URL |
| `MAX_CONCURRENT_TASKS` | `3` | Max parallel browser tasks |
| `BROWSER_HEADLESS` | `true` | Run browser in headless mode |
| `DEFAULT_TIMEOUT_MS` | `30000` | Navigation timeout (ms) |
| `SCREENSHOT_DIR` | `./screenshots` | Screenshot save directory |
| `RATE_LIMIT_DELAY_MS` | `1500` | Min delay between requests |
| `USER_AGENT_ROTATION` | `true` | Enable UA rotation |
| `PROXY_URL` | (empty) | Optional HTTP proxy |
| `LOG_LEVEL` | `INFO` | Logging level |

---

## Development

```bash
# Install dev dependencies
pip install -r requirements.txt

# Run tests
pytest tests/ -v

# Run with coverage
pytest tests/ -v --cov=phantom --cov-report=html

# Run demo
python scripts/demo.py
```

---

## Project Structure

```
phantom/
├── phantom/              # Core library
│   ├── config.py         # Pydantic Settings
│   ├── models.py         # All Pydantic v2 data models
│   ├── stealth/          # Fingerprint, humanizer, evasion
│   ├── browser/          # Playwright session, navigator, extractor
│   ├── queue/            # Async task queue + APScheduler
│   ├── extractors/       # Price, article, structured data
│   ├── api/              # FastAPI app + routes
│   └── cache/            # Redis/memory result store
├── hermes_skill/         # PHANTOM.md Hermes skill definition
├── scripts/demo.py       # Rich CLI demo
├── tests/                # 70+ tests (no real browser)
├── .env.example
├── requirements.txt
└── pyproject.toml
```

---

## License

MIT © Hermes Agent Team
