"""The live tier's opt-in gate and reachability bound (STORY-086).

Deliberately in ``tests/unit/`` rather than in ``tests/live_local/``: this criterion is about
what happens on a machine with no opt-in and no server -- exactly the machines that never run
the live tier -- so a proving test inside that tier would itself be skipped and prove nothing.

Loads the tier's conftest by file location because ``tests/`` has no ``__init__.py`` files and
therefore no importable package path. The loader registers it under the unique name
``live_local_conftest``, never the bare ``conftest`` that pytest itself uses -- that name is
shared by every conftest in the run and resolves to whichever was imported last (ADR-0011).
"""

import importlib.util
from pathlib import Path
import time
import types
from typing import Final

import pytest

_CONFTEST_PATH: Final[Path] = Path(__file__).resolve().parents[1] / "live_local" / "conftest.py"
_CLOSED_PORT_URL: Final[str] = "http://127.0.0.1:1/v1"
"""Port 1 is privileged and never bound by this project's tooling, so a connect there is
refused immediately -- the deterministic stand-in for 'no server installed'."""

_REACHABILITY_BOUND_S: Final[float] = 2.0
_BOUND_TOLERANCE_S: Final[float] = 3.0


def _load_live_local_conftest() -> types.ModuleType:
    spec = importlib.util.spec_from_file_location("live_local_conftest", _CONFTEST_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.unit
def test_live_tests_skip_when_opt_in_unset_or_server_absent() -> None:
    """Proves: STORY-086-AC-3

    With the opt-in variable unset (or set to anything but ``1``) the tier's gate reports
    disabled, and an unreachable target resolves to "not reachable" within the bounded
    connection timeout rather than raising or hanging -- so every test in
    ``tests/live_local/`` skips and no live server is contacted.
    """
    # Arrange
    conftest = _load_live_local_conftest()

    # Act
    opt_in_unset = conftest.live_local_opt_in_enabled({})
    opt_in_wrong_value = conftest.live_local_opt_in_enabled({conftest.OPT_IN_ENV_VAR: "0"})
    opt_in_enabled = conftest.live_local_opt_in_enabled(
        {conftest.OPT_IN_ENV_VAR: conftest.OPT_IN_ENABLED_VALUE}
    )
    started = time.monotonic()
    reachable = conftest.server_reachable(_CLOSED_PORT_URL, timeout_s=_REACHABILITY_BOUND_S)
    elapsed = time.monotonic() - started

    # Assert
    assert (
        opt_in_unset,
        opt_in_wrong_value,
        opt_in_enabled,
        reachable,
        elapsed < _BOUND_TOLERANCE_S,
    ) == (
        False,
        False,
        True,
        False,
        True,
    ), f"gate/reachability contract broken; reachability took {elapsed:.1f}s"
