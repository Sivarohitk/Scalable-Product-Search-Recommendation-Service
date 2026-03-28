from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from random import Random
from typing import Any

from app.services.embeddings import EMBEDDING_DIMENSIONS, build_product_embedding

REFERENCE_TIMESTAMP = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
DEFAULT_PRODUCT_COUNT = 50_000
DEFAULT_INTERACTION_COUNT = 250_000


@dataclass(frozen=True, slots=True)
class CategoryBlueprint:
    id: int
    slug: str
    name: str
    product_types: tuple[str, ...]
    descriptors: tuple[str, ...]
    features: tuple[str, ...]
    use_cases: tuple[str, ...]
    price_range: tuple[float, float]
    attribute_options: dict[str, tuple[Any, ...]]


@dataclass(frozen=True, slots=True)
class BrandBlueprint:
    id: int
    slug: str
    name: str
    category_slugs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ProductReference:
    id: int
    sku: str
    category_id: int
    category_slug: str
    brand_id: int
    brand_slug: str
    popularity_score: float


@dataclass(frozen=True, slots=True)
class SeedConfig:
    output_dir: Path
    product_count: int = DEFAULT_PRODUCT_COUNT
    interaction_count: int = DEFAULT_INTERACTION_COUNT
    seed: int = 17


@dataclass(frozen=True, slots=True)
class SeedManifest:
    seed: int
    product_count: int
    interaction_count: int
    embedding_dimensions: int
    reference_timestamp: str
    files: dict[str, str]


