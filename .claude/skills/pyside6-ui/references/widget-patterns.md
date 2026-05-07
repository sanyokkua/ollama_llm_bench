# Widget Construction Patterns

Concrete code patterns for every custom widget in the design system. Each pattern shows the class structure, property setup, and signal wiring.

## BadgeLabel — Verdict/Status Badges

A QLabel that displays PASS/FAIL/WAITING/stage badges. Styled entirely via QSS property selectors.

```python
from PySide6.QtWidgets import QLabel

class BadgeLabel(QLabel):
    """Pill-shaped status badge. Set verdict via set_verdict()."""

    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self.setProperty("role", "badge")

    def set_verdict(self, verdict: str) -> None:
        """Set to 'pass', 'fail', 'waiting', or a layer string like 'L3:cosine'."""
        self.setProperty("verdict", verdict)
        self.style().unpolish(self)
        self.style().polish(self)
```

## HealthDot — Provider Status Indicator

A fixed-size QLabel that shows as a colored circle.

```python
from PySide6.QtWidgets import QLabel

class HealthDot(QLabel):
    """10x10px colored dot indicating provider health."""

    def __init__(self, status: str = "unknown", parent=None):
        super().__init__(parent)
        self.setFixedSize(10, 10)
        self.set_status(status)

    def set_status(self, status: str) -> None:
        """Set to 'live', 'down', or 'unknown'."""
        self.setProperty("health", status)
        self.style().unpolish(self)
        self.style().polish(self)
```

## ProviderCard — Provider Info Card

A QFrame showing provider name, URL, model count, health status, and action buttons.

```python
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QVBoxLayout, QLabel, QPushButton

class ProviderCard(QFrame):
    test_clicked = Signal(str)  # provider_id
    edit_clicked = Signal(str)  # provider_id

    def __init__(self, *, provider_id: str, name: str, url: str, parent=None):
        super().__init__(parent)
        self.setProperty("role", "provider-card")
        self._provider_id = provider_id

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        # Health dot
        self._health = HealthDot("unknown")
        layout.addWidget(self._health)

        # Info column
        info = QVBoxLayout()
        info.setSpacing(2)
        self._name_label = QLabel(name)
        self._name_label.setProperty("role", "title")
        self._url_label = QLabel(url)
        self._url_label.setProperty("role", "secondary")
        self._models_label = QLabel("Checking...")
        self._models_label.setProperty("role", "secondary")
        info.addWidget(self._name_label)
        info.addWidget(self._url_label)
        info.addWidget(self._models_label)
        layout.addLayout(info, stretch=1)

        # Action buttons
        test_btn = QPushButton("Test")
        test_btn.setProperty("role", "secondary")
        test_btn.setProperty("size", "small")
        test_btn.clicked.connect(lambda: self.test_clicked.emit(self._provider_id))
        layout.addWidget(test_btn)

    def update_health(self, status: str, model_count: int = 0) -> None:
        self._health.set_status(status)
        self.setProperty("health", status)
        self.style().unpolish(self)
        self.style().polish(self)
        if status == "live":
            self._models_label.setText(f"{model_count} models available")
        elif status == "down":
            self._models_label.setText("Connection failed")
        else:
            self._models_label.setText("Not checked")
```

## ProgressWidget — Benchmark Progress Display

Combines stage badge, progress bar, ETA, and current model/task info. Each field updates independently to avoid unnecessary full redraws.

```python
from PySide6.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel, QProgressBar

class ProgressWidget(QFrame):
    """Structured progress display for benchmark execution."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # Row 1: stage badge + provider + health
        row1 = QHBoxLayout()
        self._stage_badge = BadgeLabel("IDLE")
        self._stage_badge.set_verdict("waiting")
        self._provider_label = QLabel()
        self._provider_label.setProperty("role", "secondary")
        self._health_dot = HealthDot("unknown")
        row1.addWidget(self._stage_badge)
        row1.addWidget(self._provider_label)
        row1.addWidget(self._health_dot)
        row1.addStretch()
        layout.addLayout(row1)

        # Row 2: progress bar
        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        layout.addWidget(self._progress_bar)

        # Row 3: stats line
        self._stats_label = QLabel()
        self._stats_label.setProperty("role", "secondary")
        layout.addWidget(self._stats_label)

    def update_progress(self, *, completed: int, total: int, eta: str = "") -> None:
        pct = int(completed / total * 100) if total > 0 else 0
        self._progress_bar.setValue(pct)
        self._progress_bar.setFormat(f"{pct}% — {completed} / {total}")
        if eta:
            self._stats_label.setText(f"ETA: {eta}")

    def update_stage(self, stage: str) -> None:
        self._stage_badge.setText(stage.upper())
        self._stage_badge.set_verdict("waiting" if stage == "idle" else "pass")

    def update_provider(self, name: str, health: str) -> None:
        self._provider_label.setText(name)
        self._health_dot.set_status(health)
```

