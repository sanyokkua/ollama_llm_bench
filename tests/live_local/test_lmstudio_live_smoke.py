"""STORY-086 live smoke: a real local LM Studio server.

Runs only under ``OLLAMA_BENCH_LIVE_LOCAL_TESTS=1`` with a reachable server -- both gates live
in ``conftest.py``. Authority for this tier existing: ADR-0011 Decision outcome §1.

The probe, the discovery and the tiny run share one driver with the Ollama module; it is the
``live_smoke`` fixture. Fixtures are resolved by name, so nothing here imports anything from the
sibling conftest -- ``from conftest import ...`` silently binds whichever conftest pytest
imported last.
"""

from collections.abc import Callable
from typing import Any

import pytest


@pytest.mark.live_local
@pytest.mark.slow
@pytest.mark.allow_qt_warnings
def test_lmstudio_probe_discover_and_tiny_run(
    live_smoke: Callable[[str], Any],
    lmstudio_base_url: str,
    expected_live_smoke_outcome: Any,
) -> None:
    """Proves: STORY-086-AC-2

    Against a real local LM Studio: the health probe reports the server reachable, discovery
    returns at least one model, and one tiny real benchmark run reaches ``COMPLETED`` with a
    completed result row.
    """
    # Arrange / Act
    outcome = live_smoke(lmstudio_base_url)

    # Assert
    assert outcome == expected_live_smoke_outcome
