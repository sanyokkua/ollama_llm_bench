"""Proves: STORY-038-AC-2 — the env-var-name-only api_key rule (06_IMPORT_FORMATS.md §5)."""

from pathlib import Path

from ollama_llm_bench.backend.import_export.models import ImportFindingSeverity, ImportPreviewGroup
from ollama_llm_bench.backend.import_export.tests.conftest import (
    FakeProvidersStore,
    make_service,
    write_yaml_mapping,
)

_LITERAL_SECRET = "sk-super-secret-literal-1234"  # noqa: S105  # test fixture value, not a real credential


def test_literal_secret_is_hard_error_and_not_persisted(tmp_path: Path) -> None:
    """Proves: STORY-038-AC-2

    Given a provider entry whose ``api_key`` is a literal secret (not an
    env-var name), when the file is validated, then that entry hard-errors,
    is dropped from the applied set, and the literal string never appears in
    any resulting draft or reaches the store on a confirmed apply.
    """
    document = {
        "kind": "provider_config",
        "schema_version": 1,
        "embedding": {"provider_name": "good_provider", "model_name": "nomic-embed-text"},
        "providers": [
            {
                "name": "good_provider",
                "type": "openai_compatible",
                "base_url": "http://localhost:11434/v1",
                "api_key": "",
                "enabled": True,
            },
            {
                "name": "bad_provider",
                "type": "openai_compatible",
                "base_url": "http://localhost:11434/v1",
                "api_key": _LITERAL_SECRET,
                "enabled": True,
            },
        ],
    }
    file_path = write_yaml_mapping(tmp_path, document)
    providers_store = FakeProvidersStore()
    service = make_service(providers_store=providers_store)

    preview = service.build_provider_import_preview(file_path)

    hard_errors = [
        finding
        for finding in preview.findings
        if finding.severity is ImportFindingSeverity.HARD_ERROR
        and finding.item_key == "bad_provider"
    ]
    assert hard_errors and "literal secret" in hard_errors[0].reason

    bad_item = next(item for item in preview.items if item.name == "bad_provider")
    assert bad_item.group is ImportPreviewGroup.SKIPPED
    assert bad_item.draft is None
    assert all(
        item.draft is None or item.draft.api_key_raw != _LITERAL_SECRET for item in preview.items
    )

    service.apply_provider_import(preview)

    applied = providers_store.list_providers()
    assert {provider.name for provider in applied} == {"good_provider"}
    assert all(provider.api_key_raw != _LITERAL_SECRET for provider in applied)
