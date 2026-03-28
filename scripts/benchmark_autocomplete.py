from __future__ import annotations

import argparse

from benchmark_common import print_summary, run_get_benchmark, write_summary_json


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Benchmark autocomplete latency.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--query", default="north")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--warmup", type=int, default=5)
    parser.add_argument("--iterations", type=int, default=25)
    parser.add_argument("--output-json")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    summary = run_get_benchmark(
        name="Autocomplete",
        base_url=args.base_url,
        path="/autocomplete",
        params={"query": args.query, "limit": args.limit},
        warmup=args.warmup,
        iterations=args.iterations,
    )
    write_summary_json(args.output_json, summary)
    print_summary(summary, details=f"query={args.query!r} limit={args.limit}")


if __name__ == "__main__":
    main()
