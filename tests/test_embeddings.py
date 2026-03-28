from app.services.embeddings import (
    build_product_embedding,
    cosine_similarity,
    embed_text,
)


def test_embedding_generation_is_deterministic() -> None:
    assert embed_text("Northbeam wireless monitor") == embed_text("  northbeam wireless monitor  ")


def test_related_texts_score_closer_than_unrelated_texts() -> None:
    product_embedding = build_product_embedding(
        title="Northbeam Wireless Monitor with HDR",
        description="Built for hybrid work and everyday productivity.",
        category_name="Electronics",
        brand_name="Northbeam",
        attributes={"connectivity": "usb-c", "color": "black"},
    )
    related_query = embed_text("wireless monitor for hybrid work")
    unrelated_query = embed_text("plush pet bed for apartment cats")

    assert cosine_similarity(product_embedding, related_query) > cosine_similarity(
        product_embedding,
        unrelated_query,
    )
