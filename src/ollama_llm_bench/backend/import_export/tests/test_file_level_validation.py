"""Proves: STORY-038-AC-1 — file-level condition severity (06_IMPORT_FORMATS.md §6.1)."""

from pathlib import Path

import pytest

from ollama_llm_bench.backend.errors import ConfigurationError, TaskFileError
from ollama_llm_bench.backend.import_export.models import ImportFindingSeverity
from ollama_llm_bench.backend.import_export.tests.conftest import make_service, write_yaml_text


@pytest.mark.parametrize(
    ("suffix", "content", "expected_exception"),
    [
        (".txt", "kind: settings\nsettings: {}\n", TaskFileError),
        (".yaml", "kind: settings\nsettings: {a: 1\n", TaskFileError),
        (".yaml", "- one\n- two\n", TaskFileError),
        (".yaml", "kind: provider_config\nsettings: {}\n", ConfigurationError),
        (".yaml", "schema_version: 999\nsettings: {}\n", ConfigurationError),
    ],
    ids=[
        "extension_not_yaml_or_yml",
        "malformed_yaml",
        "root_not_a_mapping",
        "kind_wrong_for_action",
        "schema_version_newer_than_build",
    ],
)
def test_file_level_condition_severity(
    tmp_path: Path, suffix: str, content: str, expected_exception: type[Exception]
) -> None:
    """Proves: STORY-038-AC-1

    Each hard-error file-level condition aborts the whole import (the import
    aborts before a preview is ever built) — covers EC-IMP-1, EC-IMP-2, EC-IMP-3.
    """
    file_path = write_yaml_text(tmp_path, content, name=f"import{suffix}")
    service = make_service()

    with pytest.raises(expected_exception):
        service.build_settings_import_preview(file_path)


@pytest.mark.parametrize(
    "schema_version_value",
    ["not-an-integer", -1],
    ids=["schema_version_non_integer", "schema_version_less_than_one"],
)
def test_schema_version_soft_conditions_treated_as_one(
    tmp_path: Path, schema_version_value: object
) -> None:
    """Proves: STORY-038-AC-1

    An invalid ``schema_version`` is a soft warning, not a hard error — the
    import still proceeds and is treated as ``schema_version: 1``.
    """
    file_path = write_yaml_text(
        tmp_path,
        f"schema_version: {schema_version_value!r}\nkind: settings\nsettings: {{}}\n",
    )
    service = make_service()

    preview = service.build_settings_import_preview(file_path)

    file_level_findings = [finding for finding in preview.findings if finding.item_key is None]
    assert any(
        finding.severity is ImportFindingSeverity.SOFT_WARNING for finding in file_level_findings
    )


def test_unreadable_file_is_hard_error(tmp_path: Path) -> None:
    """Proves: STORY-038-AC-1

    A file that cannot be decoded as UTF-8 at all is a hard error, distinct
    from a YAML syntax error.
    """
    file_path = tmp_path / "import.yaml"
    file_path.write_bytes(b"\xff\xfe\x00\x01not-valid-utf8\x80\x81")
    service = make_service()

    with pytest.raises(TaskFileError):
        service.build_settings_import_preview(str(file_path))


def test_schema_version_absent_produces_no_file_level_finding(tmp_path: Path) -> None:
    """Proves: STORY-038-AC-1

    An absent ``schema_version`` is treated as ``1`` silently — it produces
    no finding at all, unlike the invalid-value soft-warning cases.
    """
    file_path = write_yaml_text(tmp_path, "kind: settings\nsettings: {ui.theme: dark}\n")
    service = make_service()

    preview = service.build_settings_import_preview(file_path)

    assert not any(finding.item_key is None for finding in preview.findings)
