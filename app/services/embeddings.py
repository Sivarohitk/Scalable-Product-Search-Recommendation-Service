from __future__ import annotations

import math
import re
from collections.abc import Sequence
from hashlib import sha256
from typing import Any

EMBEDDING_DIMENSIONS = 16
_WHITESPACE_PATTERN = re.compile(r"\s+")
_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")


def normalize_embedding_text(text: str) -> str:
    return _WHITESPACE_PATTERN.sub(" ", text.strip()).casefold()


def tokenize_embedding_text(text: str) -> list[str]:
    tokens = _TOKEN_PATTERN.findall(normalize_embedding_text(text))
    return tokens or ["empty"]


def compose_product_embedding_text(
    *,
    title: str,
    description: str,
    category_name: str,
    brand_name: str,
    attributes: dict[str, Any] | None = None,
) -> str:
    parts = [
        brand_name,
        category_name,
        title,
        title,
        description,
        _attributes_embedding_text(attributes),
    ]
    return " ".join(part for part in parts if part)


def build_product_embedding(
    *,
    title: str,
    description: str,
    category_name: str,
    brand_name: str,
    attributes: dict[str, Any] | None = None,
    dimensions: int = EMBEDDING_DIMENSIONS,
) -> list[float]:
    return embed_text(
        compose_product_embedding_text(
            title=title,
            description=description,
            category_name=category_name,
            brand_name=brand_name,
            attributes=attributes,
        ),
        dimensions=dimensions,
    )


def embed_text(text: str, *, dimensions: int = EMBEDDING_DIMENSIONS) -> list[float]:
    vector = [0.0] * dimensions
    for feature, weight in _feature_weights(tokenize_embedding_text(text)):
        for index in range(dimensions):
            vector[index] += weight * _signed_hash(f"{feature}:{index}")

    magnitude = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [round(value / magnitude, 6) for value in vector]


def vector_literal(values: Sequence[float]) -> str:
    return "[" + ",".join(f"{value:.6f}" for value in values) + "]"


def cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    numerator = sum(
        left_value * right_value
        for left_value, right_value in zip(left, right, strict=False)
    )
    left_magnitude = math.sqrt(sum(value * value for value in left)) or 1.0
    right_magnitude = math.sqrt(sum(value * value for value in right)) or 1.0
    return numerator / (left_magnitude * right_magnitude)


def _feature_weights(tokens: list[str]) -> list[tuple[str, float]]:
    features: list[tuple[str, float]] = []
    for token in tokens:
        features.append((f"tok:{token}", 1.0))
        if len(token) >= 4:
            features.append((f"pref:{token[:4]}", 0.2))

    for index in range(len(tokens) - 1):
        features.append((f"bg:{tokens[index]}_{tokens[index + 1]}", 0.35))

    return features


def _attributes_embedding_text(attributes: dict[str, Any] | None) -> str:
    if not attributes:
        return ""

    parts: list[str] = []
    for key in sorted(attributes):
        value = attributes[key]
        parts.append(f"{key} {_attribute_value_text(value)}")
    return " ".join(parts)


def _attribute_value_text(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, tuple, set)):
        return " ".join(_attribute_value_text(item) for item in value)
    return str(value)


def _signed_hash(text: str) -> float:
    digest = sha256(text.encode("utf-8")).digest()
    value = int.from_bytes(digest[:8], byteorder="big", signed=False)
    return ((value / float(2**64 - 1)) * 2.0) - 1.0
