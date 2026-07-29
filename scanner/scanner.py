#!/usr/bin/env python3
"""
scanner.py — Prompt-Injection & Jailbreak Scanner CLI

Fires known prompt-injection and jailbreak payloads at an LLM API endpoint,
judges whether each attack succeeded using Gemini as an LLM-as-judge,
and outputs a structured JSON report.

Usage:
    python scanner.py --target https://api.yourapp.com/v1/chat/completions \
                      --api-key sk-... \
                      --model gpt-3.5-turbo \
                      --output report.json \
                      --concurrency 5
"""

import argparse
import asyncio
import os
import sys
import time
from pathlib import Path

import yaml
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, MofNCompleteColumn
from rich.table import Table
from rich.text import Text
from rich import box

from runner import run_payloads
from judge import judge_results
from report import build_report

# Load .env file from the scanner directory
load_dotenv(Path(__file__).parent / ".env")


console = Console()


def load_payloads(payloads_path):
    """Load and validate the payloads YAML file."""
    path = Path(payloads_path)
    if not path.exists():
        console.print(f"[red]✗[/red] Payloads file not found: {payloads_path}")
        sys.exit(1)

    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not data or "payloads" not in data:
        console.print("[red]✗[/red] Invalid payloads file: missing 'payloads' key")
        sys.exit(1)

    payloads = data["payloads"]
    console.print(f"[green]✓[/green] Loaded [bold]{len(payloads)}[/bold] payloads from [cyan]{payloads_path}[/cyan]")
    return payloads


def print_banner():
    """Print the scanner banner."""
    banner_text = Text()
    banner_text.append("⚡ ", style="yellow bold")
    banner_text.append("Prompt-Injection & Jailbreak Scanner", style="bold white")
    banner_text.append(" ⚡", style="yellow bold")

    console.print()
    console.print(Panel(
        banner_text,
        subtitle="[dim]Offensive LLM Security Testing Tool[/dim]",
        border_style="bright_blue",
        padding=(1, 4),
    ))
    console.print()


def print_config(args, num_payloads):
    """Print the scan configuration."""
    table = Table(
        title="Scan Configuration",
        box=box.ROUNDED,
        border_style="dim",
        title_style="bold cyan",
    )
    table.add_column("Setting", style="cyan", no_wrap=True)
    table.add_column("Value", style="white")

    table.add_row("Target", args.target)
    table.add_row("Model", args.model)
    table.add_row("Payloads", f"{num_payloads} loaded")
    table.add_row("Concurrency", str(args.concurrency))
    table.add_row("Timeout", f"{args.timeout}s")
    table.add_row("Output", args.output)
    table.add_row("Judge Model", args.judge_model)

    if args.system_prompt:
        table.add_row("System Prompt", args.system_prompt[:80] + ("..." if len(args.system_prompt) > 80 else ""))

    console.print(table)
    console.print()


