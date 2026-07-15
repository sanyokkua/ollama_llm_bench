"""Proves: STORY-038-AC-3 — provider-config condition severity (06_IMPORT_FORMATS.md §6.3)."""

from collections.abc import Mapping
from pathlib import Path

import pytest

from ollama_llm_bench.backend.errors import ConfigurationError
from ollama_llm_bench.backend.import_export.models import ImportFindingSeverity, ImportPreviewGroup
from ollama_llm_bench.backend.import_export.tests.conftest import (
    FakeProvidersStore,
    make_provider_config,
    make_service,
    write_yaml_mapping,
)

_GOOD_ENTRY = {
    "name": "control_provider",
    "type": "openai_compatible",
    "base_url": "http://localhost:11434/v1",
    "api_key": "",
    "enabled": True,
}


def _document(
    *entries: Mapping[str, object], embedding_provider: str = "control_provider"
) -> dict[str, object]:
    return {
        "kind": "provider_config",
        "schema_version": 1,
        "embedding": {"provider_name": embedding_provider, "model_name": "m"},
        "providers": list(entries),
    }


@pytest.mark.parametrize(
    ("bad_entry", "expected_item_key"),
    [
        (
            {"type": "openai_compatible", "base_url": "http://x", "api_key": ""},
            None,
        ),
        (
            {"name": "bad", "base_url": "http://x", "api_key": ""},
            "bad",
        ),
        (
            {"name": "bad", "type": "not_a_real_type", "base_url": "http://x", "api_key": ""},
            "bad",
        ),
        (
            {"name": "bad", "type": "openai_compatible", "api_key": ""},
            "bad",
        ),
        (
            {
                "name": "bad",
                "type": "openai_compatible",
                "base_url": "not a url",
                "api_key": "",
            },
            "bad",
        ),
        (
            {
                "name": "bad",
                "type": "anthropic",
                "base_url": "ftp://example.com",
                "api_key": "",
            },
            "bad",
        ),
    ],
    ids=[
        "missing_name",
        "missing_type",
        "type_not_one_of_the_three_allowed",
        "openai_compatible_missing_base_url",
        "base_url_not_syntactically_valid",
        "base_url_wrong_scheme",
    ],
)
def test_provider_condition_severity(
    tmp_path: Path, bad_entry: dict[str, object], expected_item_key: str | None
) -> None:
    """Proves: STORY-038-AC-3

    Each item-scoped hard-error condition drops only the offending entry; the
    rest of the file still imports — covers EC-IMP-6.
    """
    file_path = write_yaml_mapping(tmp_path, _document(bad_entry, _GOOD_ENTRY))
    service = make_service()

    preview = service.build_provider_import_preview(file_path)

    hard_errors = [
        finding
        for finding in preview.findings
        if finding.severity is ImportFindingSeverity.HARD_ERROR
    ]
    assert any(finding.item_key == expected_item_key for finding in hard_errors)
    assert "control_provider" in {
        item.name for item in preview.items if item.group is ImportPreviewGroup.ADDED
    }


def test_dropping_the_last_entry_aborts_the_whole_import(tmp_path: Path) -> None:
    """Proves: STORY-038-AC-3

    When an item-scoped hard error drops the only entry in the file, the
    whole import is aborted (not just that entry).
    """
    bad_entry = {"type": "openai_compatible", "base_url": "http://x", "api_key": ""}
    file_path = write_yaml_mapping(tmp_path, _document(bad_entry))
    service = make_service()

    with pytest.raises(ConfigurationError):
        service.build_provider_import_preview(file_path)


def test_duplicate_name_in_file_aborts_whole_import(tmp_path: Path) -> None:
    """Proves: STORY-038-AC-3

    Two entries sharing a ``name`` within the file is a file-scoped hard
    error — covers EC-IMP-7.
    """
    dup_a = {**_GOOD_ENTRY, "name": "dup"}
    dup_b = {**_GOOD_ENTRY, "name": "dup"}
    file_path = write_yaml_mapping(tmp_path, _document(dup_a, dup_b, embedding_provider="dup"))
    service = make_service()

    with pytest.raises(ConfigurationError):
        service.build_provider_import_preview(file_path)


