from __future__ import annotations

import json
import statistics
from dataclasses import asdict, dataclass
from pathlib import Path
from time import perf_counter

import httpx


@dataclass(frozen=True, slots=True)
class BenchmarkSummary:
    name: str
    path: str
    warmup: int
    iterations: int
    mean_ms: float
    p50_ms: float
    p95_ms: float
    max_ms: float
    status_code: int


def percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]

    ordered = sorted(values)
    index = (len(ordered) - 1) * fraction
    lower = int(index)
    upper = min(lower + 1, len(ordered) - 1)
    weight = index - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def run_get_benchmark(
    *,
    name: str,
    base_url: str,
    path: str,
    params: dict[str, object],
    warmup: int,
    iterations: int,
) -> BenchmarkSummary:
    latencies_ms: list[float] = []
    last_status_code = 0

    with httpx.Client(base_url=base_url.rstrip("/"), timeout=10.0) as client:
        for _ in range(warmup):
            response = client.get(path, params=params)
            response.raise_for_status()

        for _ in range(iterations):
            started_at = perf_counter()
            response = client.get(path, params=params)
            response.raise_for_status()
            latencies_ms.append((perf_counter() - started_at) * 1000)
            last_status_code = response.status_code

    return BenchmarkSummary(
        name=name,
        path=path,
        warmup=warmup,
        iterations=iterations,
        mean_ms=statistics.fmean(latencies_ms) if latencies_ms else 0.0,
        p50_ms=percentile(latencies_ms, 0.50),
        p95_ms=percentile(latencies_ms, 0.95),
        max_ms=max(latencies_ms, default=0.0),
        status_code=last_status_code,
    )


def write_summary_json(path: str | None, summary: BenchmarkSummary) -> None:
    if path is None:
        return
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(asdict(summary), indent=2) + "\n", encoding="utf-8")


def print_summary(summary: BenchmarkSummary, *, details: str) -> None:
    print(
        f"{summary.name} benchmark:"
        f" {details}"
        f" warmup={summary.warmup}"
        f" iterations={summary.iterations}"
        f" status_code={summary.status_code}"
        f" mean_ms={summary.mean_ms:.2f}"
        f" p50_ms={summary.p50_ms:.2f}"
        f" p95_ms={summary.p95_ms:.2f}"
        f" max_ms={summary.max_ms:.2f}"
    )
