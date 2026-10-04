"""
PHANTOM Demo
Rich CLI demonstration of PHANTOM capabilities.
Runs with simulated output — no real browser or API keys required.
"""

from __future__ import annotations

import asyncio
import random
import time
from datetime import datetime
from typing import Any, Dict, List

from rich import box
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.table import Table
from rich.text import Text
from rich import print as rprint

console = Console()


# ── Simulated Data ────────────────────────────────────────────────────────────

DEMO_FINGERPRINTS = [
    {
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.6367.207 Safari/537.36",
        "viewport": "1920x1080",
        "locale": "en-US",
        "timezone": "America/New_York",
        "os": "Windows",
    },
    {
        "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_2_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.6422.141 Safari/537.36",
        "viewport": "1440x900",
        "locale": "en-GB",
        "timezone": "Europe/London",
        "os": "macOS",
    },
    {
        "user_agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.6312.122 Safari/537.36",
        "viewport": "1366x768",
        "locale": "de-DE",
        "timezone": "Europe/Berlin",
        "os": "Linux",
    },
]

DEMO_BROWSE_RESULTS = [
    {
        "url": "https://news.ycombinator.com",
        "title": "Hacker News",
        "status_code": 200,
        "links": 147,
        "load_time_ms": 1243,
        "word_count": 3821,
    },
    {
        "url": "https://github.com/trending",
        "title": "Trending repositories on GitHub today",
        "status_code": 200,
        "links": 89,
        "load_time_ms": 987,
        "word_count": 2104,
    },
]

DEMO_PRICES = [
    {
        "product": "Sony WH-1000XM5 Headphones",
        "url": "https://www.amazon.com/dp/B09XS7JWHH",
        "current_price": 279.99,
        "original_price": 399.99,
        "discount": 30.0,
        "currency": "USD",
        "in_stock": True,
        "asin": "B09XS7JWHH",
    },
    {
        "product": "Apple AirPods Pro (2nd Gen)",
        "url": "https://www.amazon.com/dp/B0BDHWDR12",
        "current_price": 189.00,
        "original_price": 249.00,
        "discount": 24.1,
        "currency": "USD",
        "in_stock": True,
        "asin": "B0BDHWDR12",
    },
    {
        "product": "LEGO Technic BMW M 1000 RR",
        "url": "https://www.ebay.com/itm/305871234561",
        "current_price": 87.49,
        "original_price": 99.99,
        "discount": 12.5,
        "currency": "USD",
        "in_stock": False,
        "asin": None,
    },
]

DEMO_ARTICLE = {
    "url": "https://techcrunch.com/2024/06/15/example-article/",
    "title": "The Next Wave of AI Agents: How They're Changing Software Development",
    "author": "Sarah Chen",
    "published_date": "2024-06-15T14:30:00Z",
    "word_count": 2147,
    "site_name": "TechCrunch",
    "summary": "AI agents are moving beyond simple chat interfaces to become active participants in software development workflows...",
    "images": [
        "https://techcrunch.com/wp-content/uploads/2024/06/ai-agents-hero.jpg",
        "https://techcrunch.com/wp-content/uploads/2024/06/workflow-diagram.png",
    ],
}

DEMO_QUEUE = [
    {"task_id": "3f8b2c1a", "type": "price", "url": "amazon.com/dp/B09XS7JWHH", "status": "done", "ms": 1891},
    {"task_id": "7a4e9d2f", "type": "browse", "url": "news.ycombinator.com", "status": "done", "ms": 1243},
    {"task_id": "1c5f8e3b", "type": "article", "url": "techcrunch.com/...", "status": "running", "ms": None},
    {"task_id": "9b2d7f4a", "type": "scrape", "url": "slickdeals.net/deals", "status": "pending", "ms": None},
    {"task_id": "5e1a8c9d", "type": "price", "url": "ebay.com/itm/305871234561", "status": "failed", "ms": None},
]


# ── Demo Sections ─────────────────────────────────────────────────────────────

def demo_header() -> None:
    """Display PHANTOM ASCII banner."""
    banner = Text()
    banner.append("██████╗ ██╗  ██╗ █████╗ ███╗   ██╗████████╗ ██████╗ ███╗   ███╗\n", style="bold cyan")
    banner.append("██╔══██╗██║  ██║██╔══██╗████╗  ██║╚══██╔══╝██╔═══██╗████╗ ████║\n", style="bold cyan")
    banner.append("██████╔╝███████║███████║██╔██╗ ██║   ██║   ██║   ██║██╔████╔██║\n", style="bold cyan")
    banner.append("██╔═══╝ ██╔══██║██╔══██║██║╚██╗██║   ██║   ██║   ██║██║╚██╔╝██║\n", style="bold cyan")
    banner.append("██║     ██║  ██║██║  ██║██║ ╚████║   ██║   ╚██████╔╝██║ ╚═╝ ██║\n", style="bold cyan")
    banner.append("╚═╝     ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═══╝   ╚═╝    ╚═════╝ ╚═╝     ╚═╝\n", style="bold cyan")

    subtitle = Text("Browser Automation & Extraction Reliability Research  •  v0.1.0", style="dim white")
    console.print(Panel(banner, subtitle=subtitle, border_style="cyan", padding=(0, 2)))
    console.print()


