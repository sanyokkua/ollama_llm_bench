"""The as-built architecture documentation exists and is not the Phase-0 stub (STORY-093-AC-5).

Source of truth: ``docs/v3_specification/16_Engineering_Standards/01_PROJECT_STRUCTURE.md`` §2
(the place of ``docs/architecture/`` in the ``docs/`` tree).

`docs/architecture/README.md` shipped as a placeholder that deferred to the vendored
specification. Phase 12 replaces it. This test pins the replacement: both documents exist, each
covers its own subject, and neither carries a phrase that only made sense while the directory was
empty. It asserts presence and subject, not prose quality -- the point is that the stub cannot
come back unnoticed.
"""

from pathlib import Path

DOCS_ROOT = Path(__file__).resolve().parents[2] / "docs" / "architecture"
README_PATH = DOCS_ROOT / "README.md"
DATA_MODEL_PATH = DOCS_ROOT / "data-model.md"

# Phrases that were only true while `docs/architecture/` was a Phase-0 placeholder.
STUB_PHRASES = (
    "Until that documentation exists",
    "It starts empty at Phase 0",
    "This document is a stub",
)

_MIN_SUBSTANTIVE_LENGTH = 2000


def test_architecture_readme_and_data_model_exist_and_are_not_stubs() -> None:
    """Proves: STORY-093-AC-5

    `docs/architecture/README.md` and `docs/architecture/data-model.md` both exist, describe
    respectively the built three-layer architecture and the persistence data model, and neither
    contains the Phase-0 stub's placeholder sentences.
    """
    assert README_PATH.is_file(), f"missing {README_PATH}"
    assert DATA_MODEL_PATH.is_file(), f"missing {DATA_MODEL_PATH}"

    readme = README_PATH.read_text(encoding="utf-8")
    data_model = DATA_MODEL_PATH.read_text(encoding="utf-8")

    for path, text in ((README_PATH, readme), (DATA_MODEL_PATH, data_model)):
        surviving = [phrase for phrase in STUB_PHRASES if phrase in text]
        assert not surviving, f"{path.name} still carries stub text: {surviving}"
        assert len(text) >= _MIN_SUBSTANTIVE_LENGTH, (
            f"{path.name} is too short to be the as-built documentation ({len(text)} characters)"
        )

    # The README covers the three layers, the rule that binds them, and the composition root.
    for layer in ("backend/", "adapters/", "ui/"):
        assert layer in readme, f"README does not describe the {layer} layer"
    assert "import-linter" in readme
    assert "compose.py" in readme

    # The data model covers the tables, their owning stores, and the write discipline.
    for table in ("benchmark_runs", "benchmark_results", "benchmark_tasks", "app_meta"):
        assert table in data_model, f"data-model.md does not describe {table}"
    assert "WAL" in data_model
    assert "BEGIN IMMEDIATE" in data_model
    assert "recover_in_flight_results" in data_model
