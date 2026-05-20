"""Integration tests for model_capabilities table — round-trip CRUD via SqLiteDataApi."""

import sqlite3
from pathlib import Path

from ollama_llm_bench.backend.services.model_capability_service import ModelCapabilityService
from ollama_llm_bench.backend.services.sq_lite_data_api import SqLiteDataApi

# ---------------------------------------------------------------------------
# SqLiteDataApi — raw capability CRUD
# ---------------------------------------------------------------------------


def test_model_capabilities_table_is_created(data_api: SqLiteDataApi, tmp_path: Path) -> None:
    """model_capabilities table must exist after SqLiteDataApi initialisation."""
    db_path = tmp_path / "test.db"
    SqLiteDataApi(db_path)

    conn = sqlite3.connect(db_path)
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    conn.close()

    assert "model_capabilities" in tables


def test_get_model_capability_returns_none_when_no_row(data_api: SqLiteDataApi) -> None:
    result = data_api.get_model_capability("ollama", "gemma3:1b", "thinking")

    assert result is None


def test_set_and_get_model_capability_unsupported(data_api: SqLiteDataApi) -> None:
    data_api.set_model_capability(
        "ollama",
        "gemma3:1b",
        "thinking",
        supported=False,
        observed_via="warm_up_400",
    )

    result = data_api.get_model_capability("ollama", "gemma3:1b", "thinking")

    assert result == 0


def test_set_and_get_model_capability_supported(data_api: SqLiteDataApi) -> None:
    data_api.set_model_capability(
        "ollama",
        "qwen3:8b",
        "thinking",
        supported=True,
        observed_via="warm_up_success",
    )

    result = data_api.get_model_capability("ollama", "qwen3:8b", "thinking")

    assert result == 1


def test_upsert_overwrites_previous_value(data_api: SqLiteDataApi) -> None:
    data_api.set_model_capability(
        "ollama",
        "gemma3:1b",
        "thinking",
        supported=False,
        observed_via="warm_up_400",
    )

    data_api.set_model_capability(
        "ollama",
        "gemma3:1b",
        "thinking",
        supported=True,
        observed_via="warm_up_success",
    )

    result = data_api.get_model_capability("ollama", "gemma3:1b", "thinking")

    assert result == 1


def test_capability_rows_are_isolated_by_provider(data_api: SqLiteDataApi) -> None:
    data_api.set_model_capability(
        "provider_a",
        "model:1b",
        "thinking",
        supported=True,
        observed_via="test",
    )
    data_api.set_model_capability(
        "provider_b",
        "model:1b",
        "thinking",
        supported=False,
        observed_via="test",
    )

    assert data_api.get_model_capability("provider_a", "model:1b", "thinking") == 1
    assert data_api.get_model_capability("provider_b", "model:1b", "thinking") == 0


def test_capability_rows_are_isolated_by_capability_key(data_api: SqLiteDataApi) -> None:
    data_api.set_model_capability(
        "ollama",
        "model:7b",
        "thinking",
        supported=False,
        observed_via="test",
    )

    assert data_api.get_model_capability("ollama", "model:7b", "context_length") is None


def test_detail_field_is_persisted(data_api: SqLiteDataApi, tmp_path: Path) -> None:
    db_path = tmp_path / "detail.db"
    api = SqLiteDataApi(db_path)
    detail_msg = "Error code: 400 — model does not support thinking"

    api.set_model_capability(
        "ollama",
        "gemma3:1b",
        "thinking",
        supported=False,
        observed_via="warm_up_400",
        detail=detail_msg,
    )

    conn = sqlite3.connect(db_path)
    row = conn.execute(
        "SELECT detail FROM model_capabilities WHERE provider_id=? AND model_name=? AND capability=?",
        ("ollama", "gemma3:1b", "thinking"),
    ).fetchone()
    conn.close()

    assert row is not None
    assert row[0] == detail_msg


# ---------------------------------------------------------------------------
# ModelCapabilityService — Protocol layer
# ---------------------------------------------------------------------------


def test_service_supports_thinking_returns_none_when_no_row(data_api: SqLiteDataApi) -> None:
    service = ModelCapabilityService(data_api=data_api)

    result = service.supports_thinking("ollama", "gemma3:1b")

    assert result is None


def test_service_supports_thinking_returns_false_after_remember_unsupported(data_api: SqLiteDataApi) -> None:
    service = ModelCapabilityService(data_api=data_api)

    service.remember(
        "ollama",
        "gemma3:1b",
        "thinking",
        supported=False,
        observed_via="warm_up_400",
    )

    assert service.supports_thinking("ollama", "gemma3:1b") is False


def test_service_supports_thinking_returns_true_after_upsert_to_supported(data_api: SqLiteDataApi) -> None:
    service = ModelCapabilityService(data_api=data_api)

    service.remember("ollama", "gemma3:1b", "thinking", supported=False, observed_via="warm_up_400")
    service.remember("ollama", "gemma3:1b", "thinking", supported=True, observed_via="warm_up_success")

    assert service.supports_thinking("ollama", "gemma3:1b") is True


def test_service_get_returns_none_for_unknown_capability(data_api: SqLiteDataApi) -> None:
    service = ModelCapabilityService(data_api=data_api)

    result = service.get("ollama", "gemma3:1b", "context_length")

    assert result is None
