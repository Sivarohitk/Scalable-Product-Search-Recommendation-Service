from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


def test_alembic_head_revision_matches_catalog_schema() -> None:
    config = Config("alembic.ini")
    script = ScriptDirectory.from_config(config)

    assert script.get_current_head() == "20260327_0001"
    revision = script.get_revision("20260327_0001")
    assert revision is not None
    assert revision.path is not None

    contents = Path(revision.path).read_text(encoding="utf-8")
    assert "CREATE EXTENSION IF NOT EXISTS vector" in contents
    assert "CREATE EXTENSION IF NOT EXISTS pg_trgm" in contents
    assert "search_document" in contents
    assert "product_cooccurrence" in contents