def print_summary(report):
    """Print the final scan summary."""
    summary = report["summary"]
    by_category = report["by_category"]

    console.print()

    # Overall summary
    total = summary["total"]
    passed = summary["passed_attacks"]
    blocked = summary["blocked"]
    errors = summary["errors"]
    rate = summary["attack_success_rate"]

    # Color the success rate based on severity
    if rate >= 50:
        rate_style = "bold red"
        severity = "CRITICAL"
        severity_style = "bold red"
    elif rate >= 25:
        rate_style = "bold yellow"
        severity = "HIGH"
        severity_style = "bold yellow"
    elif rate >= 10:
        rate_style = "bold bright_yellow"
        severity = "MEDIUM"
        severity_style = "bold bright_yellow"
    else:
        rate_style = "bold green"
        severity = "LOW"
        severity_style = "bold green"

    summary_table = Table(
        title="Scan Results Summary",
        box=box.HEAVY,
        border_style="bright_blue",
        title_style="bold white",
    )
    summary_table.add_column("Metric", style="cyan", no_wrap=True)
    summary_table.add_column("Value", justify="right")

    summary_table.add_row("Total Payloads", str(total))
    summary_table.add_row("Attacks Succeeded (PASS)", f"[red]{passed}[/red]")
    summary_table.add_row("Attacks Blocked (FAIL)", f"[green]{blocked}[/green]")
    summary_table.add_row("Errors", f"[yellow]{errors}[/yellow]")
    summary_table.add_row("Attack Success Rate", f"[{rate_style}]{rate}%[/{rate_style}]")
    summary_table.add_row("Risk Severity", f"[{severity_style}]{severity}[/{severity_style}]")
    summary_table.add_row("Avg Response Time", f"{summary['avg_response_time_ms']}ms")

    console.print(summary_table)
    console.print()

    # Per-category breakdown
    cat_table = Table(
        title="Results by Category",
        box=box.ROUNDED,
        border_style="dim",
        title_style="bold cyan",
    )
    cat_table.add_column("Category", style="white", no_wrap=True)
    cat_table.add_column("Total", justify="center")
    cat_table.add_column("Passed", justify="center", style="red")
    cat_table.add_column("Blocked", justify="center", style="green")
    cat_table.add_column("Errors", justify="center", style="yellow")
    cat_table.add_column("Success Rate", justify="center")

    for cat_name, cat_data in sorted(by_category.items()):
        cat_total = cat_data["total"]
        cat_passed = cat_data["passed"]
        cat_rate = round((cat_passed / cat_total) * 100, 1) if cat_total > 0 else 0

        if cat_rate >= 50:
            rate_str = f"[red]{cat_rate}%[/red]"
        elif cat_rate >= 25:
            rate_str = f"[yellow]{cat_rate}%[/yellow]"
        else:
            rate_str = f"[green]{cat_rate}%[/green]"

        cat_table.add_row(
            cat_name,
            str(cat_total),
            str(cat_passed),
            str(cat_data["blocked"]),
            str(cat_data["errors"]),
            rate_str,
        )

    console.print(cat_table)
    console.print()


async def main_async(args):
    """Main async entry point."""
    # Load payloads
    payloads = load_payloads(args.payloads)
    print_config(args, len(payloads))

    # Resolve API key
    api_key = args.api_key or os.environ.get("TARGET_API_KEY", "")
    if not api_key:
        console.print("[yellow]⚠[/yellow] No API key provided. Proceeding without authentication.")
        console.print("[dim]   Set via --api-key or TARGET_API_KEY env var[/dim]")
        console.print()

    # Check Gemini API key
    gemini_key = os.environ.get("GEMINI_API_KEY")
    if not gemini_key:
        console.print("[red]✗[/red] GEMINI_API_KEY environment variable is not set.")
        console.print("[dim]   Set it with: export GEMINI_API_KEY='your-key-here'[/dim]")
        sys.exit(1)

    # ── Phase 1: Run attacks ──
    console.print(Panel("[bold]Phase 1/2[/bold] — Firing payloads at target", border_style="yellow"))

    completed = 0
    attack_passed = 0
    attack_errors = 0

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(bar_width=40),
        MofNCompleteColumn(),
        TextColumn("│"),
        TextColumn("[dim]{task.fields[status]}[/dim]"),
        console=console,
    ) as progress:
        task = progress.add_task(
            "Attacking...",
            total=len(payloads),
            status="Starting...",
        )

        async def runner_progress(result):
            nonlocal completed, attack_errors
            completed += 1
            if result.get("error"):
                attack_errors += 1
            status = f"Errors: {attack_errors}"
            progress.update(task, advance=1, status=status)

        results = await run_payloads(
            target_url=args.target,
            api_key=api_key,
            model=args.model,
            payloads=payloads,
            system_prompt=args.system_prompt,
            concurrency=args.concurrency,
            timeout=args.timeout,
            progress_callback=runner_progress,
        )

    console.print(f"[green]✓[/green] All {len(results)} payloads fired.\n")

    # ── Phase 2: Judge responses ──
    console.print(Panel("[bold]Phase 2/2[/bold] — Judging responses with Gemini", border_style="yellow"))

    judge_completed = 0

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(bar_width=40),
        MofNCompleteColumn(),
        TextColumn("│"),
        TextColumn("[dim]{task.fields[status]}[/dim]"),
        console=console,
    ) as progress:
        task = progress.add_task(
            "Judging...",
            total=len(results),
            status="Starting...",
        )
        pass_count = 0
        fail_count = 0
        err_count = 0

        async def judge_progress(result):
            nonlocal judge_completed, pass_count, fail_count, err_count
            judge_completed += 1
            v = result.get("verdict", "ERROR")
            if v == "PASS":
                pass_count += 1
            elif v == "FAIL":
                fail_count += 1
            else:
                err_count += 1
            status = f"[red]PASS:{pass_count}[/red] [green]FAIL:{fail_count}[/green] [yellow]ERR:{err_count}[/yellow]"
            progress.update(task, advance=1, status=status)

        judged = await judge_results(
            results=results,
            judge_model=args.judge_model,
            progress_callback=judge_progress,
            delay=0.3,
        )

    console.print(f"[green]✓[/green] All {len(judged)} responses judged.\n")

    # ── Phase 3: Build report ──
    report = build_report(
        target_url=args.target,
        model=args.model,
        results=judged,
        output_path=args.output,
    )

    print_summary(report)

    console.print(f"[green]✓[/green] Report saved to [bold cyan]{args.output}[/bold cyan]")
    console.print(f"[dim]  Open viewer/report_viewer.html and load the report to visualize results.[/dim]")
    console.print()


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="scanner",
        description="⚡ Prompt-Injection & Jailbreak Scanner — Offensive LLM Security Testing Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scanner.py --target https://api.openai.com/v1/chat/completions \\
                    --api-key sk-... --model gpt-3.5-turbo

  python scanner.py --target http://localhost:8000/v1/chat/completions \\
                    --model my-local-model --concurrency 10

  python scanner.py --target https://api.yourapp.com/chat \\
                    --payloads custom_payloads.yaml \\
                    --output scan_results.json