def test_embedding_provider_name_mismatch_aborts_whole_import(tmp_path: Path) -> None:
    """Proves: STORY-038-AC-3

    ``embedding.provider_name`` matching no surviving entry is a file-scoped
    hard error — covers EC-IMP-8.
    """
    file_path = write_yaml_mapping(
        tmp_path, _document(_GOOD_ENTRY, embedding_provider="does_not_exist")
    )
    service = make_service()

    with pytest.raises(ConfigurationError):
        service.build_provider_import_preview(file_path)


def test_existing_name_collision_is_soft_warning_and_excluded(tmp_path: Path) -> None:
    """Proves: STORY-038-AC-3

    An entry whose ``name`` already exists in ``ProvidersStore`` is a soft
    warning; that entry is skipped and the rest of the import proceeds —
    covers EC-IMP-13.
    """
    colliding_entry = {**_GOOD_ENTRY, "name": "existing_provider"}
    fresh_entry = {**_GOOD_ENTRY, "name": "fresh_provider"}
    file_path = write_yaml_mapping(
        tmp_path, _document(colliding_entry, fresh_entry, embedding_provider="fresh_provider")
    )
    providers_store = FakeProvidersStore(
        providers=(make_provider_config(name="existing_provider"),)
    )
    service = make_service(providers_store=providers_store)

    preview = service.build_provider_import_preview(file_path)

    soft_warnings = [
        finding
        for finding in preview.findings
        if finding.severity is ImportFindingSeverity.SOFT_WARNING
        and finding.item_key == "existing_provider"
    ]
    assert soft_warnings and "Duplicate name" in soft_warnings[0].reason
    collided_item = next(item for item in preview.items if item.name == "existing_provider")
    assert collided_item.group is ImportPreviewGroup.SKIPPED
    assert collided_item.draft is None


def test_retired_id_field_is_soft_info_and_entry_still_added(tmp_path: Path) -> None:
    """Proves: STORY-038-AC-3

    An ``id:`` field present on an entry is a soft-info, listed-skipped
    finding; the entry itself is otherwise imported normally.
    """
    entry_with_id = {**_GOOD_ENTRY, "name": "with_id", "id": "old-provider-id"}
    file_path = write_yaml_mapping(tmp_path, _document(entry_with_id, embedding_provider="with_id"))
    service = make_service()

    preview = service.build_provider_import_preview(file_path)

    soft_info = [
        finding
        for finding in preview.findings
        if finding.severity is ImportFindingSeverity.SOFT_INFO and finding.item_key == "with_id"
    ]
    assert soft_info and "retired" in soft_info[0].reason.lower()
    with_id_item = next(item for item in preview.items if item.name == "with_id")
    assert with_id_item.group is ImportPreviewGroup.ADDED
    assert with_id_item.draft is not None


