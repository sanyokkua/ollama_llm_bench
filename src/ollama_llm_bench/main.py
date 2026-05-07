import argparse
import logging
import signal
import sys
import types
from importlib import resources
from logging.handlers import RotatingFileHandler
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication, QStyleFactory

from ollama_llm_bench.app_context import ContextProvider
from ollama_llm_bench.backend.core.app_paths import ensure_user_data_dir
from ollama_llm_bench.ui.main_window import MainWindow
from ollama_llm_bench.ui.style.theme_loader import apply_theme, connect_system_theme_listener, detect_system_theme

logger = logging.getLogger(__name__)


_LOG_FILE_NAME: str = "app.log"
_LOG_MAX_BYTES: int = 10_485_760  # 10 MB
_LOG_BACKUP_COUNT: int = 5


def configure_logger(log_level: str | None = None, *, app_root: Path | None = None) -> int:
    """Configure root logger with an optional console handler and always-on file handler.

    Args:
        log_level: Console log level ('debug', 'info', 'warning', 'error'), or None
                   to suppress console output entirely.
        app_root: If provided, a RotatingFileHandler writing DEBUG-level output to
                  ``{app_root}/logs/app.log`` is always attached regardless of
                  ``log_level``.

    Returns:
        Effective numeric log level that was configured for the console handler,
        or ``logging.CRITICAL + 1`` when console output is disabled.
    """
    root_logger = logging.getLogger()

    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)-8s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console_level = logging.CRITICAL + 1
    if log_level is not None:
        level_map = {"debug": logging.DEBUG, "info": logging.INFO, "warning": logging.WARNING, "error": logging.ERROR}
        console_level = level_map.get(log_level.lower(), logging.ERROR)
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(console_level)
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)

    if app_root is not None:
        log_dir = app_root / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            log_dir / _LOG_FILE_NAME,
            maxBytes=_LOG_MAX_BYTES,
            backupCount=_LOG_BACKUP_COUNT,
            encoding="utf-8",
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    root_logger.setLevel(logging.DEBUG if root_logger.handlers else logging.CRITICAL + 1)
    root_logger.propagate = False
    return console_level


def get_dataset_path(custom_path: str | None = None) -> Path:
    """
    Get the dataset path, handling both development and production environments.

    Args:
        custom_path: Optional custom path to dataset directory.

    Returns:
        Resolved path to the dataset directory.

    Raises:
        FileNotFoundError: If the specified path does not exist.
        NotADirectoryError: If the specified path is not a directory.
    """
    if custom_path:
        path = Path(custom_path).resolve()
        if not path.exists():
            raise FileNotFoundError(f"Custom dataset path does not exist: {path}")
        if not path.is_dir():
            raise NotADirectoryError(f"Custom dataset path is not a directory: {path}")
        return path

    try:
        # For packaged application
        with resources.path("ollama_llm_bench", "dataset") as path:
            return path
    except (ImportError, TypeError, FileNotFoundError):
        # For development
        # In development, the dataset is at src/ollama_llm_bench/dataset
        return Path(__file__).parent / "dataset"


def main() -> None:
    """
    Main application entry point.
    Parses command line arguments, configures logging, initializes application context,
    and starts the Qt event loop.
    """
    parser = argparse.ArgumentParser(description="Ollama LLM Benchmark")
    parser.add_argument(
        "--log-level",
        choices=["debug", "info", "warning", "error"],
        default=None,  # CHANGED: None means logging disabled by default
        help="Enable logging with specified level (default: disabled)",
    )
    parser.add_argument(
        "--dataset",
        "-d",
        type=str,
        default=None,
        help="Path to custom dataset directory (default: bundled dataset)",
    )
    args = parser.parse_args()

    try:
        app_root = ensure_user_data_dir()
        log_level = configure_logger(args.log_level, app_root=app_root)

        # Only log paths if logging is enabled
        if log_level <= logging.INFO:
            logger.info(f"Application root: {app_root}")

        # Get dataset path (bundled or custom)
        dataset_path = get_dataset_path(args.dataset)

        # Only log dataset path if logging is enabled
        if log_level <= logging.INFO:
            logger.info(f"Dataset path: {dataset_path}")

        QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
        app = QApplication(sys.argv)
        fusion = QStyleFactory.create("Fusion")
        if fusion:
            app.setStyle(fusion)
        apply_theme(app, detect_system_theme())

        # Initialize context after QApplication — Qt objects (QMutex, QThreadPool,
        # QtEventBus) must not be created before QApplication exists.
        ContextProvider.initialize(app_root, dataset_path=dataset_path)
        ctx = ContextProvider.get_context()

        saved_theme = ctx.get_app_settings_service().get("ui.theme") or "system"
        effective_theme = detect_system_theme() if saved_theme == "system" else saved_theme
        apply_theme(app, effective_theme)

        if saved_theme == "system":
            connect_system_theme_listener(lambda t: apply_theme(app, t))

        main_window = MainWindow(ctx)
        main_window.show()

        # Route SIGINT/SIGTERM through closeEvent for clean shutdown.
        # The QTimer forces Python to process signals every 200ms while Qt's
        # C++ event loop is running (otherwise signal delivery is delayed indefinitely).
        def _handle_signal(signum: int, frame: types.FrameType | None) -> None:
            logger.info(f"Received signal {signum} — closing main window")
            main_window.close()

        signal.signal(signal.SIGINT, _handle_signal)
        signal.signal(signal.SIGTERM, _handle_signal)

        _signal_timer = QTimer()
        _signal_timer.timeout.connect(lambda: None)
        _signal_timer.start(200)

        sys.exit(app.exec())
    except Exception as e:
        # Always print critical errors to stderr, even if logging is disabled
        print(f"Application failed to start: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc(file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