def demo_fingerprints() -> None:
    """Demo: Fingerprint generation."""
    console.rule("[bold cyan]1. Browser Fingerprint Randomization[/bold cyan]")
    console.print()
    console.print(
        "[dim]PHANTOM generates a fresh, realistic browser fingerprint for each task.[/dim]\n"
    )

    with Progress(
        SpinnerColumn(),
        TextColumn("[cyan]{task.description}"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Generating fingerprints...", total=3)
        for fp in DEMO_FINGERPRINTS:
            time.sleep(0.4)
            progress.advance(task)

    table = Table(box=box.ROUNDED, border_style="cyan", show_header=True)
    table.add_column("OS", style="bold white", width=10)
    table.add_column("Viewport", style="green", width=12)
    table.add_column("Locale", style="yellow", width=8)
    table.add_column("Timezone", style="blue", width=22)
    table.add_column("Chrome UA", style="dim white", overflow="fold")

    for fp in DEMO_FINGERPRINTS:
        chrome_match = fp["user_agent"].split("Chrome/")[1].split(" ")[0] if "Chrome/" in fp["user_agent"] else "?"
        table.add_row(
            fp["os"],
            fp["viewport"],
            fp["locale"],
            fp["timezone"],
            f"Chrome/{chrome_match}",
        )

    console.print(table)
    console.print(
        "\n[green]✓[/green] Evasion scripts injected: "
        "[dim]hide_webdriver, fake_chrome_runtime, fake_plugins, permissions_override[/dim]\n"
    )


def demo_browse() -> None:
    """Demo: Page browsing."""
    console.rule("[bold cyan]2. Page Navigation (Simulated Demo)[/bold cyan]")
    console.print()

    for result in DEMO_BROWSE_RESULTS:
        with Progress(
            SpinnerColumn(),
            TextColumn(f"[cyan]Navigating {result['url']}..."),
            TimeElapsedColumn(),
            console=console,
            transient=True,
        ) as progress:
            progress.add_task("", total=None)
            time.sleep(result["load_time_ms"] / 3000)

        console.print(
            f"  [green]✓[/green] [bold]{result['title']}[/bold]\n"
            f"     Status: [green]{result['status_code']}[/green] • "
            f"Load: [yellow]{result['load_time_ms']}ms[/yellow] • "
            f"Links: [cyan]{result['links']}[/cyan] • "
            f"Words: [blue]{result['word_count']:,}[/blue]"
        )
    console.print()


def demo_price_extraction() -> None:
    """Demo: Price extraction from e-commerce sites."""
    console.rule("[bold cyan]3. E-Commerce Price Extraction[/bold cyan]")
    console.print()

    table = Table(box=box.ROUNDED, border_style="yellow", show_header=True)
    table.add_column("Product", style="white", width=32)
    table.add_column("Current", style="bold green", justify="right", width=10)
    table.add_column("Was", style="dim red", justify="right", width=10)
    table.add_column("Discount", style="bold yellow", justify="right", width=10)
    table.add_column("Stock", style="cyan", justify="center", width=8)
    table.add_column("ASIN", style="dim", width=12)

    for product in DEMO_PRICES:
        with Progress(
            SpinnerColumn(),
            TextColumn(f"[yellow]Extracting {product['url'][:40]}..."),
            console=console,
            transient=True,
        ) as progress:
            progress.add_task("", total=None)
            time.sleep(0.5)

        stock_icon = "[green]✓[/green]" if product["in_stock"] else "[red]✗[/red]"
        table.add_row(
            product["product"][:30],
            f"${product['current_price']:.2f}",
            f"${product['original_price']:.2f}",
            f"{product['discount']:.1f}%",
            stock_icon,
            product["asin"] or "N/A",
        )

    console.print(table)
    console.print()


def demo_article_extraction() -> None:
    """Demo: Article content extraction."""
    console.rule("[bold cyan]4. Article Content Extraction[/bold cyan]")
    console.print()

    with Progress(
        SpinnerColumn(),
        TextColumn(f"[cyan]Extracting {DEMO_ARTICLE['url'][:50]}..."),
        console=console,
        transient=True,
    ) as progress:
        progress.add_task("", total=None)
        time.sleep(0.7)

    console.print(Panel(
        f"[bold white]{DEMO_ARTICLE['title']}[/bold white]\n\n"
        f"[dim]By [cyan]{DEMO_ARTICLE['author']}[/cyan] • "
        f"{DEMO_ARTICLE['site_name']} • "
        f"{DEMO_ARTICLE['published_date'][:10]}[/dim]\n\n"
        f"{DEMO_ARTICLE['summary']}\n\n"
        f"[green]Word count:[/green] {DEMO_ARTICLE['word_count']:,}  "
        f"[green]Images:[/green] {len(DEMO_ARTICLE['images'])}",
        title="[cyan]Article Extracted[/cyan]",
        border_style="cyan",
    ))
    console.print()


def demo_task_queue() -> None:
    """Demo: Task queue status."""
    console.rule("[bold cyan]5. Async Task Queue[/bold cyan]")
    console.print()
    console.print("[dim]Concurrent tasks: 3 • Max retries: 3 • Backoff: exponential[/dim]\n")

    status_colors = {
        "done": "green",
        "running": "yellow",
        "pending": "blue",
        "failed": "red",
        "retrying": "magenta",
    }
    status_icons = {
        "done": "✓",
        "running": "⟳",
        "pending": "○",
        "failed": "✗",
        "retrying": "↺",
    }

    table = Table(box=box.ROUNDED, border_style="blue", show_header=True)
    table.add_column("Task ID", style="dim", width=10)
    table.add_column("Type", style="white", width=10)
    table.add_column("URL", width=30)
    table.add_column("Status", width=10)
    table.add_column("Duration", justify="right", width=10)

    for task in DEMO_QUEUE:
        color = status_colors.get(task["status"], "white")
        icon = status_icons.get(task["status"], "?")
        duration = f"{task['ms']}ms" if task["ms"] else "—"
        table.add_row(
            task["task_id"],
            task["type"],
            task["url"],
            f"[{color}]{icon} {task['status']}[/{color}]",
            duration,
        )

    console.print(table)
    console.print()


def demo_api_endpoints() -> None:
    """Demo: API endpoint overview."""
    console.rule("[bold cyan]6. REST API Endpoints[/bold cyan]")
    console.print()

    table = Table(box=box.SIMPLE, show_header=True, border_style="dim")
    table.add_column("Method", style="bold cyan", width=8)
    table.add_column("Endpoint", style="white", width=22)
    table.add_column("Description", style="dim white")

    endpoints = [
        ("POST", "/browse", "Navigate to URL, return content + screenshot"),
        ("POST", "/scrape", "Extract fields using CSS selectors"),
        ("POST", "/extract/price", "Extract product price (Amazon, eBay, generic)"),
        ("POST", "/extract/article", "Extract article title, author, content"),
        ("POST", "/screenshot", "Capture full-page PNG screenshot"),
        ("GET",  "/jobs", "List all task queue jobs"),
        ("GET",  "/jobs/{id}", "Get specific job status + result"),
        ("GET",  "/health", "Service health check"),
    ]

    for method, endpoint, desc in endpoints:
        color = "green" if method == "GET" else "yellow"
        table.add_row(f"[{color}]{method}[/{color}]", endpoint, desc)

    console.print(table)
    console.print(
        f"  API docs: [link=http://localhost:8001/docs][cyan]http://localhost:8001/docs[/cyan][/link]\n"
    )


def demo_summary() -> None:
    """Final summary panel."""
    console.rule("[bold cyan]PHANTOM — Summary[/bold cyan]")
    console.print()

    console.print(Panel(
        "[bold white]PHANTOM is ready for production deployment.[/bold white]\n\n"
        "  [cyan]•[/cyan] 3 stealth layers active (fingerprint + humanizer + evasion)\n"
        "  [cyan]•[/cyan] Async Playwright with per-task context isolation\n"
        "  [cyan]•[/cyan] Priority queue with exponential backoff retry\n"
        "  [cyan]•[/cyan] Price, article, and structured data extractors\n"
        "  [cyan]•[/cyan] Redis cache with in-memory fallback\n"
        "  [cyan]•[/cyan] 8-tool Hermes skill integration ready\n\n"
        "[dim]Start the API:[/dim]\n"
        "  [green]pip install -r requirements.txt && playwright install chromium[/green]\n"
        "  [green]uvicorn phantom.api.main:app --port 8001[/green]",
        title="[bold cyan]◈ PHANTOM v0.1.0[/bold cyan]",
        border_style="cyan",
        padding=(1, 2),
    ))


def main() -> None:
    """Run the full PHANTOM demo sequence."""
    demo_header()
    time.sleep(0.3)

    demo_fingerprints()
    time.sleep(0.2)

    demo_browse()
    time.sleep(0.2)

    demo_price_extraction()
    time.sleep(0.2)

    demo_article_extraction()
    time.sleep(0.2)

    demo_task_queue()
    time.sleep(0.2)

    demo_api_endpoints()
    time.sleep(0.2)

    demo_summary()


if __name__ == "__main__":
    main()
