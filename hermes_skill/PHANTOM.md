---
name: phantom
version: 1.0.0
description: >
  Stealth browser automation — browse, scrape, and extract structured data
  from any website undetected. Mimics real human behavior (mouse, scroll,
  typing) to bypass anti-bot systems. Supports price monitoring, article
  extraction, screenshot capture, and recurring scrape jobs.
author: Hermes Agent Team
license: MIT
tags:
  - browser
  - scraping
  - stealth
  - e-commerce
  - monitoring
auth:
  type: env
  vars:
    - PHANTOM_API_URL        # Required: base URL of PHANTOM service (e.g. http://localhost:8001)
    - PHANTOM_API_KEY        # Optional: API key for protected deployments
tools:
  - browse_url
  - scrape_page
  - extract_price
  - extract_article
  - take_screenshot
  - schedule_monitor
  - list_jobs
  - get_job_result
integrations:
  - ORACLE                   # Real-time price monitoring + alerting
  - DEALHARVEST              # Deal discovery + comparison pipelines
---

# PHANTOM — Hermes Agent Stealth Browser Engine

PHANTOM gives Hermes agents a production-grade stealth browser to interact
with any website as if they were a real human user. It handles fingerprint
randomization, behavioral simulation, and WebDriver evasion automatically.

## Authentication

Set these environment variables before use:

```bash
export PHANTOM_API_URL=http://localhost:8001
export PHANTOM_API_KEY=your_key_here   # optional
```

---

## Tools

### `browse_url`

Navigate to any URL and return the full page content, text, links,
and an optional screenshot.

**Input schema:**
```json
{
  "url": "string (required) — target URL",
  "wait_strategy": "networkidle | domcontentloaded | load (default: networkidle)",
  "wait_for_selector": "string — CSS selector to wait for before returning",
  "timeout_ms": "integer — navigation timeout in ms (default: 30000)",
  "javascript": "string — JavaScript to inject and execute",
  "capture_screenshot": "boolean (default: false)",
  "extract_links": "boolean (default: true)",
  "priority": "high | medium | low (default: medium)"
}
```

**Output schema:**
```json
{
  "task_id": "string",
  "url": "string",
  "final_url": "string",
  "status_code": "integer",
  "title": "string | null",
  "html": "string | null",
  "text_content": "string | null",
  "links": ["string"],
  "screenshot_path": "string | null",
  "javascript_result": "any | null",
  "load_time_ms": "integer",
  "success": "boolean",
  "error": "string | null"
}
```

**Example:**
```python
result = phantom.browse_url(
    url="https://news.ycombinator.com",
    wait_strategy="networkidle",
    extract_links=True
)
print(result["title"])       # "Hacker News"
print(len(result["links"]))  # 120+
```

---

### `scrape_page`

Navigate to a URL and extract specific data fields using CSS selectors.
Ideal for structured extraction from known page layouts.

**Input schema:**
```json
{
  "url": "string (required)",
  "selectors": {
    "field_name": "css_selector"
  },
  "multiple": {
    "field_name": true
  },
  "wait_for_selector": "string | null",
  "timeout_ms": "integer (default: 30000)",
  "priority": "high | medium | low"
}
```

**Output schema:**
```json
{
  "job_id": "string",
  "url": "string",
  "extractor_type": "custom",
  "data": { "field_name": "extracted_value" },
  "raw_fields": { "field_name": "raw_text" },
  "confidence": "float",
  "success": "boolean",
  "error": "string | null"
}
```

**Example:**
```python
result = phantom.scrape_page(
    url="https://books.toscrape.com",
    selectors={
        "title": "h1",
        "books": ".product_pod h3 a"
    },
    multiple={"books": True}
)
print(result["data"]["books"])   # ["A Light...", "Tipping the...", ...]
```

---

### `extract_price`

Extract price information from any e-commerce product page.
Auto-detects Amazon, eBay, Shopify, and generic stores.

**Input schema:**
```json
{
  "url": "string (required)",
  "timeout_ms": "integer (default: 30000)"
}
```

**Output schema:**
```json
{
  "url": "string",
  "current_price": "float | null",
  "original_price": "float | null",
  "currency": "string (e.g. USD)",
  "currency_symbol": "string (e.g. $)",
  "discount_percent": "float | null",
  "in_stock": "boolean | null",
  "asin": "string | null",
  "product_title": "string | null",
  "price_text": "string | null",
  "extracted_at": "ISO 8601 datetime"
}
```

**Example:**
```python
price = phantom.extract_price(
    url="https://www.amazon.com/dp/B09G9FPHY6"
)
print(f"{price['currency_symbol']}{price['current_price']}")  # "$24.99"
print(f"Was: {price['original_price']}")                       # 34.99
print(f"Discount: {price['discount_percent']}%")               # 28.6%
```

