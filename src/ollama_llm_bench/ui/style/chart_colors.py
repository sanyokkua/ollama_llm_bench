"""Chart and QPainter colour constants — theme-independent visualization palette.

These colours are used for QPainter-driven rendering (QBarSet, QStandardItem
foreground, HTML inline styles) and cannot be driven by QSS. They are
intentionally theme-independent categorical values.
"""

from typing import Final

# Pass/fail/score colours for chart series
PASS_COLOR: Final[str] = "#22c55e"  # noqa: S105  # chart colour, not a credential
FAIL_COLOR: Final[str] = "#ef4444"
SCORE_COLOR: Final[str] = "#14b8a6"

# Categorical model palette for bar chart series
MODEL_PALETTE: Final[list[str]] = [
    "#6366f1",  # indigo
    "#f59e0b",  # amber
    "#ec4899",  # pink
    "#06b6d4",  # cyan
    "#10b981",  # emerald
    "#f97316",  # orange
    "#8b5cf6",  # violet
    "#14b8a6",  # teal
]

# Layer attribution colours for stacked charts
LAYER_COLORS: Final[dict[str, str]] = {
    "L1:rules": "#ef4444",
    "L2:keywords": "#f97316",
    "L3:cosine": "#eab308",
    "L4:judge": "#8b5cf6",
    "pass": "#22c55e",
}

# QStandardItem foreground for warning/unavailable model rows.
# Dark-theme warning token value — QStandardItem.setForeground() cannot be
# driven by QSS, so a static constant is used here.
WARNING_ITEM_COLOR: Final[str] = "#FBBF24"

# HTML inline colour for placeholder text in QTextEdit (matches dark text_secondary token)
PLACEHOLDER_TEXT_COLOR: Final[str] = "#9CA3AF"

# HTML inline colour for judge log entries in the log widget
JUDGE_LOG_COLOR: Final[str] = "#9C27B0"

# Fallback colour for unknown layer attribution in stacked bar charts
LAYER_FALLBACK_COLOR: Final[str] = "#94a3b8"
