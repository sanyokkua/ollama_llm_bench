import sys
from pathlib import Path

import pytest

from ollama_llm_bench.backend.core.app_paths import get_user_data_dir


def test_get_user_data_dir_macos(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    result = get_user_data_dir()
    assert result == Path.home() / "Library" / "Application Support" / "OllamaLLMBench"


def test_get_user_data_dir_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("APPDATA", "C:\\Users\\test\\AppData\\Roaming")
    result = get_user_data_dir()
    assert result == Path("C:\\Users\\test\\AppData\\Roaming") / "OllamaLLMBench"


def test_get_user_data_dir_linux_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    result = get_user_data_dir()
    assert result == Path.home() / ".local" / "share" / "OllamaLLMBench"


def test_get_user_data_dir_linux_xdg(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setenv("XDG_DATA_HOME", "/custom/data")
    result = get_user_data_dir()
    assert result == Path("/custom/data") / "OllamaLLMBench"
