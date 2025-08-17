import argparse
import logging
import sys
from importlib import resources
from pathlib import Path

from PyQt6.QtWidgets import QApplication

from ollama_llm_bench.app_context import ContextProvider
from ollama_llm_bench.ui.main_window import MainWindow

logger = logging.getLogger(__name__)


def configure_logger(log_level: str = None) -> int:
    """
    Configure logger. If log_level is None, disable logging completely.
    Otherwise, set up logging with the specified level.

    Args:
        log_level: Logging level as string ('debug', 'info', 'warning', 'error'),
                   or None to disable logging.

    Returns:
        Configured logging level.

    Raises:
        Exception: If logger configuration fails.
    """
    root_logger = logging.getLogger()

    # Remove any existing handlers to reset
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # If no log level specified, disable logging completely
    if log_level is None:
        root_logger.setLevel(logging.CRITICAL + 1)  # Set above CRITICAL (100)
        return logging.CRITICAL + 1

    # Otherwise configure with requested level
    log_level = log_level.lower()
    if log_level == "debug":
        level = logging.DEBUG
    elif log_level == "info":
        level = logging.INFO
    elif log_level == "warning":
        level = logging.WARNING
    else:  # Default to ERROR for any other value
        level = logging.ERROR

    try:
        formatter = logging.Formatter(
            fmt='%(asctime)s [%(levelname)-8s] %(name)s: %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S',
        )
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(formatter)
        root_logger.setLevel(level)
        root_logger.addHandler(handler)
        root_logger.propagate = False

        # Only show these messages if level is INFO or lower
        if level <= logging.INFO:
            logging.info("Logger configured successfully")
        if level <= logging.DEBUG:
            logging.debug("Debug logging is enabled")
        return level
    except Exception as e:
        print(f"Failed to configure logger: {e}", file=sys.stderr)
        raise


def get_dataset_path(custom_path: str = None) -> Path:
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
        with resources.path('ollama_llm_bench', 'dataset') as path:
            return path
    except (ImportError, TypeError, FileNotFoundError):
        # For development
        # In development, the dataset is at src/ollama_llm_bench/dataset
        return Path(__file__).parent / 'dataset'


def main() -> None:
    """
    Main application entry point.
    Parses command line arguments, configures logging, initializes application context,
    and starts the Qt event loop.
    """
    parser = argparse.ArgumentParser(description='Ollama LLM Benchmark')
    parser.add_argument(
        '--log-level',
        choices=['debug', 'info', 'warning', 'error'],
        default=None,  # CHANGED: None means logging disabled by default
        help='Enable logging with specified level (default: disabled)',
    )
    parser.add_argument(
        '--dataset',
        '-d',
        type=str,
        default=None,
        help='Path to custom dataset directory (default: bundled dataset)',
    )
    args = parser.parse_args()

    # Configure logger first so we can log any issues
    log_level = configure_logger(args.log_level)

    try:
        # Application root is CURRENT WORKING DIRECTORY
        app_root = Path.cwd()

        # Only log paths if logging is enabled
        if log_level <= logging.INFO:
            logger.info(f"Application root: {app_root}")

        # Get dataset path (bundled or custom)
        dataset_path = get_dataset_path(args.dataset)

        # Only log dataset path if logging is enabled
        if log_level <= logging.INFO:
            logger.info(f"Dataset path: {dataset_path}")

        # Initialize context with proper paths
        ContextProvider.initialize(app_root, dataset_path=dataset_path)
        ctx = ContextProvider.get_context()

        app = QApplication(sys.argv)
        main_window = MainWindow(ctx)
        main_window.show()
        sys.exit(app.exec())
    except Exception as e:
        # Always print critical errors to stderr, even if logging is disabled
        print(f"Application failed to start: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
