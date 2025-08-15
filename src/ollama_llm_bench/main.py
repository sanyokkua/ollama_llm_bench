import logging
import sys
from pathlib import Path

from PyQt6.QtWidgets import QApplication

from ollama_llm_bench.app_context import ContextProvider
from ollama_llm_bench.ui.main_window import MainWindow


def configure_logger(log_level: int = logging.INFO) -> None:
    try:
        formatter = logging.Formatter(
            fmt='%(asctime)s [%(levelname)-8s] %(name)s: %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S',
        )
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(formatter)
        root_logger = logging.getLogger()
        root_logger.setLevel(log_level)
        root_logger.addHandler(handler)
        root_logger.propagate = False
        logging.info("Logger configured successfully")
        logging.debug("Debug logging is enabled")
    except Exception as e:
        print(f"Failed to configure logger: {e}", file=sys.stderr)
        raise


logger = logging.getLogger(__name__)

ROOT_FOLDER_PATH = Path(__file__).parent.parent.parent


def main() -> None:
    configure_logger(logging.DEBUG)
    ContextProvider.initialize(ROOT_FOLDER_PATH)
    ctx = ContextProvider.get_context()
    app = QApplication(sys.argv)
    main_window = MainWindow(ctx)
    main_window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
