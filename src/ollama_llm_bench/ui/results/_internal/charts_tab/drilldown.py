"""Pure chart-element-click -> ``ChartDrilldownRequest`` mapping (STORY-064).

Source of truth: ``docs/v3_specification/05_Result_Widget/tabs/charts_tab.md`` §8
(chart-click drill-down). Imports no Qt symbol -- testable with no ``QApplication``.
"""

from ollama_llm_bench.backend.domain import ChartKind
from ollama_llm_bench.ui.results.models import ChartDrilldownRequest

__all__: list[str] = [
    "map_bar_click",
    "map_grouped_bar_click",
    "map_heatmap_cell_click",
    "map_scatter_point_click",
    "map_stacked_segment_click",
]


def map_bar_click(
    *, chart_kind: ChartKind, provider_id: str, model_name: str
) -> ChartDrilldownRequest:
    """Narrow the Details tab to a single model (charts_tab.md#8, charts 1, 2, 3, 5, 6).

    Args:
        chart_kind: The clicked chart's kind (kept for call-site symmetry with
            the other mappers; every per-model bar chart narrows identically).
        provider_id: The clicked bar's model's provider id.
        model_name: The clicked bar's model name.

    Returns:
        A drill-down request narrowing the Models chip to that one model.
    """
    del chart_kind
    return ChartDrilldownRequest(provider_id=provider_id, model_name=model_name)


def map_stacked_segment_click(
    *, chart_kind: ChartKind, provider_id: str, model_name: str, segment: str
) -> ChartDrilldownRequest:
    """Narrow the Details tab to a model plus its clicked stacked-bar segment.

    Args:
        chart_kind: Either ``SUCCESS_FAILED_INCOMPLETE_STACKED`` (chart 4, narrows
            by status) or ``VERDICT_COUNTS_STACKED`` (chart 7, narrows by verdict).
        provider_id: The clicked segment's model's provider id.
        model_name: The clicked segment's model name.
        segment: The clicked segment's status or verdict value.

    Returns:
        A drill-down request narrowing the Models chip to that model and the
        Status or Verdict chip to that segment (charts_tab.md#8).
    """
    if chart_kind is ChartKind.VERDICT_COUNTS_STACKED:
        return ChartDrilldownRequest(
            provider_id=provider_id, model_name=model_name, verdict=segment
        )
    return ChartDrilldownRequest(provider_id=provider_id, model_name=model_name, status=segment)


def map_scatter_point_click(
    *, chart_kind: ChartKind, provider_id: str, model_name: str, task_id: str
) -> ChartDrilldownRequest:
    """Narrow the Details tab to a scatter point's underlying result or model.

    Args:
        chart_kind: ``TIME_VS_TOKENS_SCATTER`` (chart 8) or ``TOKENS_PER_TASK_BOX``
            (chart 12, an outlier marker) narrow to the point's single result;
            ``SPEED_VS_QUALITY_SCATTER`` (chart 11) narrows to the point's model only.
        provider_id: The clicked point's model's provider id.
        model_name: The clicked point's model name.
        task_id: The clicked point's underlying result's task id; ignored for
            ``SPEED_VS_QUALITY_SCATTER``, which has no single-result back-reference.

    Returns:
        A drill-down request per charts_tab.md#8's per-kind narrowing rule.
    """
    if chart_kind is ChartKind.SPEED_VS_QUALITY_SCATTER:
        return ChartDrilldownRequest(provider_id=provider_id, model_name=model_name)
    return ChartDrilldownRequest(provider_id=provider_id, model_name=model_name, task_id=task_id)


def map_heatmap_cell_click(
    *, provider_id: str, model_name: str, task_id: str
) -> ChartDrilldownRequest:
    """Narrow the Details tab to a heatmap cell's ``(task_id, model)`` pair.

    Args:
        provider_id: The clicked cell's model's provider id.
        model_name: The clicked cell's model name.
        task_id: The clicked cell's row task id.

    Returns:
        A drill-down request narrowing the Tasks and Models chips to that
        pair (charts_tab.md#8, chart 9).
    """
    return ChartDrilldownRequest(provider_id=provider_id, model_name=model_name, task_id=task_id)


def map_grouped_bar_click(
    *, provider_id: str, model_name: str, category: str
) -> ChartDrilldownRequest:
    """Narrow the Details tab to a grouped sub-bar's ``(model, category)`` pair.

    Details tab's ``apply_drilldown`` (STORY-063) does not yet consume this
    request's ``category`` field -- see this story's Notes section for why
    the field was added anyway (the request shape) without a matching
    Details-tab consumer, which is out of this story's scope.

    Args:
        provider_id: The clicked sub-bar's model's provider id.
        model_name: The clicked sub-bar's model name.
        category: The clicked sub-bar's task category.

    Returns:
        A drill-down request narrowing the Models and Category chips to that
        pair (charts_tab.md#8, chart 10).
    """
    return ChartDrilldownRequest(provider_id=provider_id, model_name=model_name, category=category)