---

### `extract_article`

Extract structured article content from news and blog pages.
Returns title, author, publish date, full text, and metadata.

**Input schema:**
```json
{
  "url": "string (required)",
  "timeout_ms": "integer (default: 30000)"
}
```

**Output schema:**
```json
{
  "url": "string",
  "title": "string | null",
  "author": "string | null",
  "published_date": "string | null",
  "content": "string | null",
  "summary": "string | null",
  "word_count": "integer",
  "images": ["string"],
  "tags": ["string"],
  "site_name": "string | null",
  "language": "string | null"
}
```

**Example:**
```python
article = phantom.extract_article(
    url="https://techcrunch.com/2024/06/15/openai-gpt5/"
)
print(article["title"])       # "OpenAI announces GPT-5"
print(article["word_count"])  # 1842
print(article["author"])      # "Jane Smith"
```

---

### `take_screenshot`

Navigate to a URL and capture a full-page PNG screenshot.
Returns the path to the saved file.

**Input schema:**
```json
{
  "url": "string (required)",
  "full_page": "boolean (default: true)",
  "wait_for_selector": "string | null",
  "timeout_ms": "integer (default: 30000)"
}
```

**Output schema:**
```json
{
  "task_id": "string",
  "url": "string",
  "screenshot_path": "string | null",
  "success": "boolean"
}
```

**Example:**
```python
shot = phantom.take_screenshot(
    url="https://stripe.com/pricing",
    full_page=True
)
print(shot["screenshot_path"])  # "./screenshots/abc123.png"
```

---

### `schedule_monitor`

Set up a recurring price or content monitor using a cron schedule.
Integrates with ORACLE for real-time alerting when thresholds are crossed.

**Input schema:**
```json
{
  "url": "string (required)",
  "selectors": { "field": "css_selector" },
  "schedule_cron": "string (cron expression, e.g. '0 */6 * * *')",
  "priority": "high | medium | low"
}
```

**Output schema:**
```json
{
  "job_id": "string",
  "url": "string",
  "schedule_cron": "string",
  "next_run": "ISO 8601 datetime"
}
```

**Example:**
```python
job = phantom.schedule_monitor(
    url="https://www.amazon.com/dp/B09G9FPHY6",
    selectors={"price": ".a-price .a-offscreen"},
    schedule_cron="0 */4 * * *"  # every 4 hours
)
print(job["job_id"])   # "job-uuid-here"
```

---

### `list_jobs`

List all task queue jobs (pending, running, completed, failed).

**Input schema:**
```json
{
  "status": "pending | running | done | failed | retrying | null",
  "limit": "integer (default: 50)"
}
```

**Output schema:**
```json
[
  {
    "task_id": "string",
    "task_type": "string",
    "status": "string",
    "priority": "string",
    "url": "string",
    "attempt": "integer",
    "created_at": "ISO 8601",
    "completed_at": "ISO 8601 | null",
    "error": "string | null"
  }
]
```

---

### `get_job_result`

Retrieve the result and status of a specific job by task ID.

**Input schema:**
```json
{
  "task_id": "string (required)"
}
```

**Output:** Same as individual TaskRecord with full `result` payload.

---

## Integration Notes

### ORACLE Integration (Real-time Price Monitoring)

PHANTOM pairs naturally with ORACLE for price threshold alerting:

```python
# Hermes agent combining PHANTOM + ORACLE
async def monitor_price_drop(url: str, target_price: float):
    price = phantom.extract_price(url=url)
    if price["current_price"] and price["current_price"] <= target_price:
        oracle.trigger_alert(
            channel="deals",
            message=f"Price drop! {price['product_title']} now ${price['current_price']}"
        )
```

### DealHarvest Integration

PHANTOM serves as the browser backbone for DealHarvest's deal discovery pipeline:

```python
# DealHarvest uses PHANTOM for stealth product scraping
deals = phantom.scrape_page(
    url="https://slickdeals.net/deals/",
    selectors={
        "title": ".bp-c-card-deal-title",
        "price": ".bp-c-card-deal-price",
        "store": ".bp-c-card-store-name"
    },
    multiple={
        "title": True,
        "price": True,
        "store": True
    }
)
```

### Error Handling

All PHANTOM tools return a `success` boolean. On failure, check the `error` field:

```python
result = phantom.browse_url(url="https://example.com")
if not result["success"]:
    logger.error(f"Browse failed: {result['error']}")
    # PHANTOM automatically retries up to 3 times before marking failed
```

### Rate Limiting

PHANTOM respects configurable rate limits (`RATE_LIMIT_DELAY_MS=1500`).
For high-volume use, increase `MAX_CONCURRENT_TASKS` and add proxy rotation
via `PROXY_URL`.
