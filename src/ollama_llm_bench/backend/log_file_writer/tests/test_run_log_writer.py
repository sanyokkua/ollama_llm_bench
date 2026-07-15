"""Colocated tests for the per-run event-log writer — STORY-037-AC-1."""

from pathlib import Path

from ollama_llm_bench.backend.domain import RunLogEvent, RunLogEventKind
from ollama_llm_bench.backend.log_file_writer import make_run_log_writer
from ollama_llm_bench.backend.log_file_writer.tests.conftest import FakePlatformDetector


def test_per_run_file_name_and_verbose_field_set(
    tmp_path: Path, fake_platform_detector: FakePlatformDetector
) -> None:
    """Proves: STORY-037-AC-1

    The per-run writer targets ``run_<run_id>_<unix_ts>.log`` under
    ``<app-data>/logs/run/``, and the written line carries Verbose-only fields (TTFT,
    tokens per second) regardless of any on-screen verbosity setting — there is none on
    this writer, which is the point.
    """
    writer = make_run_log_writer(
        platform_detector=fake_platform_detector, run_id="42", unix_ts=1747407187
    )
    event = RunLogEvent(
        kind=RunLogEventKind.DONE,
        timestamp="2026-05-22T14:53:27Z",
        ttft_ms=310,
        tokens_per_second=42.5,
    )

    outcome = writer.write_event(event)

    expected_path = fake_platform_detector.app_data_root / "logs" / "run" / "run_42_1747407187.log"
    assert outcome.succeeded is True
    assert expected_path.exists()
    content = expected_path.read_text(encoding="utf-8")
    assert "ttft_ms=310" in content
    assert "tokens_per_second=42.5" in content