Environment Variables:
  TARGET_URL        Target endpoint URL (alternative to --target)
  TARGET_API_KEY    API key for the target endpoint (alternative to --api-key)
  GEMINI_API_KEY    API key for the Gemini judge model (required)
        """,
    )

    parser.add_argument(
        "--target",
        default=os.environ.get("TARGET_URL"),
        help="Target API endpoint URL (or set TARGET_URL env var)",
    )
    parser.add_argument(
        "--api-key",
        default=None,
        help="API key for the target endpoint (or set TARGET_API_KEY env var)",
    )
    parser.add_argument(
        "--model",
        default="gpt-3.5-turbo",
        help="Model name to use at the target (default: gpt-3.5-turbo)",
    )
    parser.add_argument(
        "--payloads",
        default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "payloads.yaml"),
        help="Path to payloads YAML file (default: payloads.yaml in scanner directory)",
    )
    parser.add_argument(
        "--output",
        default="report.json",
        help="Output report file path (default: report.json)",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=5,
        help="Maximum concurrent requests (default: 5)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=30,
        help="Per-request timeout in seconds (default: 30)",
    )
    parser.add_argument(
        "--system-prompt",
        default=None,
        help="Optional system prompt to include in requests to the target",
    )
    parser.add_argument(
        "--judge-model",
        default="gemini-2.0-flash",
        help="Gemini model for judging responses (default: gemini-2.0-flash)",
    )

    args = parser.parse_args()

    if not args.target:
        parser.error("--target is required (or set TARGET_URL in .env / environment)")

    print_banner()

    start = time.time()

    try:
        asyncio.run(main_async(args))
    except KeyboardInterrupt:
        console.print("\n[yellow]⚠ Scan interrupted by user.[/yellow]")
        sys.exit(130)
    except Exception as e:
        console.print(f"\n[red]✗ Fatal error: {e}[/red]")
        sys.exit(1)

    elapsed = time.time() - start
    console.print(f"[dim]Completed in {elapsed:.1f}s[/dim]\n")


if __name__ == "__main__":
    main()