CATEGORY_BLUEPRINTS: tuple[CategoryBlueprint, ...] = (
    CategoryBlueprint(
        id=1,
        slug="electronics",
        name="Electronics",
        product_types=("Headphones", "Monitor", "Speaker", "Keyboard", "Camera", "Router"),
        descriptors=("Wireless", "Smart", "Premium", "Compact", "Studio", "Ultra"),
        features=(
            "with Spatial Audio",
            "with USB-C",
            "for Hybrid Work",
            "with HDR",
            "with Fast Charge",
        ),
        use_cases=("commuting", "hybrid work", "gaming", "content creation", "travel"),
        price_range=(39.0, 1499.0),
        attribute_options={
            "color": ("black", "silver", "white", "navy"),
            "connectivity": ("bluetooth", "wifi-6", "usb-c", "wired"),
            "warranty_years": (1, 2, 3),
        },
    ),
    CategoryBlueprint(
        id=2,
        slug="home-office",
        name="Home Office",
        product_types=("Desk", "Office Chair", "Lamp", "Docking Station", "Bookshelf", "Footrest"),
        descriptors=("Ergonomic", "Adjustable", "Minimal", "Modular", "Quiet", "Standing"),
        features=("for Small Spaces", "with Cable Routing", "for Long Sessions", "with Soft Light"),
        use_cases=("remote work", "study sessions", "compact apartments", "shared workspaces"),
        price_range=(29.0, 999.0),
        attribute_options={
            "finish": ("walnut", "matte black", "oak", "white"),
            "material": ("steel", "bamboo", "engineered wood", "mesh"),
            "assembly_level": ("easy", "moderate"),
        },
    ),
    CategoryBlueprint(
        id=3,
        slug="kitchen",
        name="Kitchen",
        product_types=(
            "Blender",
            "Air Fryer",
            "Chef Knife",
            "Coffee Maker",
            "Mixer",
            "Cookware Set",
        ),
        descriptors=("Professional", "Countertop", "Quick-Heat", "Precision", "Family", "Everyday"),
        features=(
            "for Meal Prep",
            "with Timer Presets",
            "with Stainless Finish",
            "for Busy Mornings",
        ),
        use_cases=("meal prep", "weeknight dinners", "small kitchens", "batch cooking"),
        price_range=(19.0, 699.0),
        attribute_options={
            "capacity": ("1.5L", "4qt", "6qt", "12-cup", "16-piece"),
            "dishwasher_safe": (True, False),
            "power_source": ("electric", "manual"),
        },
    ),
    CategoryBlueprint(
        id=4,
        slug="outdoors",
        name="Outdoors",
        product_types=("Tent", "Cooler", "Lantern", "Backpack", "Sleeping Pad", "Camp Chair"),
        descriptors=(
            "Trail-Ready",
            "Weatherproof",
            "Packable",
            "Rugged",
            "Expedition",
            "All-Season",
        ),
        features=("for Weekend Trips", "with Thermal Lining", "for Fast Setup", "with Light Frame"),
        use_cases=("camping", "road trips", "festival weekends", "hiking"),
        price_range=(24.0, 899.0),
        attribute_options={
            "capacity": ("2-person", "4-person", "20L", "40L", "55L"),
            "weather_rating": ("light rain", "3-season", "all-season"),
            "color": ("forest", "sand", "charcoal", "copper"),
        },
    ),
    CategoryBlueprint(
        id=5,
        slug="fitness",
        name="Fitness",
        product_types=(
            "Dumbbell Set",
            "Yoga Mat",
            "Exercise Bike",
            "Resistance Band",
            "Rowing Machine",
        ),
        descriptors=("Performance", "Recovery", "Compact", "Pro", "Studio", "Cardio"),
        features=("for Daily Training", "with Quiet Drive", "for Home Gyms", "with Grip Texture"),
        use_cases=("strength training", "mobility work", "cardio sessions", "recovery days"),
        price_range=(14.0, 1699.0),
        attribute_options={
            "resistance_level": ("light", "medium", "heavy", "adjustable"),
            "material": ("rubber", "foam", "steel", "tpe"),
            "foldable": (True, False),
        },
    ),
    CategoryBlueprint(
        id=6,
        slug="beauty",
        name="Beauty",
        product_types=("Hair Dryer", "Skin Serum", "Makeup Brush Set", "Facial Cleanser", "Mirror"),
        descriptors=("Hydrating", "Radiance", "Salon", "Daily", "Gentle", "Glow"),
        features=(
            "for Sensitive Skin",
            "with Ionic Control",
            "for Everyday Use",
            "with LED Lighting",
        ),
        use_cases=("morning routines", "travel kits", "professional styling", "night care"),
        price_range=(9.0, 399.0),
        attribute_options={
            "skin_type": ("all", "dry", "sensitive", "combination"),
            "size": ("30ml", "50ml", "standard", "travel"),
            "finish": ("matte", "natural", "dewy"),
        },
    ),
    CategoryBlueprint(
        id=7,
        slug="pet-supplies",
        name="Pet Supplies",
        product_types=("Pet Bed", "Feeder", "Leash", "Cat Tree", "Treat Container"),
        descriptors=("Comfort", "Durable", "Smart", "Washable", "Travel", "Indoor"),
        features=(
            "for Multi-Pet Homes",
            "with Slow Feed Design",
            "for Daily Walks",
            "with Storage",
        ),
        use_cases=("daily care", "apartment living", "travel days", "training"),
        price_range=(12.0, 329.0),
        attribute_options={
            "pet_size": ("small", "medium", "large"),
            "material": ("canvas", "plush", "steel", "silicone"),
            "color": ("sage", "charcoal", "blue", "rose"),
        },
    ),
    CategoryBlueprint(
        id=8,
        slug="toys",
        name="Toys",
        product_types=("Building Set", "Puzzle", "Plush Toy", "STEM Kit", "Board Game"),
        descriptors=("Creative", "Learning", "Adventure", "Collector", "Junior", "Family"),
        features=("for Weekend Play", "with Storage Case", "for Ages 6+", "for Group Play"),
        use_cases=("family nights", "creative play", "gifting", "classroom fun"),
        price_range=(8.0, 249.0),
        attribute_options={
            "age_range": ("3-5", "6-8", "9-12", "13+"),
            "pieces": ("24", "60", "120", "320"),
            "material": ("wood", "fabric", "plastic", "mixed"),
        },
    ),
    CategoryBlueprint(
        id=9,
        slug="apparel",
        name="Apparel",
        product_types=("Jacket", "T-Shirt", "Hoodie", "Pants", "Dress", "Base Layer"),
        descriptors=("Lightweight", "Classic", "Stretch", "Performance", "Relaxed", "Weatherproof"),
        features=("for Layering", "with Moisture Control", "for Everyday Wear", "with Soft Finish"),
        use_cases=("commutes", "travel", "weekend errands", "training"),
        price_range=(15.0, 299.0),
        attribute_options={
            "size": ("xs", "s", "m", "l", "xl"),
            "fabric": ("cotton", "merino", "recycled blend", "nylon"),
            "color": ("black", "sand", "olive", "stone", "blue"),
        },
    ),
    CategoryBlueprint(
        id=10,
        slug="footwear",
        name="Footwear",
        product_types=("Running Shoe", "Boot", "Sandal", "Sneaker", "Slip-On"),
        descriptors=("Cushioned", "Trail", "Breathable", "Waterproof", "Minimal", "All-Day"),
        features=("for Long Walks", "with Grip Sole", "for Warm Weather", "with Arch Support"),
        use_cases=("daily wear", "trail days", "travel", "gym sessions"),
        price_range=(24.0, 249.0),
        attribute_options={
            "size": ("7", "8", "9", "10", "11", "12"),
            "upper_material": ("mesh", "leather", "canvas", "knit"),
            "color": ("white", "black", "clay", "sand", "navy"),
        },
    ),
)