## LogWidget — Structured Log with Collapsible Entries

A scrollable container of LogEntry cards. Supports auto-scroll with manual override.

```python
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QScrollArea, QWidget, QPushButton, QLineEdit
)

class LogWidget(QFrame):
    """Scrollable structured log with filter and auto-scroll."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # Filter input
        self._filter = QLineEdit()
        self._filter.setPlaceholderText("Filter by model, task, or keyword...")
        self._filter.setProperty("role", "filter")
        self._filter.textChanged.connect(self._apply_filter)
        layout.addWidget(self._filter)

        # Scroll area
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._container = QWidget()
        self._entries_layout = QVBoxLayout(self._container)
        self._entries_layout.setContentsMargins(0, 0, 0, 0)
        self._entries_layout.setSpacing(4)
        self._entries_layout.addStretch()  # Push entries to top

        self._scroll.setWidget(self._container)
        layout.addWidget(self._scroll)

        # Jump-to-bottom button (hidden by default)
        self._jump_btn = QPushButton("Jump to bottom")
        self._jump_btn.setProperty("role", "secondary")
        self._jump_btn.setProperty("size", "small")
        self._jump_btn.setVisible(False)
        self._jump_btn.clicked.connect(self._scroll_to_bottom)
        layout.addWidget(self._jump_btn)

        # Auto-scroll tracking
        self._auto_scroll = True
        vbar = self._scroll.verticalScrollBar()
        vbar.valueChanged.connect(self._on_scroll)
        vbar.rangeChanged.connect(self._on_range_changed)

    def add_entry(self, entry: "LogEntry") -> None:
        # Insert before the stretch
        count = self._entries_layout.count()
        self._entries_layout.insertWidget(count - 1, entry)

    def _scroll_to_bottom(self) -> None:
        vbar = self._scroll.verticalScrollBar()
        vbar.setValue(vbar.maximum())
        self._auto_scroll = True
        self._jump_btn.setVisible(False)

    def _on_scroll(self, value: int) -> None:
        vbar = self._scroll.verticalScrollBar()
        at_bottom = value >= vbar.maximum() - 20
        if not at_bottom:
            self._auto_scroll = False
            self._jump_btn.setVisible(True)
        else:
            self._auto_scroll = True
            self._jump_btn.setVisible(False)

    def _on_range_changed(self, _min: int, _max: int) -> None:
        if self._auto_scroll:
            self._scroll.verticalScrollBar().setValue(_max)

    def _apply_filter(self, text: str) -> None:
        text_lower = text.lower()
        for i in range(self._entries_layout.count()):
            widget = self._entries_layout.itemAt(i).widget()
            if widget and hasattr(widget, "matches_filter"):
                widget.setVisible(widget.matches_filter(text_lower))
```

## LogEntry — Individual Log Card

```python
from PySide6.QtWidgets import QFrame, QVBoxLayout, QLabel

class LogEntry(QFrame):
    """Collapsible log entry for a single model+task result."""

    def __init__(self, *, model: str, task: str, parent=None):
        super().__init__(parent)
        self.setProperty("role", "log-entry")
        self._model = model
        self._task = task

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 12, 8)
        layout.setSpacing(4)

        # Header (always visible)
        self._header = QLabel(f"\u25B8 {model} — {task}")
        self._header.setStyleSheet("font-weight: 600; font-size: 12px;")
        layout.addWidget(self._header)

        # Collapsible sections (hidden by default)
        self._prompt_label = QLabel("\u25B8 Prompt (click to expand)")
        self._prompt_label.setProperty("role", "secondary")
        self._prompt_label.setVisible(False)
        layout.addWidget(self._prompt_label)

        self._response_label = QLabel()
        self._response_label.setWordWrap(True)
        layout.addWidget(self._response_label)

        self._metrics_label = QLabel()
        self._metrics_label.setProperty("role", "secondary")
        layout.addWidget(self._metrics_label)

        self._verdict_row = BadgeLabel()
        layout.addWidget(self._verdict_row)

    def set_response(self, text: str) -> None:
        self._response_label.setText(text)

    def set_metrics(self, time_ms: int, tokens: int, tps: float) -> None:
        self._metrics_label.setText(
            f"{time_ms:,}ms \u00B7 {tokens:,} tok \u00B7 {tps:.1f} tok/s"
        )

    def set_verdict(self, verdict: str, score: float, layer: str) -> None:
        symbol = "\u2713" if verdict == "pass" else "\u2717"
        self._verdict_row.setText(f"{symbol} {verdict.upper()}")
        self._verdict_row.set_verdict(verdict)

    def set_error(self, message: str) -> None:
        self.setProperty("status", "error")
        self.style().unpolish(self)
        self.style().polish(self)
        self._response_label.setText(message)

    def matches_filter(self, text: str) -> bool:
        return text in self._model.lower() or text in self._task.lower()
```

