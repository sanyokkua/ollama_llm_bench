# Design Tokens Reference

Complete token definitions for the theming system. These Python dicts live in `ui/style/tokens.py` and are injected into QSS templates via `str.format(**tokens)`.

## DARK Theme Tokens

```python
DARK = {
    "bg_primary":       "#111827",
    "bg_secondary":     "#1F2937",
    "bg_card":          "#263044",
    "bg_input":         "#1F2937",
    "border":           "#374151",
    "border_focus":     "#14B8A6",
    "primary":          "#14B8A6",
    "primary_hover":    "#0FA898",
    "primary_pressed":  "#0D9488",
    "primary_disabled": "#2D5A54",
    "text_primary":     "#F9FAFB",
    "text_secondary":   "#9CA3AF",
    "text_disabled":    "#4B5563",
    "text_on_primary":  "#111827",
    "accent":           "#A78BFA",
    "accent_light":     "#2E1065",
    "success":          "#34D399",
    "success_bg":       "#064E3B",
    "failure":          "#F87171",
    "failure_bg":       "#7F1D1D",
    "warning":          "#FBBF24",
    "warning_bg":       "#78350F",
    "selection":        "#134E4A",
    "hover":            "#1A3A35",
    "scrollbar_bg":     "#1F2937",
    "scrollbar_handle": "#4B5563",
}
```

## LIGHT Theme Tokens

```python
LIGHT = {
    "bg_primary":       "#FDFDFD",
    "bg_secondary":     "#F3F4F6",
    "bg_card":          "#FFFFFF",
    "bg_input":         "#FFFFFF",
    "border":           "#D1D5DB",
    "border_focus":     "#0D9488",
    "primary":          "#0D9488",
    "primary_hover":    "#0B7E73",
    "primary_pressed":  "#096B62",
    "primary_disabled": "#A7D3CF",
    "text_primary":     "#0F172A",
    "text_secondary":   "#64748B",
    "text_disabled":    "#9CA3AF",
    "text_on_primary":  "#FFFFFF",
    "accent":           "#8B5CF6",
    "accent_light":     "#EDE9FE",
    "success":          "#059669",
    "success_bg":       "#ECFDF5",
    "failure":          "#DC2626",
    "failure_bg":       "#FEF2F2",
    "warning":          "#D97706",
    "warning_bg":       "#FFFBEB",
    "selection":        "#CCFBF1",
    "hover":            "#F0FDFA",
    "scrollbar_bg":     "#E5E7EB",
    "scrollbar_handle": "#9CA3AF",
}
```

## SHARED Tokens (theme-independent)

```python
SHARED = {
    "font_sans":    '"Segoe UI", "SF Pro Display", Ubuntu, "Noto Sans", sans-serif',
    "font_mono":    '"JetBrains Mono", "Fira Code", Consolas, "Courier New", monospace',
    "radius_sm":    "4px",
    "radius_md":    "6px",
    "radius_lg":    "8px",
    "radius_pill":  "10px",
    "spacing_xs":   "4px",
    "spacing_sm":   "8px",
    "spacing_md":   "12px",
    "spacing_lg":   "16px",
    "spacing_xl":   "24px",
}
```

## Theme Loader Implementation

```python
# ui/style/theme_loader.py
from pathlib import Path
from PySide6.QtWidgets import QApplication
from .tokens import DARK, LIGHT, SHARED

_THEMES = {"dark": DARK, "light": LIGHT}

def apply_theme(app: QApplication, theme: str = "dark") -> None:
    """Load QSS template, inject tokens, apply to application."""
    tokens = {**SHARED, **_THEMES[theme]}
    qss_path = Path(__file__).parent / f"theme_{theme}.qss"
    template = qss_path.read_text(encoding="utf-8")
    app.setStyleSheet(template.format(**tokens))

def get_color(theme: str, token_name: str) -> str:
    """Get a color hex value for use in QPainter code."""
    merged = {**SHARED, **_THEMES[theme]}
    return merged[token_name]
```

## Color Semantic Mapping

| Semantic Role | Dark Hex | Light Hex | Where Used |
|--------------|----------|-----------|------------|
| Background (main) | #111827 | #FDFDFD | Window, panels |
| Background (cards/sections) | #1F2937 | #F3F4F6 | Table headers, group boxes |
| Primary action | #14B8A6 | #0D9488 | Buttons, active indicators, links |
| Text (primary) | #F9FAFB | #0F172A | All body text |
| Text (secondary) | #9CA3AF | #64748B | Labels, hints, secondary info |
| Accent | #A78BFA | #8B5CF6 | Cosine scores, L3 layer, highlights |
| Success / PASS | #34D399 | #059669 | Verdict badges, pass rates |
| Failure / FAIL | #F87171 | #DC2626 | Error states, fail badges |
| Warning | #FBBF24 | #D97706 | Pause state, low-score alerts |
| Selection highlight | #134E4A | #CCFBF1 | Table row selection |

## Resolution Layer Color Mapping

For eval pipeline visualization:

| Layer | Color Token | Meaning |
|-------|------------|---------|
| L1 (rule-based) | `failure` | Auto-FAIL by rules |
| L2 (keyword) | `warning` | Keyword verification resolved |
| L3 (cosine) | `accent` | Cosine similarity resolved |
| L4 (judge) | `primary` | LLM judge decided |

## Chart Color Cycle

When displaying ranked data (bar charts, comparisons):

1. First / best → `primary`
2. Middle tier → `accent`
3. Worst / failing → `failure`

For multi-series charts, cycle through: `primary` → `accent` → `warning` → `success`.
