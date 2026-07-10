"""Coder sanity checks for ``backend/platform/`` — not the authoritative AC suite.

The tester agent owns the STORY-005 acceptance-criteria tests (``Proves:`` docstrings).
These checks exist only to validate the implementation while it was being written.
"""

from pathlib import Path

import pytest

from ollama_llm_bench.backend.errors import ConfigurationError
from ollama_llm_bench.backend.platform import (
    PlatformKind,
    create_app_data_dir,
    make_platform_detector,
)
from ollama_llm_bench.backend.platform._internal.detector import InjectablePlatformDetector


def test_make_platform_detector_returns_real_profile() -> None:
    detector = make_platform_detector()
    profile = detector.detect()
    assert profile.kind in (
        PlatformKind.MACOS,
        PlatformKind.WINDOWS,
        PlatformKind.LINUX,
        PlatformKind.UNKNOWN,
    )
    assert profile.app_data_root.name == "OllamaLLMBench"


def test_macos_app_data_root() -> None:
    home = Path("/Users/someone")
    detector = InjectablePlatformDetector(platform_identifier="darwin", environ={}, home_path=home)
    profile = detector.detect()
    assert profile.kind is PlatformKind.MACOS
    assert profile.app_data_root == home / "Library" / "Application Support" / "OllamaLLMBench"


def test_windows_app_data_root() -> None:
    home = Path("C:/Users/someone")
    detector = InjectablePlatformDetector(
        platform_identifier="win32",
        environ={"LOCALAPPDATA": "C:/Users/someone/AppData/Local"},
        home_path=home,
    )
    profile = detector.detect()
    assert profile.kind is PlatformKind.WINDOWS
    assert profile.app_data_root == Path("C:/Users/someone/AppData/Local/OllamaLLMBench")


def test_linux_xdg_data_home_unset_falls_back() -> None:
    home = Path("/home/someone")
    detector = InjectablePlatformDetector(platform_identifier="linux", environ={}, home_path=home)
    profile = detector.detect()
    assert profile.kind is PlatformKind.LINUX
    assert profile.app_data_root == home / ".local" / "share" / "OllamaLLMBench"


def test_linux_xdg_data_home_empty_falls_back() -> None:
    home = Path("/home/someone")
    detector = InjectablePlatformDetector(
        platform_identifier="linux", environ={"XDG_DATA_HOME": ""}, home_path=home
    )
    profile = detector.detect()
    assert profile.app_data_root == home / ".local" / "share" / "OllamaLLMBench"


def test_unknown_host_falls_back_to_linux_conventions() -> None:
    home = Path("/home/someone")
    detector = InjectablePlatformDetector(
        platform_identifier="some-exotic-os", environ={}, home_path=home
    )
    profile = detector.detect()
    assert profile.kind is PlatformKind.UNKNOWN
    assert profile.app_data_root == home / ".local" / "share" / "OllamaLLMBench"
    assert profile.path_separator == "/"
    assert profile.line_ending == "\n"
    assert profile.file_manager_label == "Open in file manager"


def test_create_app_data_dir_idempotent(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "OllamaLLMBench"
    create_app_data_dir(target)
    assert target.is_dir()
    create_app_data_dir(target)  # second call must not raise
    assert target.is_dir()


def test_create_app_data_dir_non_ascii(tmp_path: Path) -> None:
    target = tmp_path / "Пользователь" / "OllamaLLMBench"
    result = create_app_data_dir(target)
    assert result == target
    assert target.is_dir()


def test_create_app_data_dir_permission_failure(tmp_path: Path) -> None:
    parent = tmp_path / "locked"
    parent.mkdir(mode=0o500)
    target = parent / "OllamaLLMBench"
    try:
        with pytest.raises(ConfigurationError) as exc_info:
            create_app_data_dir(target)
        assert str(target) in str(exc_info.value)
    finally:
        parent.chmod(0o700)
