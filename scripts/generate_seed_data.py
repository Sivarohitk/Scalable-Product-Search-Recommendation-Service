from __future__ import annotations

import argparse
from pathlib import Path

from app.services.seed import (
    DEFAULT_INTERACTION_COUNT,
    DEFAULT_PRODUCT_COUNT,
    SeedConfig,
    generate_seed_bundle,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate deterministic synthetic catalog seed data."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data") / "generated" / "default",
        help="Directory to write manifest, products, and interactions into.",
    )
    parser.add_argument(
        "--product-count",
        type=int,
        default=DEFAULT_PRODUCT_COUNT,
        help="Number of products to generate.",
    )
    parser.add_argument(
        "--interaction-count",
        type=int,
        default=DEFAULT_INTERACTION_COUNT,
        help="Number of interactions to generate.",
    )
    parser.add_argument("--seed", type=int, default=17, help="Deterministic random seed.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    manifest = generate_seed_bundle(
        SeedConfig(
            output_dir=args.output_dir,
            product_count=args.product_count,
            interaction_count=args.interaction_count,
            seed=args.seed,
        )
    )
    print(
        "Generated seed bundle:",
        f"dir={args.output_dir}",
        f"products={manifest.product_count}",
        f"interactions={manifest.interaction_count}",
        f"seed={manifest.seed}",
    )


if __name__ == "__main__":
    main()
