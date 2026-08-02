"""Integration test for the app-data-directory permission-failure abort path
(STORY-078-AC-1, EC-M-1).
"""

from pathlib import Path

from PySide6.QtCore import QEventLoop
from PySide6.QtWidgets import QApplication
import pytest
from pytest_mock import MockerFixture

from ollama_llm_bench.compose import build_app
from ollama_llm_bench.ui.common_dialogs import ErrorDialogPattern


@pytest.fixture
def isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect `Path.home()` into `tmp_path` so the real, non-injected
    `PlatformDetector` `build_app` constructs resolves `<app-data>` under `tmp_path`
    on every host platform (mirrors `test_compose_build_app.py`'s `isolated_home`)."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    return home


def test_app_data_permission_failure_aborts_with_modal_and_exits(
    isolated_home: Path, qapp: QApplication, mocker: MockerFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Proves: STORY-078-AC-1

    Given the application-data directory does not exist and cannot be created
    because of a permission failure, when launch reaches the app-data step, then
    launch aborts with a modal naming the path and the process exits (EC-M-1).
    """
    # Arrange
    permission_error = PermissionError("Permission denied")

    def _raise_permission_error(self: Path, *args: object, **kwargs: object) -> None:
        raise permission_error

    monkeypatch.setattr(Path, "mkdir", _raise_permission_error)
    dialog = mocker.Mock()
    make_error_dialog_spy = mocker.patch(
        "ollama_llm_bench.compose.make_error_dialog", return_value=dialog
    )

    # Act / Assert
    with pytest.raises(SystemExit) as exc_info:
        build_app(app=qapp, loop=QEventLoop())

    assert exc_info.value.code == 1
    payload = make_error_dialog_spy.call_args.kwargs["payload"]
    assert payload.pattern is ErrorDialogPattern.FATAL
    dialog.exec.assert_called_once()