BRAND_BLUEPRINTS: tuple[BrandBlueprint, ...] = (
    BrandBlueprint(1, "northbeam", "Northbeam", ("electronics", "outdoors", "fitness")),
    BrandBlueprint(2, "cinderlane", "Cinderlane", ("home-office", "apparel", "footwear")),
    BrandBlueprint(3, "oak-and-iron", "Oak & Iron", ("home-office", "kitchen")),
    BrandBlueprint(4, "trueform", "TrueForm", ("fitness", "beauty", "apparel")),
    BrandBlueprint(5, "blueharbor", "BlueHarbor", ("outdoors", "pet-supplies", "toys")),
    BrandBlueprint(6, "lumena", "Lumena", ("beauty", "electronics", "home-office")),
    BrandBlueprint(7, "kindledrop", "KindleDrop", ("kitchen", "home-office")),
    BrandBlueprint(8, "trailgrid", "TrailGrid", ("outdoors", "footwear", "fitness")),
    BrandBlueprint(9, "meadowcraft", "MeadowCraft", ("pet-supplies", "toys", "home-office")),
    BrandBlueprint(10, "driftline", "Driftline", ("apparel", "footwear", "outdoors")),
    BrandBlueprint(11, "vertex-labs", "Vertex Labs", ("electronics", "fitness")),
    BrandBlueprint(12, "goldfinch", "Goldfinch", ("beauty", "apparel", "toys")),
    BrandBlueprint(13, "harvest-table", "Harvest Table", ("kitchen",)),
    BrandBlueprint(14, "station-six", "Station Six", ("home-office", "electronics")),
    BrandBlueprint(15, "palisade", "Palisade", ("outdoors", "pet-supplies")),
    BrandBlueprint(16, "daybreak", "Daybreak", ("beauty", "home-office", "apparel")),
    BrandBlueprint(17, "atlas-run", "Atlas Run", ("fitness", "footwear", "apparel")),
    BrandBlueprint(18, "littlecomet", "Little Comet", ("toys", "beauty")),
)


def generate_seed_bundle(config: SeedConfig) -> SeedManifest:
    config.output_dir.mkdir(parents=True, exist_ok=True)
    rng = Random(config.seed)

    categories = [_category_record(item) for item in CATEGORY_BLUEPRINTS]
    brands = [_brand_record(item) for item in BRAND_BLUEPRINTS]

    _write_json(config.output_dir / "categories.json", categories)
    _write_json(config.output_dir / "brands.json", brands)

    product_refs = _write_products(config.output_dir / "products.jsonl", config.product_count, rng)
    _write_interactions(
        config.output_dir / "interactions.jsonl",
        product_refs,
        config.interaction_count,
        rng,
    )

    manifest = SeedManifest(
        seed=config.seed,
        product_count=config.product_count,
        interaction_count=config.interaction_count,
        embedding_dimensions=EMBEDDING_DIMENSIONS,
        reference_timestamp=REFERENCE_TIMESTAMP.isoformat(),
        files={
            "categories": "categories.json",
            "brands": "brands.json",
            "products": "products.jsonl",
            "interactions": "interactions.jsonl",
        },
    )
    _write_json(config.output_dir / "manifest.json", asdict(manifest))
    return manifest


