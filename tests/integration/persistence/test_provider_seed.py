"""Integration tests for the built-in provider seed.

Exercises the real ``seed_builtin_providers`` public surface of
``backend/persistence/providers/`` against a real ``tmp_path`` SQLite database file,
never ``:memory:``, per ``testing.md``'s integration-tier rule.

Source of truth: STORY-012 acceptance criterion AC-5.
"""

from pathlib import Path
import uuid

from ollama_llm_bench.backend.infra.protocols import Clock
from ollama_llm_bench.backend.persistence.app_settings import ensure_schema, open_write_connection
from ollama_llm_bench.backend.persistence.providers import seed_builtin_providers

_EXPECTED_BUILTIN_PROVIDER_COUNT = 3
_UUID_VERSION_4 = 4


def test_seed_writes_three_builtin_providers_in_one_transaction(
    db_path: Path, clock: Clock
) -> None:
    """Proves: STORY-012-AC-5

    Given an empty database, when the provider seed runs, then exactly three
    provider_type = 'openai_compatible' providers exist -- named Ollama, LM
    Studio, and llama.cpp -- each enabled = 1 with no API key, with
    provider_order 0, 1, and 2 respectively and a distinct UUID4 provider_id,
    written in one transaction.
    """
    # Arrange
    write_conn, lock = open_write_connection(db_path)
    ensure_schema(write_conn, lock, clock=clock)
    rows_before = write_conn.execute("SELECT COUNT(*) FROM providers").fetchone()[0]
    assert rows_before == 0

    # Act
    seed_builtin_providers(write_conn, lock)

    # Assert -- exactly three rows, ordered by provider_order.
    rows = write_conn.execute(
        "SELECT provider_id, name, provider_type, enabled, api_key_raw, provider_order "
        "FROM providers ORDER BY provider_order"
    ).fetchall()
    assert len(rows) == _EXPECTED_BUILTIN_PROVIDER_COUNT

    expected_names = ("Ollama (local)", "LM Studio (local)", "llama.cpp (local)")
    seen_ids: set[str] = set()
    for order, (row, expected_name) in enumerate(zip(rows, expected_names, strict=True)):
        provider_id, name, provider_type, enabled, api_key_raw, provider_order = row
        assert name == expected_name
        assert provider_type == "openai_compatible"
        assert enabled == 1
        assert api_key_raw is None
        assert provider_order == order
        parsed = uuid.UUID(provider_id)
        assert parsed.version == _UUID_VERSION_4
        seen_ids.add(provider_id)

    # Assert -- every provider_id is distinct.
    assert len(seen_ids) == _EXPECTED_BUILTIN_PROVIDER_COUNT

    write_conn.close()
