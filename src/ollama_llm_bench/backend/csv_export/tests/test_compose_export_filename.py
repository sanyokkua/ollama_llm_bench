"""Export-filename sanitisation property tests (`05_EXPORT_FORMATS.md` §2.1, SPEC-064)."""

import re

from hypothesis import example, given, strategies as st
import pytest

from ollama_llm_bench.backend.csv_export import ExportKind, compose_export_filename

_ALLOWED_NAME_CHARS_PATTERN = re.compile(r"^[A-Za-z0-9._-]+$")
_MAX_NAME_SEGMENT_LENGTH = 80

# Characters that can never survive sanitisation: none is alphanumeric or `-`, so a
# run name built solely from this alphabet always sanitises to an empty string
# (`_` runs collapse/strip, `.` strips only when leading, everything else in this
# alphabet is replaced by `_`) — see `sanitise_run_name` (`19_TABLE_SERIALIZATION.md`
# §2.1, SPEC-064).
_UNSURVIVABLE_ALPHABET = " ./\\:;!@#$%^&*()[]{}<>?,~`+='\"|\n\t"


def _name_segment_of(filename: str) -> str:
    """Strip the fixed `_Summary.csv` suffix this test always composes with."""
    return filename.removesuffix(f"_{ExportKind.SUMMARY.value}.csv")


@pytest.mark.slow
@pytest.mark.property
@given(run_name=st.text(max_size=200), run_id=st.integers(min_value=1, max_value=1_000_000))
@example(run_name="../../etc/passwd", run_id=7)
@example(run_name="....", run_id=7)
@example(run_name="a" * 200, run_id=7)
def test_filename_is_traversal_safe_and_bounded(run_name: str, run_id: int) -> None:
    """Proves: STORY-032-AC-3

    For every export-filename input, `compose_export_filename` produces a name
    containing only characters in `[A-Za-z0-9._-]` plus the kind/extension
    separators, never beginning with `.`, never equal to `.` or `..`, and
    truncated to at most 80 characters for the run-name segment.
    """
    filename = compose_export_filename(
        run_name=run_name, run_id=run_id, kind=ExportKind.SUMMARY, ext="csv"
    )

    name_segment = _name_segment_of(filename)

    assert filename == f"{name_segment}_{ExportKind.SUMMARY.value}.csv"
    assert _ALLOWED_NAME_CHARS_PATTERN.match(name_segment) is not None
    assert not name_segment.startswith(".")
    assert name_segment not in {".", ".."}
    assert len(name_segment) <= _MAX_NAME_SEGMENT_LENGTH


@pytest.mark.slow
@pytest.mark.property
@given(
    run_name=st.text(alphabet=_UNSURVIVABLE_ALPHABET, max_size=50),
    run_id=st.integers(min_value=1, max_value=1_000_000),
)
@example(run_name="", run_id=7)
@example(run_name="   ", run_id=7)
def test_filename_falls_back_when_sanitisation_yields_empty(run_name: str, run_id: int) -> None:
    """Proves: STORY-032-AC-3

    For every run name built entirely from characters with no alphanumeric or
    `-` survivor, `compose_export_filename` falls back to the `Run_<run_id>`
    name segment.
    """
    filename = compose_export_filename(
        run_name=run_name, run_id=run_id, kind=ExportKind.SUMMARY, ext="csv"
    )

    name_segment = _name_segment_of(filename)

    assert name_segment == f"Run_{run_id}"
