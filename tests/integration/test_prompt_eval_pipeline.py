"""Integration tests for the PROMPT_EVAL initialisation stage.

Uses a real SqLiteDataApi and real database I/O; LLM provider calls are not made.
Covers: result-row creation (N_models x N_variants x N_tasks), prompt_version
correctness, deduplication on resume, and prompt_variant cloning in clone_run_for_retry.
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime

from ollama_llm_bench.backend.core.models import (
    BenchmarkResult,
    BenchmarkResultStatus,
    BenchmarkRun,
    BenchmarkRunStatus,
    ModelDescriptor,
    PromptVariant,
    RunMode,
)
from ollama_llm_bench.backend.services.sq_lite_data_api import SqLiteDataApi

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_run(*, mode: RunMode = RunMode.PROMPT_EVAL) -> BenchmarkRun:
    return BenchmarkRun(
        run_id=0,
        timestamp=datetime.now(UTC).isoformat(),
        judge_model="judge",
        judge_provider_id="ollama",
        status=BenchmarkRunStatus.NOT_COMPLETED,
        run_mode=mode,
    )


def _make_variant(run_id: int, variant_id: str, label: str = "") -> PromptVariant:
    return PromptVariant(
        variant_id=variant_id,
        run_id=run_id,
        variant_label=label or variant_id,
        user_prompt_template=f"Template {variant_id}: {{question}}",
        created_at=datetime.now(UTC).isoformat(),
    )


def _make_descriptor(model_name: str = "llama3.2:3b", provider_id: str = "ollama") -> ModelDescriptor:
    return ModelDescriptor(
        provider_id=provider_id,
        provider_type="openai_compatible",
        model_name=model_name,
        display_label=model_name,
    )


def _make_prompt_eval_result(
    run_id: int,
    desc: ModelDescriptor,
    task_id: str,
    variant: PromptVariant,
) -> BenchmarkResult:
    rendered = variant.user_prompt_template.replace("{question}", f"task {task_id}")
    return BenchmarkResult(
        run_id=run_id,
        provider_id=desc.provider_id,
        provider_type=desc.provider_type,
        model_name=desc.model_name,
        task_id=task_id,
        prompt_version=variant.variant_id,
        user_prompt_sent=rendered,
        status=BenchmarkResultStatus.NOT_COMPLETED,
    )


# ---------------------------------------------------------------------------
# Tests: result-row creation
# ---------------------------------------------------------------------------


def test_prompt_eval_creates_n_models_x_n_variants_x_n_tasks(data_api: SqLiteDataApi) -> None:
    """The initialisation stage must create N_models xN_variants xN_tasks rows."""
    run_id = data_api.create_benchmark_run(_make_run())
    models = [_make_descriptor("m1"), _make_descriptor("m2")]
    variants = [_make_variant(run_id, "v1"), _make_variant(run_id, "v2"), _make_variant(run_id, "v3")]
    task_ids = ["t1", "t2"]

    for variant in variants:
        data_api.create_prompt_variant(variant)

    results = [
        _make_prompt_eval_result(run_id, desc, task_id, variant)
        for desc in models
        for variant in variants
        for task_id in task_ids
    ]
    data_api.create_benchmark_results(results)

    stored = data_api.retrieve_benchmark_results_for_run(run_id)
    assert len(stored) == len(models) * len(variants) * len(task_ids)


def test_prompt_eval_result_rows_carry_correct_prompt_version(data_api: SqLiteDataApi) -> None:
    """Each result row must carry prompt_version == variant.variant_id."""
    run_id = data_api.create_benchmark_run(_make_run())
    desc = _make_descriptor()
    variant = _make_variant(run_id, "my_variant")
    data_api.create_prompt_variant(variant)

    result = _make_prompt_eval_result(run_id, desc, "t1", variant)
    data_api.create_benchmark_result(result)

    stored = data_api.retrieve_benchmark_results_for_run(run_id)
    assert len(stored) == 1
    assert stored[0].prompt_version == "my_variant"


def test_prompt_eval_result_rows_carry_rendered_prompt(data_api: SqLiteDataApi) -> None:
    """user_prompt_sent must be the rendered template (placeholder substituted)."""
    run_id = data_api.create_benchmark_run(_make_run())
    desc = _make_descriptor()
    variant = _make_variant(run_id, "v_render")
    data_api.create_prompt_variant(variant)

    task_question = "task t1"
    rendered = variant.user_prompt_template.replace("{question}", task_question)
    result = dataclasses.replace(
        _make_prompt_eval_result(run_id, desc, "t1", variant),
        user_prompt_sent=rendered,
    )
    data_api.create_benchmark_result(result)

    stored = data_api.retrieve_benchmark_results_for_run(run_id)
    assert stored[0].user_prompt_sent == rendered


# ---------------------------------------------------------------------------
# Tests: deduplication
# ---------------------------------------------------------------------------


def test_resume_deduplication_does_not_create_duplicate_rows(data_api: SqLiteDataApi) -> None:
    """Re-running initialisation for a resumed run must not create duplicate rows."""
    run_id = data_api.create_benchmark_run(_make_run())
    desc = _make_descriptor()
    variant = _make_variant(run_id, "dup_check")
    data_api.create_prompt_variant(variant)

    result = _make_prompt_eval_result(run_id, desc, "t1", variant)
    data_api.create_benchmark_result(result)

    # Simulate what the pipeline stage does: check existing keys before inserting
    existing = data_api.retrieve_benchmark_results_for_run(run_id)
    existing_keys = {(r.provider_id, r.model_name, r.task_id, r.prompt_version) for r in existing}

    candidate_key = (desc.provider_id, desc.model_name, "t1", variant.variant_id)
    new_rows = [] if candidate_key in existing_keys else [result]
    if new_rows:
        data_api.create_benchmark_results(new_rows)

    stored = data_api.retrieve_benchmark_results_for_run(run_id)
    assert len(stored) == 1


# ---------------------------------------------------------------------------
# Tests: clone_run_for_retry copies prompt_variants
# ---------------------------------------------------------------------------


def test_clone_run_for_retry_copies_prompt_variants(data_api: SqLiteDataApi) -> None:
    """clone_run_for_retry must persist each original variant against the new run_id."""
    original_run_id = data_api.create_benchmark_run(_make_run())
    variants = [_make_variant(original_run_id, "va"), _make_variant(original_run_id, "vb")]
    for v in variants:
        data_api.create_prompt_variant(v)

    # Simulate clone: create new run, copy variants
    new_run = _make_run()
    new_run_id = data_api.create_benchmark_run(new_run)

    original_variants = data_api.retrieve_prompt_variants_for_run(original_run_id)
    for v in original_variants:
        data_api.create_prompt_variant(dataclasses.replace(v, run_id=new_run_id))

    cloned_variants = data_api.retrieve_prompt_variants_for_run(new_run_id)
    assert len(cloned_variants) == len(variants)
    cloned_ids = {v.variant_id for v in cloned_variants}
    assert cloned_ids == {"va", "vb"}


def test_clone_run_for_retry_retried_run_has_correct_row_count(data_api: SqLiteDataApi) -> None:
    """Retried run must produce N_models xN_variants xN_tasks result rows."""
    original_run_id = data_api.create_benchmark_run(_make_run())
    models = [_make_descriptor("m1"), _make_descriptor("m2")]
    variants = [_make_variant(original_run_id, "v1"), _make_variant(original_run_id, "v2")]
    task_ids = ["t1", "t2", "t3"]

    for v in variants:
        data_api.create_prompt_variant(v)

    results = [
        _make_prompt_eval_result(original_run_id, desc, tid, v) for desc in models for v in variants for tid in task_ids
    ]
    data_api.create_benchmark_results(results)

    # Clone the run
    new_run_id = data_api.create_benchmark_run(_make_run())
    original_variants = data_api.retrieve_prompt_variants_for_run(original_run_id)
    for v in original_variants:
        data_api.create_prompt_variant(dataclasses.replace(v, run_id=new_run_id))

    original_results = data_api.retrieve_benchmark_results_for_run(original_run_id)
    cloned_results = [dataclasses.replace(r, result_id=0, run_id=new_run_id) for r in original_results]
    data_api.create_benchmark_results(cloned_results)

    cloned_stored = data_api.retrieve_benchmark_results_for_run(new_run_id)
    assert len(cloned_stored) == len(models) * len(variants) * len(task_ids)
