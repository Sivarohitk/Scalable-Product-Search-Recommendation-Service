from __future__ import annotations

import argparse

from app.core.config import get_settings
from app.services.ingestion import build_derived_artifacts


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build vector, full-text, and recommendation artifacts."
    )
    parser.add_argument(
        "--database-url",
        type=str,
        default=get_settings().database_url,
        help="Application database URL. Async URLs are converted automatically for sync loading.",
    )
    parser.add_argument(
        "--min-cooccurrence-count",
        type=int,
        default=2,
        help="Minimum supporting interactions needed before a co-occurrence edge is stored.",
    )
    parser.add_argument(
        "--embedding-batch-size",
        type=int,
        default=1_000,
        help="Number of product embeddings to refresh per SQL batch during artifact rebuilds.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    summary = build_derived_artifacts(
        database_url=args.database_url,
        min_cooccurrence_count=args.min_cooccurrence_count,
        embedding_batch_size=args.embedding_batch_size,
    )
    print(
        "Built derived artifacts:",
        f"embeddings_refreshed={summary.embeddings_refreshed}",
        f"products_indexed={summary.products_indexed}",
        f"co_view_edges={summary.co_view_edges}",
        f"co_purchase_edges={summary.co_purchase_edges}",
    )


if __name__ == "__main__":
    main()
