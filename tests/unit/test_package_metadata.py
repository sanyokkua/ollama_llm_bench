"""Cross-module unit test: the installed package metadata matches pyproject.toml.

Real signal, not a fake pass -- catches drift between the editable install and the
single source of truth for the project version
(docs/v3_specification/16_Engineering_Standards/01_PROJECT_STRUCTURE.md Section 10:
"There is one project version, declared in pyproject.toml").
"""

from importlib.metadata import version


def test_installed_version_matches_pyproject() -> None:
    assert version("ollama-llm-bench") == "1.0.0"
