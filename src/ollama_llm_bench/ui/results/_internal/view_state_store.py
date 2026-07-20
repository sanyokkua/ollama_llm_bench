"""``PerRunViewStateStore`` -- per-``run_id`` slice storage for the four Result
widget tabs (STORY-061-AC-6).

Source of truth: ``docs/v3_specification/05_Result_Widget/description.md`` §9 (per-run
table and chart view state) and §11 (persistence). No per-run view-state table exists
in the persistence schema; the store persists through the gateway's
``get_setting``/``set_setting`` (D-R-06), keyed
``ui.result_view_state.<slice_key>.<run_id>`` (this story's own naming decision -- kept
stable for the tab stories that will reuse it).
"""

from collections.abc import Callable

import structlog

from ollama_llm_bench.backend.domain import RunId, RunMode
from ollama_llm_bench.ui.results.protocols import ResultGateway

__all__: list[str] = ["PerRunViewStateStore"]

logger = structlog.get_logger(__name__)

_SETTING_KEY_TEMPLATE = "ui.result_view_state.{slice_key}.{run_id}"


class PerRunViewStateStore:
    """Per-``run_id`` slice storage, persisted through ``ResultGateway``.

    A tab requests its own slice by key; the store returns the mode-default slice
    on a run's first open, or the exact previously-stored slice on reopen. No slice
    ever crosses between runs -- each is keyed by ``(slice_key, run_id)``.
    """

    def __init__(self, *, gateway: ResultGateway) -> None:
        self._gateway = gateway

    def get_slice[T](
        self,
        *,
        run_id: RunId,
        slice_key: str,
        run_mode: RunMode,
        decoder: Callable[[str], T],
        default_factory: Callable[[RunMode], T],
    ) -> T:
        """Return the stored slice for ``(slice_key, run_id)``, or the mode default.

        Args:
            run_id: The run this slice belongs to.
            slice_key: The tab-owned slice identifier (e.g. ``"summary.filters"``).
            run_mode: The run's mode, passed to ``default_factory`` on first open.
            decoder: Parses a previously-stored setting value back into ``T``.
            default_factory: Builds the built-in default slice for a run's mode.

        Returns:
            The decoded stored slice, or the mode default when none is stored yet.
        """
        key = _SETTING_KEY_TEMPLATE.format(slice_key=slice_key, run_id=run_id)
        stored = self._gateway.get_setting(key)
        logger.debug(
            "result_view_state_get", run_id=run_id, slice_key=slice_key, found=stored is not None
        )
        if stored is None:
            return default_factory(run_mode)
        return decoder(stored)

    def set_slice[T](
        self, *, run_id: RunId, slice_key: str, value: T, encoder: Callable[[T], str]
    ) -> None:
        """Persist a slice back against ``(slice_key, run_id)``.

        Args:
            run_id: The run this slice belongs to.
            slice_key: The tab-owned slice identifier.
            value: The slice value to persist.
            encoder: Serialises ``value`` to the stored setting string.
        """
        key = _SETTING_KEY_TEMPLATE.format(slice_key=slice_key, run_id=run_id)
        logger.debug("result_view_state_set", run_id=run_id, slice_key=slice_key)
        self._gateway.set_setting(key, encoder(value))
