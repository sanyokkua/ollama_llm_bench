"""Colocated unit tests for ``PerRunViewStateStore`` (STORY-061-AC-6)."""

import msgspec

from ollama_llm_bench.backend.domain import RunMode
from ollama_llm_bench.ui.results._internal.view_state_store import PerRunViewStateStore
from ollama_llm_bench.ui.results.tests.conftest import FakeResultGateway


class _FixtureSlice(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """A small test-local slice type standing in for a real tab's view state."""

    filter_text: str
    column_order: tuple[str, ...]


def _default_factory(run_mode: RunMode) -> _FixtureSlice:
    columns = ("a", "b") if run_mode is RunMode.TASKS else ()
    return _FixtureSlice(filter_text="", column_order=columns)


def _encode(value: _FixtureSlice) -> str:
    return msgspec.json.encode(value).decode("utf-8")


def _decode(raw: str) -> _FixtureSlice:
    return msgspec.json.decode(raw.encode("utf-8"), type=_FixtureSlice)


def test_first_open_defaults_vs_reopen_restore() -> None:
    """Proves: STORY-061-AC-6

    A run opened for the first time gets the mode-default slice; a previously
    stored slice is decoded and returned exactly on reopen; two different run
    ids never cross slices.
    """
    # Arrange
    gateway = FakeResultGateway()
    store = PerRunViewStateStore(gateway=gateway)
    # Act -- first open of run 1: no stored setting yet
    first_open = store.get_slice(
        run_id=1,
        slice_key="summary.filters",
        run_mode=RunMode.TASKS,
        decoder=_decode,
        default_factory=_default_factory,
    )
    # Assert
    assert first_open == _FixtureSlice(filter_text="", column_order=("a", "b"))
    # Act -- the user changes the slice and it is persisted
    changed = _FixtureSlice(filter_text="pass_only", column_order=("b", "a"))
    store.set_slice(run_id=1, slice_key="summary.filters", value=changed, encoder=_encode)
    reopened = store.get_slice(
        run_id=1,
        slice_key="summary.filters",
        run_mode=RunMode.TASKS,
        decoder=_decode,
        default_factory=_default_factory,
    )
    # Assert -- reopen restores the exact stored slice
    assert reopened == changed
    # Act -- a different run id never sees run 1's stored slice
    other_run_default = store.get_slice(
        run_id=2,
        slice_key="summary.filters",
        run_mode=RunMode.TASKS,
        decoder=_decode,
        default_factory=_default_factory,
    )
    # Assert
    assert other_run_default == _FixtureSlice(filter_text="", column_order=("a", "b"))
    assert other_run_default != reopened
