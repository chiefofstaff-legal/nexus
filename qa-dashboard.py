#!/usr/bin/env python3
"""
NEXUS QA Dashboard — TUI monitor for backend requests, LLM costs, and latency.

Usage:
    cd ~/nexus-poc && source backend/venv/bin/activate && python3 qa-dashboard.py
    python3 qa-dashboard.py --benchmark  # Run upload benchmark (local vs tunnel)
"""

import os
import sys

# Auto-activate backend venv if rich isn't available
_venv = os.path.join(os.path.dirname(__file__), "backend", "venv")
if os.path.isdir(_venv) and _venv not in sys.prefix:
    _sp = os.path.join(_venv, "lib", f"python{sys.version_info.major}.{sys.version_info.minor}", "site-packages")
    if os.path.isdir(_sp):
        sys.path.insert(0, _sp)

import json
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

DATA_DIR = Path(__file__).parent / "data"
TELEMETRY_LOG = DATA_DIR / "telemetry.jsonl"
ROUTING_AUDIT = DATA_DIR / "audit" / "routing-audit.jsonl"
DOC_AUDIT = DATA_DIR / "audit" / "audit.jsonl"
BACKEND_LOG = Path("/tmp/nexus-backend.log")

console = Console()


def read_jsonl(path: Path, max_lines: int = 500) -> list[dict]:
    """Read last N lines from a JSONL file."""
    if not path.exists():
        return []
    lines = path.read_text().strip().split("\n")
    result = []
    for line in lines[-max_lines:]:
        try:
            result.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return result


def read_log_tail(path: Path, lines: int = 20) -> list[str]:
    """Read last N lines from a log file."""
    if not path.exists():
        return []
    all_lines = path.read_text().strip().split("\n")
    return all_lines[-lines:]


def build_request_table(entries: list[dict]) -> Table:
    """Build recent requests table from telemetry."""
    table = Table(title="Recent Requests", expand=True, border_style="dim")
    table.add_column("Time", style="dim", width=8)
    table.add_column("Method", width=6)
    table.add_column("Path", style="cyan", ratio=2)
    table.add_column("Status", width=6, justify="right")
    table.add_column("Ms", width=8, justify="right")
    table.add_column("Source", width=7)

    for entry in entries[-15:]:
        ts = entry.get("ts", "")
        time_str = ts[11:19] if len(ts) > 19 else ts
        ms = entry.get("ms", 0)
        status = entry.get("status", 0)
        source = entry.get("source", "?")

        ms_style = "green" if ms < 100 else "yellow" if ms < 1000 else "red"
        status_style = "green" if 200 <= status < 300 else "yellow" if 300 <= status < 400 else "red"
        source_style = "blue" if source == "tunnel" else "dim"

        table.add_row(
            time_str,
            entry.get("method", "?"),
            entry.get("path", "?")[:40],
            Text(str(status), style=status_style),
            Text(f"{ms:.0f}", style=ms_style),
            Text(source, style=source_style),
        )

    return table


def build_llm_panel(routing_entries: list[dict]) -> Panel:
    """Build LLM routing costs and latency panel."""
    table = Table(expand=True, border_style="dim")
    table.add_column("Time", style="dim", width=8)
    table.add_column("Model", style="cyan", width=20)
    table.add_column("Provider", width=9)
    table.add_column("Sensitivity", width=13)
    table.add_column("Latency", width=8, justify="right")
    table.add_column("Cost", width=10, justify="right")
    table.add_column("PII", width=15)

    total_cost = 0.0
    for entry in routing_entries[-10:]:
        ts = entry.get("timestamp", "")
        time_str = ts[11:19] if len(ts) > 19 else ts
        latency = entry.get("latency_ms", 0)
        cost = entry.get("cost_usd", 0)
        total_cost += cost
        sens = entry.get("sensitivity_level", "?")
        pii = ", ".join(entry.get("pii_types", [])[:2])

        sens_style = "red" if sens == "confidential" else "yellow" if sens == "internal" else "green"
        provider = entry.get("provider", "?")
        provider_style = "green" if provider == "ollama" else "cyan" if provider == "groq" else "magenta"
        cost_str = f"${cost:.4f}" if cost > 0 else "FREE"
        cost_style = "green" if cost == 0 else "yellow"

        table.add_row(
            time_str,
            entry.get("model", "?"),
            Text(provider, style=provider_style),
            Text(sens, style=sens_style),
            f"{latency:.0f}ms",
            Text(cost_str, style=cost_style),
            pii[:15] if pii else "-",
        )

    total_queries = len(routing_entries)
    free_queries = sum(1 for e in routing_entries if e.get("cost_usd", 0) == 0)

    return Panel(
        table,
        title=f"LLM Routing | {total_queries} queries | {free_queries} free | Total: ${total_cost:.4f}",
        border_style="magenta",
    )