def test_env_var_name_unset_is_soft_warning_and_imported_as_is(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Proves: STORY-038-AC-3

    An ``api_key`` naming a currently-unset environment variable is a soft
    warning; the name is still imported as-is — covers EC-IMP-10.
    """
    env_var_name = "OLLAMA_LLM_BENCH_TEST_UNSET_ENV_VAR"
    monkeypatch.delenv(env_var_name, raising=False)
    entry = {**_GOOD_ENTRY, "name": "unset_env_provider", "api_key": env_var_name}
    file_path = write_yaml_mapping(
        tmp_path, _document(entry, embedding_provider="unset_env_provider")
    )
    service = make_service()

    preview = service.build_provider_import_preview(file_path)

    soft_warnings = [
        finding
        for finding in preview.findings
        if finding.severity is ImportFindingSeverity.SOFT_WARNING
        and finding.item_key == "unset_env_provider"
    ]
    assert soft_warnings and env_var_name in soft_warnings[0].reason
    item = next(item for item in preview.items if item.name == "unset_env_provider")
    assert item.group is ImportPreviewGroup.ADDED
    assert item.draft is not None
    assert item.draft.api_key_raw == env_var_name


def test_env_var_name_currently_set_has_no_finding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Proves: STORY-038-AC-3

    An ``api_key`` naming a currently-*set* environment variable produces no
    finding at all for that entry.
    """
    env_var_name = "OLLAMA_LLM_BENCH_TEST_SET_ENV_VAR"
    monkeypatch.setenv(env_var_name, "irrelevant-value")
    entry = {**_GOOD_ENTRY, "name": "set_env_provider", "api_key": env_var_name}
    file_path = write_yaml_mapping(
        tmp_path, _document(entry, embedding_provider="set_env_provider")
    )
    service = make_service()

    preview = service.build_provider_import_preview(file_path)

    assert not any(finding.item_key == "set_env_provider" for finding in preview.findings)


def test_api_key_field_omitted_is_treated_as_keyless(tmp_path: Path) -> None:
    """Proves: STORY-038-AC-3

    An entry with no ``api_key`` field at all is valid — equivalent to a
    keyless local provider, not a literal-secret hard error.
    """
    entry = {key: value for key, value in _GOOD_ENTRY.items() if key != "api_key"}
    entry["name"] = "keyless_provider"
    file_path = write_yaml_mapping(
        tmp_path, _document(entry, embedding_provider="keyless_provider")
    )
    service = make_service()

    preview = service.build_provider_import_preview(file_path)

    item = next(item for item in preview.items if item.name == "keyless_provider")
    assert item.group is ImportPreviewGroup.ADDED
    assert item.draft is not None
    assert item.draft.api_key_raw is None


def test_api_key_non_string_value_is_hard_error(tmp_path: Path) -> None:
    """Proves: STORY-038-AC-3

    A non-string ``api_key`` value is neither empty nor a syntactically valid
    env-var name, so it hard-errors the same as a literal secret.
    """
    entry = {**_GOOD_ENTRY, "name": "bad_api_key_type", "api_key": 12345}
    file_path = write_yaml_mapping(tmp_path, _document(entry, _GOOD_ENTRY))
    service = make_service()

    preview = service.build_provider_import_preview(file_path)

    assert any(
        finding.severity is ImportFindingSeverity.HARD_ERROR
        and finding.item_key == "bad_api_key_type"
        for finding in preview.findings
    )


def test_non_dict_provider_entry_is_hard_error(tmp_path: Path) -> None:
    """Proves: STORY-038-AC-3

    A ``providers`` sequence entry that is not a mapping at all is a hard
    error for that entry (no usable ``name`` to key a preview row on).
    """
    document: dict[str, object] = {
        "kind": "provider_config",
        "schema_version": 1,
        "embedding": {"provider_name": "control_provider", "model_name": "m"},
        "providers": [_GOOD_ENTRY, "not_a_mapping"],
    }
    file_path = write_yaml_mapping(tmp_path, document)
    service = make_service()

    preview = service.build_provider_import_preview(file_path)

    assert any(
        finding.severity is ImportFindingSeverity.HARD_ERROR
        and finding.item_key is None
        and "not a mapping" in finding.reason
        for finding in preview.findings
    )


def test_providers_missing_is_hard_error(tmp_path: Path) -> None:
    """Proves: STORY-038-AC-3

    A missing (or empty, or non-sequence) ``providers`` key is a file-scoped
    hard error.
    """
    document = _document(_GOOD_ENTRY)
    del document["providers"]
    file_path = write_yaml_mapping(tmp_path, document)
    service = make_service()

    with pytest.raises(ConfigurationError):
        service.build_provider_import_preview(file_path)


def test_embedding_missing_is_hard_error(tmp_path: Path) -> None:
    """Proves: STORY-038-AC-3

    A missing (or non-mapping) ``embedding`` key is a file-scoped hard error.
    """
    document = _document(_GOOD_ENTRY)
    del document["embedding"]
    file_path = write_yaml_mapping(tmp_path, document)
    service = make_service()

    with pytest.raises(ConfigurationError):
        service.build_provider_import_preview(file_path)


def test_schema_version_soft_warning_on_provider_import(tmp_path: Path) -> None:
    """Proves: STORY-038-AC-3

    An invalid ``schema_version`` on a provider-config import is the same
    file-level soft warning as on a settings import (§6.1).
    """
    document = _document(_GOOD_ENTRY)
    document["schema_version"] = "not-an-integer"
    file_path = write_yaml_mapping(tmp_path, document)
    service = make_service()

    preview = service.build_provider_import_preview(file_path)

    file_level_findings = [finding for finding in preview.findings if finding.item_key is None]
    assert any(
        finding.severity is ImportFindingSeverity.SOFT_WARNING for finding in file_level_findings
    )
