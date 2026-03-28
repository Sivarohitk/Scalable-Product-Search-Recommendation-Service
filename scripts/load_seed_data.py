from __future__ import annotations

import argparse
from pathlib import Path

from app.core.config import get_settings
from app.services.ingestion import load_seed_bundle


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Load a generated seed bundle into PostgreSQL.")
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=Path("data") / "generated" / "default",
        help="Directory containing manifest, product, and interaction files.",
    )
    parser.add_argument(
        "--database-url",
        type=str,
        default=get_settings().database_url,
        help="Application database URL. Async URLs are converted automatically for sync loading.",
    )
    parser.add_argument(
        "--append",
        action="store_true",
        help="Append to existing data instead of truncating first.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    summary = load_seed_bundle(
        bundle_dir=args.input_dir,
        database_url=args.database_url,
        replace_existing=not args.append,
    )
    print(
        "Loaded seed bundle:",
        f"categories={summary.categories_loaded}",
        f"brands={summary.brands_loaded}",
        f"products={summary.products_loaded}",
        f"interactions={summary.interactions_loaded}",
    )


if __name__ == "__main__":
    main()