def build_docs_panel(doc_entries: list[dict]) -> Panel:
    """Build document processing panel."""
    table = Table(expand=True, border_style="dim")
    table.add_column("File", style="cyan", ratio=2)
    table.add_column("Type", width=15)
    table.add_column("Conf.", width=6, justify="right")
    table.add_column("Chunks", width=7, justify="right")

    for entry in doc_entries[-8:]:
        conf = entry.get("confidence", 0)
        conf_style = "green" if conf >= 0.9 else "yellow" if conf >= 0.7 else "red"
        table.add_row(
            entry.get("filename", "?")[:30],
            entry.get("type", "?"),
            Text(f"{conf:.0%}", style=conf_style),
            str(entry.get("chunks_indexed", 0)),
        )

    return Panel(
        table,
        title=f"Documents Processed ({len(doc_entries)} total)",
        border_style="cyan",
    )


def build_latency_panel(telemetry: list[dict]) -> Panel:
    """Build latency comparison panel: local vs tunnel."""
    local_times = [e["ms"] for e in telemetry if e.get("source") == "local" and e.get("method") != "OPTIONS"]
    tunnel_times = [e["ms"] for e in telemetry if e.get("source") == "tunnel" and e.get("method") != "OPTIONS"]

    lines = []

    def stats_line(label: str, times: list[float]) -> str:
        if not times:
            return f"  {label}: no data"
        avg = sum(times) / len(times)
        p50 = sorted(times)[len(times) // 2]
        p95 = sorted(times)[int(len(times) * 0.95)] if len(times) >= 5 else max(times)
        return f"  {label}: avg {avg:.0f}ms | p50 {p50:.0f}ms | p95 {p95:.0f}ms | n={len(times)}"

    lines.append(stats_line("Local  (V>>)", local_times))
    lines.append(stats_line("Tunnel (Craig)", tunnel_times))

    if local_times and tunnel_times:
        overhead = (sum(tunnel_times) / len(tunnel_times)) - (sum(local_times) / len(local_times))
        lines.append(f"\n  Tunnel overhead: +{overhead:.0f}ms avg")

    # Upload estimate
    upload_times = [e["ms"] for e in telemetry if "/upload" in e.get("path", "")]
    if upload_times:
        avg_upload = sum(upload_times) / len(upload_times)
        est_100_local = avg_upload * 100 / 1000 / 60
        lines.append(f"\n  Avg upload: {avg_upload:.0f}ms/doc")
        lines.append(f"  Est. 100 docs (local): {est_100_local:.1f} min")
        if tunnel_times:
            ratio = (sum(tunnel_times) / len(tunnel_times)) / (sum(local_times) / len(local_times)) if local_times else 2.0
            est_100_tunnel = est_100_local * ratio
            lines.append(f"  Est. 100 docs (Zurich): {est_100_tunnel:.1f} min")

    return Panel(
        "\n".join(lines) if lines else "  Waiting for data...",
        title="Latency: V>> (local) vs Craig (Zurich)",
        border_style="yellow",
    )


def build_log_panel() -> Panel:
    """Build backend log tail panel."""
    lines = read_log_tail(BACKEND_LOG, 8)
    filtered = [l for l in lines if "INFO:" in l or "ERROR:" in l or "WARNING:" in l]
    text = "\n".join(filtered[-6:]) if filtered else "No recent log entries"
    return Panel(text, title="Backend Log", border_style="dim")


def build_provider_panel(routing_entries: list[dict]) -> Panel:
    """Provider breakdown with cost summary."""
    by_provider = defaultdict(lambda: {"count": 0, "cost": 0.0, "latency": []})

    for entry in routing_entries:
        p = entry.get("provider", "unknown")
        by_provider[p]["count"] += 1
        by_provider[p]["cost"] += entry.get("cost_usd", 0)
        by_provider[p]["latency"].append(entry.get("latency_ms", 0))

    table = Table(expand=True, border_style="dim")
    table.add_column("Provider", width=12)
    table.add_column("Queries", width=8, justify="right")
    table.add_column("Avg Latency", width=12, justify="right")
    table.add_column("Total Cost", width=12, justify="right")

    for provider in ["groq", "ollama", "anthropic"]:
        data = by_provider.get(provider, {"count": 0, "cost": 0.0, "latency": []})
        avg_lat = sum(data["latency"]) / len(data["latency"]) if data["latency"] else 0
        cost_str = f"${data['cost']:.4f}" if data["cost"] > 0 else "FREE"
        style = "green" if provider == "ollama" else "cyan" if provider == "groq" else "magenta"
        table.add_row(
            Text(provider, style=style),
            str(data["count"]),
            f"{avg_lat:.0f}ms",
            Text(cost_str, style="green" if data["cost"] == 0 else "yellow"),
        )

    return Panel(table, title="Provider Cost Breakdown", border_style="green")


def make_layout() -> Layout:
    """Build the dashboard layout."""
    layout = Layout()
    layout.split_column(
        Layout(name="header", size=3),
        Layout(name="body"),
        Layout(name="footer", size=10),
    )
    layout["body"].split_row(
        Layout(name="left", ratio=3),
        Layout(name="right", ratio=2),
    )
    layout["left"].split_column(
        Layout(name="requests"),
        Layout(name="llm"),
    )
    layout["right"].split_column(
        Layout(name="latency"),
        Layout(name="providers"),
        Layout(name="docs"),
    )
    return layout


def render_dashboard() -> Layout:
    """Render one frame of the dashboard."""
    telemetry = read_jsonl(TELEMETRY_LOG)
    routing = read_jsonl(ROUTING_AUDIT)
    docs = read_jsonl(DOC_AUDIT)

    layout = make_layout()

    now = datetime.now(timezone.utc).strftime("%H:%M:%S")
    header = Text(f" NEXUS QA Dashboard | {now} UTC | telemetry: {len(telemetry)} | routing: {len(routing)} | docs: {len(docs)}", style="bold white on dark_blue")
    layout["header"].update(Panel(header, border_style="blue"))

    layout["requests"].update(build_request_table(telemetry))
    layout["llm"].update(build_llm_panel(routing))
    layout["latency"].update(build_latency_panel(telemetry))
    layout["providers"].update(build_provider_panel(routing))
    layout["docs"].update(build_docs_panel(docs))
    layout["footer"].update(build_log_panel())

    return layout


def _get_auth_cookie(base_url: str) -> str | None:
    """Authenticate against tunnel via curl (bypasses Cloudflare bot challenge)."""
    import subprocess

    pw = (Path(__file__).parent / "frontend" / ".env.local").read_text()
    pw_val = ""
    for line in pw.strip().split("\n"):
        if line.startswith("NEXUS_DEMO_"):
            pw_val = line.split("=", 1)[1]
            break
    if not pw_val:
        return None

    result = subprocess.run(
        ["curl", "-sf", "-X", "POST", f"{base_url}/api/auth/login",
         "-H", "Content-Type: application/json",
         "-d", json.dumps({"password": pw_val}),
         "-c", "-"],
        capture_output=True, text=True, timeout=15,
    )
    for line in result.stdout.split("\n"):
        if "nexus-demo-auth" in line:
            parts = line.split()
            return f"nexus-demo-auth={parts[-1]}" if parts else None
    return None


def _upload_file(base_url: str, filepath: Path, cookie: str | None = None) -> float:
    """Upload a single file via curl and return elapsed ms. Raises on failure."""
    import subprocess

    cmd = [
        "curl", "-sf", "-o", "/dev/null", "-w", "%{time_total}",
        "-X", "POST", f"{base_url}/api/documents/upload",
        "-F", f"file=@{filepath}",
    ]
    if cookie:
        cmd.extend(["-b", cookie])

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        raise RuntimeError(f"HTTP error (curl exit {result.returncode})")

    return float(result.stdout.strip()) * 1000


def _bench_endpoint(label: str, base_url: str, test_files: list[Path]) -> None:
    """Benchmark uploads against one endpoint and print results."""
    console.print(f"[bold cyan]{label}[/bold cyan]: {base_url}")

    cookie = None
    if "grip-web.com" in base_url or "trycloudflare" in base_url:
        console.print("  Authenticating...")
        cookie = _get_auth_cookie(base_url)

    times = []

    for f in test_files:
        try:
            elapsed = _upload_file(base_url, f, cookie)
            times.append(elapsed)
            console.print(f"  {f.name}: {elapsed:.0f}ms")
        except Exception as e:
            console.print(f"  [red]{f.name}: {e}[/red]")

    if times:
        avg = sum(times) / len(times)
        est_100 = avg * 100 / 1000 / 60
        console.print(f"\n  [green]Avg: {avg:.0f}ms | Total: {sum(times):.0f}ms | Est 100 docs: {est_100:.1f} min[/green]\n")


def run_benchmark():
    """Run upload benchmark: local vs tunnel."""
    console.print("\n[bold]NEXUS Upload Benchmark[/bold]\n")

    test_files = list((Path(__file__).parent / "test_corpus").glob("*"))
    if not test_files:
        console.print("[red]No test files found in test_corpus/[/red]")
        return

    console.print(f"Test corpus: {len(test_files)} files\n")

    _bench_endpoint("Local (V>>)", "http://localhost:8100", test_files)
    _bench_endpoint("Tunnel (Craig)", "https://try.grip-web.com", test_files)


def main():
    if "--benchmark" in sys.argv:
        run_benchmark()
        return

    console.print("[bold]Starting NEXUS QA Dashboard...[/bold] (Ctrl+C to exit)\n")

    with Live(render_dashboard(), refresh_per_second=2, console=console) as live:
        while True:
            time.sleep(0.5)
            live.update(render_dashboard())


if __name__ == "__main__":
    main()
