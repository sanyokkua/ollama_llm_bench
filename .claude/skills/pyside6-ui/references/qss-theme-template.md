# QSS Theme Template Reference

This is the complete QSS template for the dark theme. The light theme uses the same selectors with different token values. Every `{placeholder}` corresponds to a key in the token dict (see `design-tokens.md`).

Copy this as `theme_dark.qss` and `theme_light.qss` — the same template works for both since the tokens provide the different values.

## Complete Template

```qss
/* ============================================================
   Theme QSS Template
   Generated from design tokens. Do not hardcode colors here.
   All {placeholders} are replaced at runtime by theme_loader.py
   ============================================================ */

/* --- Base --- */
QMainWindow, QDialog {{
    background-color: {bg_primary};
    color: {text_primary};
    font-family: {font_sans};
    font-size: 13px;
}}

/* --- Labels --- */
QLabel {{
    color: {text_primary};
}}
QLabel[role="secondary"] {{
    color: {text_secondary};
    font-size: 12px;
}}
QLabel[role="heading"] {{
    color: {text_secondary};
    font-size: 11px;
    font-weight: 700;
}}
QLabel[role="title"] {{
    font-size: 15px;
    font-weight: 700;
}}

/* --- Buttons: Primary --- */
QPushButton[role="primary"] {{
    background-color: {primary};
    color: {text_on_primary};
    border: none;
    border-radius: {radius_md};
    padding: 6px 16px;
    font-weight: 600;
    min-height: 32px;
}}
QPushButton[role="primary"]:hover {{
    background-color: {primary_hover};
}}
QPushButton[role="primary"]:pressed {{
    background-color: {primary_pressed};
}}
QPushButton[role="primary"]:disabled {{
    background-color: {primary_disabled};
    color: {text_disabled};
}}

/* --- Buttons: Secondary --- */
QPushButton[role="secondary"] {{
    background-color: transparent;
    color: {primary};
    border: 1px solid {border};
    border-radius: {radius_md};
    padding: 6px 16px;
    min-height: 32px;
}}
QPushButton[role="secondary"]:hover {{
    background-color: {hover};
    border-color: {primary};
}}
QPushButton[role="secondary"]:pressed {{
    background-color: {selection};
}}
QPushButton[role="secondary"]:disabled {{
    color: {text_disabled};
    border-color: {border};
}}

/* --- Buttons: Danger --- */
QPushButton[role="danger"] {{
    background-color: transparent;
    color: {failure};
    border: 1px solid {border};
    border-radius: {radius_md};
    padding: 6px 16px;
    min-height: 32px;
}}
QPushButton[role="danger"]:hover {{
    background-color: {failure_bg};
    border-color: {failure};
}}

/* --- Buttons: Icon (compact) --- */
QPushButton[role="icon"] {{
    background-color: transparent;
    color: {text_secondary};
    border: 1px solid {border};
    border-radius: {radius_md};
    padding: 4px 8px;
    min-height: 28px;
    min-width: 28px;
}}
QPushButton[role="icon"]:hover {{
    background-color: {hover};
    color: {text_primary};
}}

/* --- Buttons: Small variant --- */
QPushButton[size="small"] {{
    font-size: 11px;
    padding: 3px 10px;
    min-height: 24px;
}}

/* --- Combo Box --- */
QComboBox {{
    background-color: {bg_input};
    border: 1px solid {border};
    border-radius: {radius_md};
    padding: 5px 12px;
    color: {text_primary};
    min-height: 32px;
}}
QComboBox:focus {{
    border-color: {border_focus};
}}
QComboBox:disabled {{
    color: {text_disabled};
    background-color: {bg_secondary};
}}
QComboBox::drop-down {{
    border: none;
    width: 20px;
}}
QComboBox QAbstractItemView {{
    background-color: {bg_secondary};
    border: 1px solid {border};
    selection-background-color: {selection};
    color: {text_primary};
}}

/* --- Line Edit / Spin Boxes --- */
QLineEdit, QSpinBox, QDoubleSpinBox {{
    background-color: {bg_input};
    border: 1px solid {border};
    border-radius: {radius_md};
    padding: 5px 12px;
    color: {text_primary};
    min-height: 32px;
}}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
    border-color: {border_focus};
}}
QLineEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled {{
    color: {text_disabled};
    background-color: {bg_secondary};
}}
QLineEdit[role="filter"] {{
    font-size: 11px;
    min-height: 26px;
    padding: 3px 10px;
}}

/* --- Text Edit (log, code) --- */
QTextEdit {{
    background-color: {bg_input};
    border: 1px solid {border};
    border-radius: {radius_md};
    padding: 8px;
    color: {text_primary};
    font-family: {font_mono};
    font-size: 12px;
}}

/* --- Checkbox --- */
QCheckBox {{
    color: {text_primary};
    spacing: 8px;
}}
QCheckBox::indicator {{
    width: 18px;
    height: 18px;
    border-radius: {radius_sm};
    border: 2px solid {border};
    background-color: {bg_input};
}}
QCheckBox::indicator:checked {{
    background-color: {primary};
    border-color: {primary};
}}
QCheckBox::indicator:disabled {{
    border-color: {text_disabled};
    background-color: {bg_secondary};
}}

/* --- Radio Button --- */
QRadioButton {{
    color: {text_primary};
    spacing: 8px;
}}
QRadioButton::indicator {{
    width: 18px;
    height: 18px;
    border-radius: 9px;
    border: 2px solid {border};
    background-color: {bg_input};
}}
QRadioButton::indicator:checked {{
    border-color: {primary};
}}

/* --- Progress Bar --- */
QProgressBar {{
    background-color: {bg_secondary};
    border: 1px solid {border};
    border-radius: 10px;
    min-height: 20px;
    text-align: center;
    font-size: 11px;
    font-weight: 600;
    color: {text_primary};
}}
QProgressBar::chunk {{
    background-color: {primary};
    border-radius: 10px;
}}

/* --- Tab Bar --- */
QTabBar::tab {{
    padding: 8px 20px;
    color: {text_secondary};
    font-weight: 600;
    border-bottom: 2px solid transparent;
}}
QTabBar::tab:selected {{
    color: {primary};
    border-bottom-color: {primary};
}}
QTabBar::tab:hover:!selected {{
    color: {text_primary};
}}
QTabWidget::pane {{
    border: none;
}}

/* --- Table View --- */
QTableView {{
    background-color: {bg_primary};
    border: 1px solid {border};
    gridline-color: {bg_secondary};
    selection-background-color: {selection};
    color: {text_primary};
    font-size: 12px;
}}
QHeaderView::section {{
    background-color: {bg_secondary};
    color: {text_secondary};
    font-weight: 600;
    font-size: 11px;
    padding: 8px 10px;
    border: none;
    border-bottom: 1px solid {border};
}}

/* --- Group Box --- */
QGroupBox {{
    border: 1px solid {border};
    border-radius: {radius_md};
    padding: 16px;
    margin-top: 16px;
}}
QGroupBox::title {{
    color: {text_secondary};
    font-size: 11px;
    font-weight: 700;
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 6px;
}}

/* --- Scrollbar (vertical) --- */
QScrollBar:vertical {{
    background-color: {scrollbar_bg};
    width: 8px;
    border-radius: 4px;
}}
QScrollBar::handle:vertical {{
    background-color: {scrollbar_handle};
    border-radius: 4px;
    min-height: 30px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}

/* --- Scrollbar (horizontal) --- */
QScrollBar:horizontal {{
    background-color: {scrollbar_bg};
    height: 8px;
    border-radius: 4px;
}}
QScrollBar::handle:horizontal {{
    background-color: {scrollbar_handle};
    border-radius: 4px;
    min-width: 30px;
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0px;
}}

/* --- Splitter --- */
QSplitter::handle {{
    background-color: {border};
    width: 5px;
}}
QSplitter::handle:hover {{
    background-color: {primary};
}}

/* --- Tooltip --- */
QToolTip {{
    background-color: {bg_secondary};
    color: {text_primary};
    border: 1px solid {border};
    border-radius: {radius_sm};
    padding: 6px 10px;
    font-size: 12px;
}}

/* --- Badge Labels (via property) --- */
QLabel[verdict="pass"] {{
    background-color: {success_bg};
    color: {success};
    border-radius: 10px;
    padding: 2px 8px;
    font-size: 11px;
    font-weight: 700;
}}
QLabel[verdict="fail"] {{
    background-color: {failure_bg};
    color: {failure};
    border-radius: 10px;
    padding: 2px 8px;
    font-size: 11px;
    font-weight: 700;
}}

/* --- Health Dots (via property) --- */
QLabel[health="live"] {{
    background-color: {success};
    border-radius: 5px;
    min-width: 10px;
    max-width: 10px;
    min-height: 10px;
    max-height: 10px;
}}
QLabel[health="down"] {{
    background-color: {failure};
    border-radius: 5px;
    min-width: 10px;
    max-width: 10px;
    min-height: 10px;
    max-height: 10px;
}}
QLabel[health="unknown"] {{
    background-color: {text_disabled};
    border-radius: 5px;
    min-width: 10px;
    max-width: 10px;
    min-height: 10px;
    max-height: 10px;
}}

/* --- Provider Card (QFrame) --- */
QFrame[role="provider-card"] {{
    background-color: {bg_card};
    border: 1px solid {border};
    border-radius: {radius_md};
    padding: 12px;
}}
QFrame[role="provider-card"][health="down"] {{
    border-color: {failure};
}}

/* --- Drop Zone --- */
QLabel[role="drop-zone"] {{
    border: 2px dashed {border};
    border-radius: {radius_lg};
    padding: 24px;
    color: {text_disabled};
    font-size: 13px;
}}
QLabel[role="drop-zone"][active="true"] {{
    border-color: {primary};
    color: {primary};
    background-color: {hover};
}}

/* --- Log Entry (QFrame) --- */
QFrame[role="log-entry"] {{
    border-left: 3px solid {accent};
    padding: 8px 12px;
    margin-bottom: 4px;
}}
QFrame[role="log-entry"][status="error"] {{
    border-left-color: {failure};
    background-color: {failure_bg};
}}
QFrame[role="log-entry"][status="streaming"] {{
    border-left-color: {primary};
}}
```

## Important QSS Notes

1. **Double braces `{{` `}}`** — In the actual `.qss` file used with Python's `.format()`, you need to escape literal braces as `{{` and `}}`. The template above shows them escaped for direct use with `str.format(**tokens)`.

2. **Property selectors** like `[role="primary"]` require the property to be set via `widget.setProperty("role", "primary")` before the stylesheet is applied. If you set the property after the stylesheet, call `unpolish`/`polish`.

3. **Pseudo-state precedence** — More specific selectors override less specific ones. `QPushButton[role="primary"]:hover` overrides `QPushButton[role="primary"]`.

4. **Platform differences** — Some sub-controls render differently on macOS vs Windows vs Linux. Test on your target platforms. In particular, `QComboBox::drop-down` and `QProgressBar::chunk` may need platform-specific tweaks.

5. **Font inheritance** — Setting `font-family` on `QMainWindow` propagates to all children unless overridden. Set it once at the top level.
