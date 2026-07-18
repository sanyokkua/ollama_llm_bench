"""Window-geometry persistence: a debounced writer plus the restore-time off-screen clamp.

Source of truth: ``docs/v3_specification/01_Main_Window/description.md`` §7 (persistence)
and §2 (sizing defaults); edge case EC-PLAT-3 / EC-PERSIST-2 (stored geometry fully
off-screen after a monitor change).

The persisted format is a plain ``"x,y,w,h"`` CSV string -- deliberately simpler to
construct/inspect/test than Qt's opaque ``saveGeometry()`` blob.
"""

from collections.abc import Sequence

from PySide6.QtCore import QRect, QTimer
from PySide6.QtGui import QGuiApplication, QScreen
from PySide6.QtWidgets import QMainWindow
import structlog

from ollama_llm_bench.ui.main_window.protocols import MainWindowGateway

__all__: list[str] = ["DebouncedGeometryWriter", "geometry_to_str", "restore_geometry"]

logger = structlog.get_logger(__name__)

_DEFAULT_WIDTH = 1440
_DEFAULT_HEIGHT = 900
_DEFAULT_DEBOUNCE_MS = 200
_GEOMETRY_FIELD_COUNT = 4


def geometry_to_str(rect: QRect) -> str:
    """Serialize ``rect`` to the persisted ``"x,y,w,h"`` CSV format (§7)."""
    return f"{rect.x()},{rect.y()},{rect.width()},{rect.height()}"


class DebouncedGeometryWriter:
    """Coalesces a burst of resize/move or splitter-drag events into one write each.

    One ``QTimer(singleShot=True)`` per persisted key (``window_geometry``,
    ``splitter_sizes``). Each raw event handler records the latest value and restarts its
    timer; Qt restarts a running single-shot timer's countdown, so a burst of events
    collapses into exactly one write, ``debounce_ms`` after the burst stops, carrying the
    last value observed (AC-7).
    """

    def __init__(
        self, *, gateway: MainWindowGateway, debounce_ms: int = _DEFAULT_DEBOUNCE_MS
    ) -> None:
        """Store the gateway this writer persists through and start both timers idle.

        Args:
            gateway: The ``MainWindowGateway`` this writer calls
                ``set_window_geometry``/``set_splitter_sizes`` on.
            debounce_ms: The coalescing window, in milliseconds, shared by both keys.
        """
        self._gateway = gateway
        self._pending_geometry: str | None = None
        self._pending_splitter_sizes: str | None = None
        self._geometry_timer = QTimer()
        self._geometry_timer.setSingleShot(True)
        self._geometry_timer.setInterval(debounce_ms)
        self._geometry_timer.timeout.connect(self._flush_geometry)
        self._splitter_timer = QTimer()
        self._splitter_timer.setSingleShot(True)
        self._splitter_timer.setInterval(debounce_ms)
        self._splitter_timer.timeout.connect(self._flush_splitter_sizes)

    def on_window_geometry_changed(self, geometry_str: str) -> None:
        """Record the latest window geometry and (re)start its debounce timer."""
        self._pending_geometry = geometry_str
        self._geometry_timer.start()

    def on_splitter_sizes_changed(self, sizes_str: str) -> None:
        """Record the latest splitter sizes and (re)start its debounce timer."""
        self._pending_splitter_sizes = sizes_str
        self._splitter_timer.start()

    def flush(self) -> None:
        """Write any pending values immediately, bypassing the debounce (quit sequence)."""
        self._geometry_timer.stop()
        self._splitter_timer.stop()
        self._flush_geometry()
        self._flush_splitter_sizes()

    def _flush_geometry(self) -> None:
        if self._pending_geometry is not None:
            self._gateway.set_window_geometry(self._pending_geometry)
            logger.debug("window_geometry_persisted", value=self._pending_geometry)

    def _flush_splitter_sizes(self) -> None:
        if self._pending_splitter_sizes is not None:
            self._gateway.set_splitter_sizes(self._pending_splitter_sizes)
            logger.debug("splitter_sizes_persisted", value=self._pending_splitter_sizes)


def restore_geometry(
    window: QMainWindow,
    gateway: MainWindowGateway,
    *,
    screens: Sequence[QScreen] | None = None,
) -> None:
    """Restore ``window``'s geometry from ``gateway``, clamped to the available screens.

    Falls back to a centred ``1440x900`` default when no persisted geometry exists, the
    persisted value is malformed, or it would place the window fully off-screen (AC-8,
    EC-PLAT-3). ``screens`` is injectable so a test can pass a fake screen list instead of
    depending on the real display.

    Args:
        window: The top-level window whose geometry is set.
        gateway: The gateway ``ui.window_geometry`` is read from.
        screens: The candidate screens to clamp against; defaults to
            ``QGuiApplication.screens()``.
    """
    resolved_screens = screens if screens is not None else QGuiApplication.screens()
    rect = _parse_geometry(gateway.get_window_geometry())
    if rect is None or not _fits_any_screen(rect, resolved_screens):
        rect = _default_centered_rect(resolved_screens)
    window.setGeometry(rect)


def _parse_geometry(raw: str | None) -> QRect | None:
    """Parse the persisted ``"x,y,w,h"`` CSV string, or ``None`` if malformed/absent."""
    if raw is None:
        return None
    parts = raw.split(",")
    if len(parts) != _GEOMETRY_FIELD_COUNT:
        return None
    try:
        x, y, width, height = (int(part) for part in parts)
    except ValueError:
        return None
    if width <= 0 or height <= 0:
        return None
    return QRect(x, y, width, height)


def _fits_any_screen(rect: QRect, screens: Sequence[QScreen]) -> bool:
    """Return ``True`` when ``rect`` intersects at least one screen's available area."""
    return any(screen.availableGeometry().intersects(rect) for screen in screens)


def _default_centered_rect(screens: Sequence[QScreen]) -> QRect:
    """Return the default ``1440x900`` rect, centred on ``screens[0]``, or at ``(0, 0)``."""
    if not screens:
        return QRect(0, 0, _DEFAULT_WIDTH, _DEFAULT_HEIGHT)
    available = screens[0].availableGeometry()
    x = available.x() + (available.width() - _DEFAULT_WIDTH) // 2
    y = available.y() + (available.height() - _DEFAULT_HEIGHT) // 2
    return QRect(x, y, _DEFAULT_WIDTH, _DEFAULT_HEIGHT)