## DropZoneWidget — Drag-and-Drop Target

```python
from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import QLabel

class DropZoneWidget(QLabel):
    """Accepts drag-and-drop of .yaml files or folders."""
    files_dropped = Signal(list)  # list of Path objects

    def __init__(self, text: str = "Drop files here", parent=None):
        super().__init__(text, parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setProperty("role", "drop-zone")
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.setProperty("active", "true")
            self.style().unpolish(self)
            self.style().polish(self)

    def dragLeaveEvent(self, event):
        self.setProperty("active", "false")
        self.style().unpolish(self)
        self.style().polish(self)

    def dropEvent(self, event):
        self.setProperty("active", "false")
        self.style().unpolish(self)
        self.style().polish(self)
        from pathlib import Path
        paths = [Path(url.toLocalFile()) for url in event.mimeData().urls()]
        self.files_dropped.emit(paths)
```

## ChartWidget — QPainter-Based Bar Chart

```python
from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QPainter, QColor, QFont
from PySide6.QtWidgets import QWidget, QSizePolicy

class BarChartWidget(QWidget):
    """Simple bar chart drawn with QPainter. No external libraries."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._data: list[tuple[str, float, str]] = []  # (label, value, color_hex)
        self._title = ""
        self.setSizePolicy(
            QSizePolicy.Policy.MinimumExpanding,
            QSizePolicy.Policy.MinimumExpanding,
        )

    def sizeHint(self) -> QSize:
        return QSize(200, 120)

    def set_data(self, data: list[tuple[str, float, str]], title: str = "") -> None:
        self._data = data
        self._title = title
        self.update()  # Queue repaint

    def paintEvent(self, event):
        if not self._data:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()
        margin = 24
        chart_h = h - margin * 2
        bar_w = max(20, (w - margin * 2) // len(self._data) - 8)
        max_val = max(v for _, v, _ in self._data) or 1

        for i, (label, value, color) in enumerate(self._data):
            x = margin + i * (bar_w + 8)
            bar_h = int((value / max_val) * chart_h)
            y = h - margin - bar_h
            painter.fillRect(x, y, bar_w, bar_h, QColor(color))
            # Label below bar
            painter.setPen(QColor("#9CA3AF"))
            painter.setFont(QFont("sans-serif", 9))
            painter.drawText(x, h - 4, label)

        if self._title:
            painter.setPen(QColor("#64748B"))
            painter.drawText(w // 2 - 50, h - 2, self._title)

        painter.end()  # ALWAYS call end()
```

## ModelSelector — Checkable List with Provider Filter

```python
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFrame, QVBoxLayout, QComboBox, QListWidget, QListWidgetItem
from PySide6.QtCore import Qt

class ModelSelector(QFrame):
    """Multi-select model list with provider filter dropdown."""
    selection_changed = Signal(list)  # list of (provider_id, model_name)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self._provider_filter = QComboBox()
        self._provider_filter.addItem("All Providers")
        self._provider_filter.currentIndexChanged.connect(self._apply_filter)
        layout.addWidget(self._provider_filter)

        self._list = QListWidget()
        self._list.itemChanged.connect(self._on_item_changed)
        layout.addWidget(self._list)

        self._models: list[dict] = []  # {provider_id, model_name, display}

    def set_models(self, models: list[dict]) -> None:
        self._models = models
        providers = sorted(set(m["provider_id"] for m in models))
        self._provider_filter.clear()
        self._provider_filter.addItem("All Providers")
        self._provider_filter.addItems(providers)
        self._rebuild_list()

    def _rebuild_list(self) -> None:
        self._list.clear()
        provider = self._provider_filter.currentText()
        for m in self._models:
            if provider != "All Providers" and m["provider_id"] != provider:
                continue
            item = QListWidgetItem(m["display"])
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            item.setData(Qt.ItemDataRole.UserRole, m)
            self._list.addItem(item)

    def _apply_filter(self) -> None:
        self._rebuild_list()

    def _on_item_changed(self, item: QListWidgetItem) -> None:
        selected = []
        for i in range(self._list.count()):
            it = self._list.item(i)
            if it.checkState() == Qt.CheckState.Checked:
                data = it.data(Qt.ItemDataRole.UserRole)
                selected.append((data["provider_id"], data["model_name"]))
        self.selection_changed.emit(selected)

    def get_selected(self) -> list[tuple[str, str]]:
        selected = []
        for i in range(self._list.count()):
            it = self._list.item(i)
            if it.checkState() == Qt.CheckState.Checked:
                data = it.data(Qt.ItemDataRole.UserRole)
                selected.append((data["provider_id"], data["model_name"]))
        return selected
```
