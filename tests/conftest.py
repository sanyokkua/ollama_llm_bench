"""Root fixtures: filesystem isolation, Hypothesis profiles. Qt parity rig lands with the
first story that needs it.

See docs/v3_specification/16_Engineering_Standards/07_TESTING_STANDARD.md Sections 5, 10, 12.
"""

import os
from pathlib import Path

from hypothesis import HealthCheck, settings
import pytest

settings.register_profile("dev", max_examples=20, deadline=None)
settings.register_profile(
    "release", max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow]
)
settings.register_profile(
    "ci",
    max_examples=200,
    deadline=None,
    derandomize=True,
    suppress_health_check=[HealthCheck.too_slow],
)
settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "dev"))


@pytest.fixture(autouse=True)
def _isolate_filesystem(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "appdata"))
