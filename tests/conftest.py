"""Root fixtures: filesystem isolation. Qt parity rig + Hypothesis profiles land with the
first story that needs them (Phase 0 has no Qt or Hypothesis usage yet).

See docs/v3_specification/16_Engineering_Standards/07_TESTING_STANDARD.md Sections 5 and 12.
"""

import pytest


@pytest.fixture(autouse=True)
def _isolate_filesystem(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "appdata"))
