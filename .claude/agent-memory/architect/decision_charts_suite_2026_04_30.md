---
name: 12-Chart Suite design (2026-04-30)
description: Architecture decisions for replacing ChartsWidget with 12-chart ChartsSwitcherWidget using pure-Python aggregation layer
type: project
---

Selected **QComboBox switcher + ChartFrame per chart** over tab-based extension or sidebar approaches.

**Why:** The 6-tab structure cannot scale to 12 charts readably. The data model mismatch (SummaryTableItem missing ttft_ms, final_verdict, judge_score etc.) requires a full aggregation rewrite regardless. Pure-Python aggregation in `backend/services/charts/` allows unit testing without Qt, satisfying the 80% coverage requirement.

**Key decisions:**
- `ResultWidgetControllerApi` gains `subscribe_to_chart_data_change(Callable[[BenchmarkRun | None, list[BenchmarkResult]], None])` and `get_app_settings_service() -> AppSettingsServiceApi` — both abstract methods.
- `ResultWidgetController._emit_chart_data()` fires after `_set_run_id()` and `_set_detailed_summary()` so live run updates reach the chart.
- Chart 9 (heatmap): custom `HeatmapWidget(QWidget)` with `paintEvent` + `QPainter.fillRect`; wrapped in `HeatmapFrame` with `QScrollArea`. Color interpolation: linear RGB between failure/warning/success tokens.
- Chart 11 bubble-size: `QScatterSeries` does not support per-point markerSize — use multiple series, one per count bucket (3–5 tiers).
- Chart 6 error bars: subclass `QChartView` as `ErrorBarChartView`, override `paintEvent` to draw stdev whiskers after `super().paintEvent(event)`.
- Frames instantiated lazily on first navigation to avoid 12 QChart objects at startup.
- `app_settings` key `ui.charts_last_chart` persists the last-viewed chart name.
- Layer colors: L1=failure, L2=warning, L3=accent, L4=primary — consistent with existing tokens.

**How to apply:** When extending charts or adding a 13th chart family, add a new `BaseChartAggregator` subclass in `aggregations.py`, register it in `ChartsSwitcherWidget._frame_map`, add a unit test in `tests/unit/services/charts/`.