def _write_products(output_path: Path, product_count: int, rng: Random) -> list[ProductReference]:
    product_refs: list[ProductReference] = []
    with output_path.open("w", encoding="utf-8", newline="\n") as handle:
        for product_id in range(1, product_count + 1):
            category = rng.choice(CATEGORY_BLUEPRINTS)
            brand = _select_brand(category.slug, rng)
            descriptor = rng.choice(category.descriptors)
            product_type = rng.choice(category.product_types)
            feature = rng.choice(category.features)
            use_case = rng.choice(category.use_cases)
            title = f"{brand.name} {descriptor} {product_type} {feature}"
            description = (
                f"{title} is built for {use_case}. "
                f"It is part of the {category.name.lower()} assortment and balances durability, "
                f"ease of setup, and reliable day-to-day performance."
            )
            price = round(rng.uniform(*category.price_range), 2)
            inventory_count = max(0, int(rng.triangular(0, 400, 120)))
            rating = round(min(4.9, max(2.7, rng.gauss(4.1, 0.45))), 2)
            popularity_score = round(max(1.0, rng.lognormvariate(2.3, 0.35)), 4)
            created_at = _random_timestamp(rng, 720)
            updated_at = min(
                REFERENCE_TIMESTAMP,
                created_at + timedelta(days=rng.randint(0, 120), hours=rng.randint(0, 23)),
            )
            attributes = _build_attributes(category, rng)
            sku = f"{category.slug[:3].upper()}-{brand.slug[:3].upper()}-{product_id:06d}"

            record = {
                "id": product_id,
                "sku": sku,
                "title": title,
                "description": description,
                "category_id": category.id,
                "category_slug": category.slug,
                "brand_id": brand.id,
                "brand_slug": brand.slug,
                "price": f"{price:.2f}",
                "currency": "USD",
                "inventory_count": inventory_count,
                "rating": f"{rating:.2f}",
                "popularity_score": f"{popularity_score:.4f}",
                "attributes": attributes,
                "embedding": build_product_embedding(
                    title=title,
                    description=description,
                    category_name=category.name,
                    brand_name=brand.name,
                    attributes=attributes,
                    dimensions=EMBEDDING_DIMENSIONS,
                ),
                "created_at": created_at.isoformat(),
                "updated_at": updated_at.isoformat(),
            }
            handle.write(json.dumps(record, sort_keys=True) + "\n")
            product_refs.append(
                ProductReference(
                    id=product_id,
                    sku=sku,
                    category_id=category.id,
                    category_slug=category.slug,
                    brand_id=brand.id,
                    brand_slug=brand.slug,
                    popularity_score=popularity_score,
                )
            )
    return product_refs


def _write_interactions(
    output_path: Path,
    product_refs: list[ProductReference],
    interaction_count: int,
    rng: Random,
) -> None:
    by_category: dict[str, list[ProductReference]] = {}
    by_brand: dict[str, list[ProductReference]] = {}
    for reference in product_refs:
        by_category.setdefault(reference.category_slug, []).append(reference)
        by_brand.setdefault(reference.brand_slug, []).append(reference)
    bundle_catalog = _build_purchase_bundles(by_category)

    interactions_written = 0
    session_number = 0

    with output_path.open("w", encoding="utf-8", newline="\n") as handle:
        while interactions_written < interaction_count:
            session_number += 1
            user_id = f"user-{rng.randint(1, max(10, interaction_count // 4)):06d}"
            session_id = f"session-{session_number:08d}"
            session_started_at = _random_timestamp(rng, 180)
            primary_product = rng.choice(product_refs)
            primary_pool = by_category[primary_product.category_slug]
            session_products = [primary_product]

            purchase_bundle: tuple[ProductReference, ...] | None = None
            for _ in range(rng.randint(1, 4)):
                if rng.random() < 0.65:
                    candidate_pool = primary_pool
                else:
                    candidate_pool = by_brand.get(primary_product.brand_slug, primary_pool)
                candidate = rng.choice(candidate_pool)
                if candidate.id not in {item.id for item in session_products}:
                    session_products.append(candidate)

            order_id: str | None = None
            purchased_products: set[int] = set()
            if rng.random() < 0.18:
                order_id = f"order-{session_number:08d}"
                purchase_bundle = rng.choice(bundle_catalog[primary_product.category_slug])
                session_products = _deduplicate_products(
                    [*purchase_bundle, primary_product, *session_products]
                )
                purchased_products.update(product.id for product in purchase_bundle)

            for index, product in enumerate(session_products):
                occurred_at = session_started_at + timedelta(minutes=index * rng.randint(1, 4))
                view_event = {
                    "user_token": user_id,
                    "session_id": session_id,
                    "order_id": None,
                    "product_id": product.id,
                    "interaction_type": "view",
                    "quantity": 1,
                    "context": {
                        "channel": rng.choice(("search", "category_page", "email", "homepage")),
                        "device": rng.choice(("mobile", "desktop", "tablet")),
                    },
                    "occurred_at": occurred_at.isoformat(),
                }
                handle.write(json.dumps(view_event, sort_keys=True) + "\n")
                interactions_written += 1
                if interactions_written >= interaction_count:
                    break

                if product.id in purchased_products:
                    purchase_event = {
                        "user_token": user_id,
                        "session_id": session_id,
                        "order_id": order_id,
                        "product_id": product.id,
                        "interaction_type": "purchase",
                        "quantity": rng.choice((1, 1, 1, 2)),
                        "context": {
                            "payment_method": rng.choice(("card", "wallet", "paypal")),
                            "promotion_applied": rng.choice((True, False)),
                        },
                        "occurred_at": (occurred_at + timedelta(minutes=5)).isoformat(),
                    }
                    handle.write(json.dumps(purchase_event, sort_keys=True) + "\n")
                    interactions_written += 1
                    if interactions_written >= interaction_count:
                        break


