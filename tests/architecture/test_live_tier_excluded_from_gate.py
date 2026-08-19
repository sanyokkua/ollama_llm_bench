"""Architecture test: the `live_local` tier is registered and deselected by default (STORY-086).

Source of truth: ADR-0011 Decision outcome §1 (the tier is excluded from `just check` and
from CI) and ``docs/v3_specification/16_Engineering_Standards/07_TESTING_STANDARD.md`` §3
(every pytest marker is declared in ``[tool.pytest.ini_options]`` under ``--strict-markers``).

This is the one STORY-086 guard that runs in the offline gate, on a machine with no Ollama
and no LM Studio installed.
"""

from pathlib import Path
import tomllib
from typing import Final

_REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
_MARKER: Final[str] = "live_local"


def _pytest_ini_options() -> dict[str, object]:
    raw = (_REPO_ROOT / "pyproject.toml").read_bytes()
    tool = tomllib.loads(raw.decode("utf-8"))["tool"]
    assert isinstance(tool, dict)
    options = tool["pytest"]["ini_options"]
    assert isinstance(options, dict)
    return options


def test_live_local_marker_excluded_from_default_selection() -> None:
    """Proves: STORY-086-AC-4

    A bare ``uv run pytest`` -- the shape used by ``just test``, ``just coverage-layers``,
    ``release.yml``'s quality gate and ``pr-gate.yml``'s coverage step -- selects no test
    carrying the ``live_local`` marker, and the marker is registered so ``--strict-markers``
    does not turn the tier into a collection error.
    """
    # Arrange
    options = _pytest_ini_options()
    markers = options["markers"]
    addopts = options["addopts"]
    assert isinstance(markers, list)
    assert isinstance(addopts, list)

    # Act
    declared = [entry for entry in markers if str(entry).startswith(f"{_MARKER}:")]
    marker_expressions = [
        str(addopts[index + 1])
        for index, entry in enumerate(addopts)
        if entry == "-m" and index + 1 < len(addopts)
    ]

    # Assert
    assert declared, f"{_MARKER} is not declared in [tool.pytest.ini_options].markers"
    assert len(marker_expressions) == 1, (
        "addopts must carry exactly one -m entry -- pytest honours only the last one, so a "
        "second entry (e.g. STORY-094's packaging tier) would silently disable this one; "
        f"found {marker_expressions}"
    )
    assert f"not {_MARKER}" in marker_expressions[0]
