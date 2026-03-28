from pathlib import Path

from app.services.ingestion import inspect_seed_bundle
from app.services.seed import SeedConfig, generate_seed_bundle


def test_seed_generation_is_deterministic_for_the_same_seed(tmp_path: Path) -> None:
    bundle_one = tmp_path / "bundle-one"
    bundle_two = tmp_path / "bundle-two"

    manifest_one = generate_seed_bundle(
        SeedConfig(output_dir=bundle_one, product_count=40, interaction_count=120, seed=101)
    )
    manifest_two = generate_seed_bundle(
        SeedConfig(output_dir=bundle_two, product_count=40, interaction_count=120, seed=101)
    )

    assert manifest_one == manifest_two
    assert (bundle_one / "products.jsonl").read_text(encoding="utf-8") == (
        bundle_two / "products.jsonl"
    ).read_text(encoding="utf-8")
    assert (bundle_one / "interactions.jsonl").read_text(encoding="utf-8") == (
        bundle_two / "interactions.jsonl"
    ).read_text(encoding="utf-8")


def test_seed_bundle_manifest_and_record_counts_align(tmp_path: Path) -> None:
    bundle_dir = tmp_path / "bundle"
    manifest = generate_seed_bundle(
        SeedConfig(output_dir=bundle_dir, product_count=25, interaction_count=80, seed=7)
    )
    summary = inspect_seed_bundle(bundle_dir)

    assert manifest.product_count == 25
    assert manifest.interaction_count == 80
    assert summary.product_count == 25
    assert summary.interaction_count == 80
    assert summary.category_count >= 8
    assert summary.brand_count >= 12

