import logging

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QPushButton, QTextEdit, QVBoxLayout, QWidget

from ollama_llm_bench.core.controllers import LogWidgetControllerApi

logger = logging.getLogger(__name__)


class LogWidget(QWidget):
    def __init__(self, controller: LogWidgetControllerApi):
        super().__init__()
        self._controller = controller

        self._clean_button = QPushButton("Clean")
        self._text_edit = QTextEdit()
        self._text_edit.setReadOnly(True)
        self._text_edit.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        layout = QVBoxLayout()
        layout.addWidget(self._clean_button)
        layout.addWidget(self._text_edit)
        self.setLayout(layout)

        self._clean_button.clicked.connect(self._clear_text)
        self._controller.subscribe_to_log_clear(self._clear_text)
        self._controller.subscribe_to_log_append(self._append_text)

    def _clear_text(self):
        logger.debug("Clearing text")
        self._text_edit.clear()

    def _append_text(self, text: str):
        logger.debug(f"Appending text: {text}")
        self._text_edit.append("\n")
        self._text_edit.append(text)
        self._text_edit.append("\n")
        scrollbar = self._text_edit.verticalScrollBar()
        if scrollbar is not None:
            scrollbar.setValue(scrollbar.maximum())
