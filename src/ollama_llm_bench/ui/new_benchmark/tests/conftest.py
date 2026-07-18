"""Shared fixtures for ``ui/new_benchmark/tests/`` (STORY-054).

Mirrors ``ui/main_window/_internal/tests/conftest.py``'s in-process synchronous
``EventBus`` test double and real-``ThemeManager`` pattern.
"""

from collections.abc import Callable

from PySide6.QtWidgets import QApplication
import pytest

from ollama_llm_bench.backend.domain import RunMode
from ollama_llm_bench.backend.events import Subscription
from ollama_llm_bench.backend.mode_visibility import visible_sections
from ollama_llm_bench.ui.theme import PlatformKind, ThemeManager, ThemeSetting, make_theme_manager


class _FakeSubscription:
    def __init__(self, cancel_fn: Callable[[], None]) -> None:
        self._cancel_fn = cancel_fn
        self._cancelled = False

    def cancel(self) -> None:
        if self._cancelled:
            return
        self._cancelled = True
        self._cancel_fn()


class FakeEventBus:
    """A synchronous, in-process ``EventBus`` test double (immediate delivery)."""

    def __init__(self) -> None:
        self._handlers: dict[str, list[Callable[[object], None]]] = {}

    def subscribe(
        self, signal_name: str, handler: Callable[[object], None], owner: object | None = None
    ) -> Subscription:
        self._handlers.setdefault(signal_name, []).append(handler)

        def _cancel() -> None:
            self._handlers[signal_name].remove(handler)

        return _FakeSubscription(_cancel)

    def emit(self, signal_name: str, payload: object) -> None:
        for handler in list(self._handlers.get(signal_name, [])):
            handler(payload)


class _RealBackedModeVisibilityPolicy:
    """Wraps the real ``backend.mode_visibility.visible_sections`` -- see Design Decision 4."""

    def visible_sections(self, mode: RunMode) -> tuple:  # type: ignore[type-arg]  # matches Protocol's bare tuple return
        return visible_sections(mode)


@pytest.fixture
def fake_event_bus() -> FakeEventBus:
    return FakeEventBus()


@pytest.fixture
def real_mode_visibility_policy() -> _RealBackedModeVisibilityPolicy:
    return _RealBackedModeVisibilityPolicy()


@pytest.fixture
def platform_kind() -> PlatformKind:
    return PlatformKind.MACOS


@pytest.fixture
def theme_manager(qapp: QApplication, platform_kind: PlatformKind) -> ThemeManager:
    return make_theme_manager(
        app=qapp, theme_setting=ThemeSetting.DARK, platform_kind=platform_kind
    )
