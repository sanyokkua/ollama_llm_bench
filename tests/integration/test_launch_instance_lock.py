"""Integration test for the single-instance-lock launch abort path (STORY-078-AC-6)."""

from pathlib import Path

from PySide6.QtCore import QEventLoop
from PySide6.QtWidgets import QApplication
import pytest
from pytest_mock import MockerFixture

from ollama_llm_bench.backend.infra import acquire_instance_lock, make_system_clock
from ollama_llm_bench.backend.persistence.app_settings import DB_FILENAME
from ollama_llm_bench.backend.platform import create_app_data_dir, make_platform_detector
from ollama_llm_bench.compose import build_app
from ollama_llm_bench.ui.common_dialogs import ErrorDialogPattern


@pytest.fixture
def isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    return home


def test_second_instance_finds_lock_held_shows_modal_and_exits_without_opening_db(
    isolated_home: Path, qapp: QApplication, mocker: MockerFixture
) -> None:
    """Proves: STORY-078-AC-6

    Given the single-instance lock is already held by a live process, when a
    second launch attempts to acquire it, then launch aborts with an "already
    running" modal naming the data folder, no database file is created, and the
    process exits.
    """
    # Arrange — simulate a first, still-running instance holding the lock.
    profile = make_platform_detector().detect()
    app_data_root = create_app_data_dir(profile.app_data_root)
    held = acquire_instance_lock(app_data_root=app_data_root, clock=make_system_clock())
    assert held.lock is not None
    db_path = app_data_root / DB_FILENAME

    dialog = mocker.Mock(spec=["exec"])
    make_error_dialog_spy = mocker.patch(
        "ollama_llm_bench.compose.make_error_dialog", return_value=dialog
    )

    try:
        # Act / Assert
        with pytest.raises(SystemExit) as exc_info:
            build_app(app=qapp, loop=QEventLoop())

        assert exc_info.value.code == 1
        payload = make_error_dialog_spy.call_args.kwargs["payload"]
        assert payload.pattern is ErrorDialogPattern.FATAL
        assert str(app_data_root) in (payload.detail or "")
        assert not db_path.exists()
    finally:
        held.lock.release()