def _build_purchase_bundles(
    by_category: dict[str, list[ProductReference]]
) -> dict[str, list[tuple[ProductReference, ...]]]:
    bundles: dict[str, list[tuple[ProductReference, ...]]] = {}
    for category_slug, references in by_category.items():
        sorted_references = sorted(references, key=lambda item: item.id)
        category_bundles: list[tuple[ProductReference, ...]] = []
        for offset in range(0, min(len(sorted_references), 40), 2):
            pair = tuple(sorted_references[offset : offset + 2])
            if len(pair) == 2:
                category_bundles.append(pair)
        bundles[category_slug] = category_bundles or [tuple(sorted_references[:2])]
    return bundles


def _deduplicate_products(items: list[ProductReference]) -> list[ProductReference]:
    deduplicated: list[ProductReference] = []
    seen_ids: set[int] = set()
    for item in items:
        if item.id not in seen_ids:
            deduplicated.append(item)
            seen_ids.add(item.id)
    return deduplicated


def _category_record(blueprint: CategoryBlueprint) -> dict[str, Any]:
    return {
        "id": blueprint.id,
        "slug": blueprint.slug,
        "name": blueprint.name,
        "created_at": REFERENCE_TIMESTAMP.isoformat(),
        "updated_at": REFERENCE_TIMESTAMP.isoformat(),
    }


def _brand_record(blueprint: BrandBlueprint) -> dict[str, Any]:
    return {
        "id": blueprint.id,
        "slug": blueprint.slug,
        "name": blueprint.name,
        "created_at": REFERENCE_TIMESTAMP.isoformat(),
        "updated_at": REFERENCE_TIMESTAMP.isoformat(),
    }


def _select_brand(category_slug: str, rng: Random) -> BrandBlueprint:
    eligible = [brand for brand in BRAND_BLUEPRINTS if category_slug in brand.category_slugs]
    return rng.choice(eligible or list(BRAND_BLUEPRINTS))


def _build_attributes(category: CategoryBlueprint, rng: Random) -> dict[str, Any]:
    attributes: dict[str, Any] = {}
    for key, values in category.attribute_options.items():
        attributes[key] = rng.choice(values)
    attributes["release_cycle"] = rng.choice(("core", "seasonal", "limited"))
    attributes["eco_packaging"] = rng.choice((True, False))
    return attributes


def _random_timestamp(rng: Random, max_days_back: int) -> datetime:
    return REFERENCE_TIMESTAMP - timedelta(
        days=rng.randint(0, max_days_back),
        hours=rng.randint(0, 23),
        minutes=rng.randint(0, 59),
        seconds=rng.randint(0, 59),
    )


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
