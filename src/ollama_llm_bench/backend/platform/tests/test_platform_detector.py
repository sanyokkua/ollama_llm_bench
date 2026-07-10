"""Authoritative acceptance-criteria tests for STORY-005's platform detector.

Covers STORY-005-AC-1, STORY-005-AC-2, STORY-005-AC-3 — see
``docs/stories/story-005-platform-detector-and-app-data-paths.md``.
"""

from pathlib import Path

import pytest

from ollama_llm_bench.backend.platform import PlatformKind
from ollama_llm_bench.backend.platform._internal.detector import InjectablePlatformDetector


@pytest.mark.parametrize(
    "platform_identifier,environ,home_path,expected_kind,expected_app_data_root",
    [
        (
            "darwin",
            {},
            Path("/Users/testuser"),
            PlatformKind.MACOS,
            Path("/Users/testuser/Library/Application Support/OllamaLLMBench"),
        ),
        (
            "win32",
            {"LOCALAPPDATA": "C:\\Users\\testuser\\AppData\\Local"},
            Path("C:/Users/testuser"),
            PlatformKind.WINDOWS,
            Path("C:\\Users\\testuser\\AppData\\Local") / "OllamaLLMBench",
        ),
        (
            "linux",
            {"XDG_DATA_HOME": "/home/testuser/.local/share"},
            Path("/home/testuser"),
            PlatformKind.LINUX,
            Path("/home/testuser/.local/share/OllamaLLMBench"),
        ),
    ],
    ids=["macos", "windows", "linux"],
)
def test_platform_kind_and_app_data_root_per_os(
    platform_identifier: str,
    environ: dict[str, str],
    home_path: Path,
    expected_kind: PlatformKind,
    expected_app_data_root: Path,
) -> None:
    """Proves: STORY-005-AC-1

    For a faked macOS, Windows, and Linux host identity, ``detect()`` classifies
    ``kind`` correctly and resolves ``app_data_root`` to exactly the documented
    per-OS path.
    """
    # Arrange
    detector = InjectablePlatformDetector(
        platform_identifier=platform_identifier, environ=environ, home_path=home_path
    )

    # Act
    profile = detector.detect()

    # Assert
    assert profile.kind is expected_kind
    assert profile.app_data_root == expected_app_data_root


@pytest.mark.parametrize(
    "environ",
    [
        {},
        {"XDG_DATA_HOME": ""},
    ],
    ids=["unset", "empty_string"],
)
def test_xdg_data_home_unset_or_empty_falls_back(environ: dict[str, str]) -> None:
    """Proves: STORY-005-AC-2

    Given a faked Linux host with ``XDG_DATA_HOME`` unset or set to an empty
    string, ``app_data_root`` resolves to ``~/.local/share/OllamaLLMBench/``.
    """
    # Arrange
    home_path = Path("/home/testuser")
    detector = InjectablePlatformDetector(
        platform_identifier="linux", environ=environ, home_path=home_path
    )

    # Act
    profile = detector.detect()

    # Assert
    assert profile.app_data_root == home_path / ".local" / "share" / "OllamaLLMBench"


def test_unknown_host_falls_back_to_linux_conventions() -> None:
    """Proves: STORY-005-AC-3

    Given a host identity the detector cannot classify, ``kind`` resolves to
    ``UNKNOWN`` and every OS-dependent field resolves using the Linux-convention
    fallback, with no exception raised during detection itself.
    """
    # Arrange
    home_path = Path("/home/testuser")
    detector = InjectablePlatformDetector(
        platform_identifier="freebsd13", environ={}, home_path=home_path
    )

    # Act
    profile = detector.detect()

    # Assert
    assert profile.kind is PlatformKind.UNKNOWN
    assert profile.app_data_root == home_path / ".local" / "share" / "OllamaLLMBench"
    assert profile.path_separator == "/"
    assert profile.line_ending == "\n"
    assert profile.file_manager_label == "Open in file manager"
