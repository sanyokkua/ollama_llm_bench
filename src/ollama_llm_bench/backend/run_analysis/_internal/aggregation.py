"""The bounded run digest (§6.2)."""

from collections import Counter
from dataclasses import dataclass
from typing import Final

from ollama_llm_bench.backend.domain import (
    BenchmarkResult,
    BenchmarkRun,
    BenchmarkTask,
    ModelRole,
    ResultStatus,
    RunMode,
    Verdict,
)
from ollama_llm_bench.backend.errors import ContractViolationError

__all__: list[str] = [
    "CategoryDigestRow",
    "ModelDigestRow",
    "NotableResultEntry",
    "RunDigest",
    "RunFacts",
    "build_run_digest",
]

_NOTABLE_RESULTS_CAP: Final[int] = 12
_NONE_LABEL: Final[str] = "none"
_MIN_MODELS_FOR_MISCALIBRATION_SIGNAL: Final[int] = 2

_TERMINAL_FAILURE_STATUSES: Final[frozenset[ResultStatus]] = frozenset(
    {
        ResultStatus.FAILED_INFERENCE,
        ResultStatus.FAILED_PROVIDER,
        ResultStatus.FAILED_TIMEOUT,
        ResultStatus.FAILED_JUDGE_TIMEOUT,
        ResultStatus.ERRORED,
    }
)
_TERMINAL_STATUSES: Final[frozenset[ResultStatus]] = _TERMINAL_FAILURE_STATUSES | frozenset(
    {ResultStatus.COMPLETED}
)


@dataclass(slots=True, frozen=True)
class RunFacts:
    """The run-level facts row of the digest (§6.2)."""

    run_mode: RunMode
    test_model_labels: tuple[str, ...]
    judge_model_label: str
    embedding_model_label: str
    started_at: str | None
    finished_at: str | None
    total_elapsed_ms: int
    total_tasks: int
    completed_tasks: int


@dataclass(slots=True, frozen=True)
class ModelDigestRow:
    """One test model's aggregated row (§6.2)."""

    provider_id: str
    model_name: str
    label: str
    task_count: int
    completed_count: int
    error_count: int
    mean_ttft_ms: float | None
    mean_total_time_ms: float | None
    mean_tokens_per_second: float | None
    pass_count: int | None
    fail_count: int | None
    pass_rate: float | None
    mean_cosine_similarity: float | None
    resolution_layer_counts: dict[str, int] | None


@dataclass(slots=True, frozen=True)
class CategoryDigestRow:
    """One task category's aggregated row (§6.2, ``GRADED`` runs only)."""

    category: str
    pass_rate: float
    result_count: int


@dataclass(slots=True, frozen=True)
class NotableResultEntry:
    """One shortlisted notable result or task-level signal (§6.2)."""

    task_id: str
    provider_id: str
    model_name: str
    verdict: str | None
    note: str


@dataclass(slots=True, frozen=True)
class RunDigest:
    """The compact, deterministic, bounded digest fed to the analysis prompt (§6.2)."""

    facts: RunFacts
    per_model: tuple[ModelDigestRow, ...]
    per_category: tuple[CategoryDigestRow, ...]
    notable_results: tuple[NotableResultEntry, ...]


def build_run_digest(
    *,
    run: BenchmarkRun,
    results: tuple[BenchmarkResult, ...],
    tasks_by_id: dict[str, BenchmarkTask],
) -> RunDigest:
    """Aggregate a finished run into a compact, bounded, deterministic digest (§6.2).

    Args:
        run: The run header, with its frozen model/provider snapshots.
        results: Every result row belonging to ``run``.
        tasks_by_id: Every task belonging to ``run``, keyed by ``task_id``.

    Returns:
        The bounded digest fed to the mode-aware prompt builder.

    Raises:
        ContractViolationError: A result's ``task_id`` is absent from
            ``tasks_by_id`` — the caller must supply complete task metadata (§8).
    """
    for result in results:
        if result.task_id not in tasks_by_id:
            raise ContractViolationError(
                message=(
                    f"result {result.result_id} references task_id {result.task_id!r}, "
                    "which is absent from tasks_by_id"
                )
            )
    provider_names = {p.provider_id: p.name for p in run.providers}
    return RunDigest(
        facts=_build_facts(run, provider_names),
        per_model=_build_per_model_rows(run, results, provider_names),
        per_category=_build_per_category_rows(run, results, tasks_by_id),
        notable_results=_build_notable_results(run, results),
    )


def _label(provider_names: dict[str, str], provider_id: str, model_name: str) -> str:
    return f"{provider_names.get(provider_id, provider_id)}/{model_name}"


def _build_facts(run: BenchmarkRun, provider_names: dict[str, str]) -> RunFacts:
    test_entries = tuple(e for e in run.models if e.role == ModelRole.TEST)
    judge_entries = tuple(e for e in run.models if e.role == ModelRole.JUDGE)
    embedding_entries = tuple(e for e in run.models if e.role == ModelRole.EMBEDDING)
    judge_label = (
        _label(provider_names, judge_entries[0].provider_id, judge_entries[0].model_name)
        if judge_entries
        else _NONE_LABEL
    )
    embedding_label = (
        _label(provider_names, embedding_entries[0].provider_id, embedding_entries[0].model_name)
        if embedding_entries
        else _NONE_LABEL
    )
    return RunFacts(
        run_mode=run.run_mode,
        test_model_labels=tuple(
            _label(provider_names, e.provider_id, e.model_name) for e in test_entries
        ),
        judge_model_label=judge_label,
        embedding_model_label=embedding_label,
        started_at=run.started_at,
        finished_at=run.finished_at,
        total_elapsed_ms=run.total_elapsed_ms,
        total_tasks=run.total_tasks,
        completed_tasks=run.completed_tasks,
    )


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _build_per_model_rows(
    run: BenchmarkRun,
    results: tuple[BenchmarkResult, ...],
    provider_names: dict[str, str],
) -> tuple[ModelDigestRow, ...]:
    test_entries = tuple(e for e in run.models if e.role == ModelRole.TEST)
    rows: list[ModelDigestRow] = []
    for entry in test_entries:
        group = [
            r
            for r in results
            if r.provider_id == entry.provider_id and r.model_name == entry.model_name
        ]
        rows.append(
            _build_one_model_row(run, entry.provider_id, entry.model_name, group, provider_names)
        )
    return tuple(rows)


def _build_one_model_row(
    run: BenchmarkRun,
    provider_id: str,
    model_name: str,
    group: list[BenchmarkResult],
    provider_names: dict[str, str],
) -> ModelDigestRow:
    completed = [r for r in group if r.status == ResultStatus.COMPLETED]
    errored = [r for r in group if r.status in _TERMINAL_FAILURE_STATUSES]
    mean_ttft = _mean([float(r.ttft_ms) for r in group if r.ttft_ms is not None])
    mean_total_time = _mean([float(r.total_time_ms) for r in group if r.total_time_ms is not None])
    mean_tps = _mean([r.tokens_per_second for r in group if r.tokens_per_second is not None])
    pass_count: int | None = None
    fail_count: int | None = None
    pass_rate: float | None = None
    mean_cosine: float | None = None
    resolution_layer_counts: dict[str, int] | None = None
    if run.run_mode == RunMode.GRADED:
        pass_count = sum(1 for r in group if r.verdict == Verdict.PASS)
        fail_count = sum(1 for r in group if r.verdict == Verdict.FAIL)
        total_verdicts = pass_count + fail_count
        pass_rate = pass_count / total_verdicts if total_verdicts > 0 else None
        mean_cosine = _mean([r.cosine_similarity for r in group if r.cosine_similarity is not None])
        resolution_layer_counts = dict(
            Counter(r.resolution_layer.value for r in group if r.resolution_layer is not None)
        )
    return ModelDigestRow(
        provider_id=provider_id,
        model_name=model_name,
        label=_label(provider_names, provider_id, model_name),
        task_count=len(group),
        completed_count=len(completed),
        error_count=len(errored),
        mean_ttft_ms=mean_ttft,
        mean_total_time_ms=mean_total_time,
        mean_tokens_per_second=mean_tps,
        pass_count=pass_count,
        fail_count=fail_count,
        pass_rate=pass_rate,
        mean_cosine_similarity=mean_cosine,
        resolution_layer_counts=resolution_layer_counts,
    )


def _build_per_category_rows(
    run: BenchmarkRun,
    results: tuple[BenchmarkResult, ...],
    tasks_by_id: dict[str, BenchmarkTask],
) -> tuple[CategoryDigestRow, ...]:
    if run.run_mode != RunMode.GRADED:
        return ()
    by_category: dict[str, list[BenchmarkResult]] = {}
    for result in results:
        category = tasks_by_id[result.task_id].category
        if not category:
            continue
        by_category.setdefault(category, []).append(result)
    rows: list[CategoryDigestRow] = []
    for category, group in by_category.items():
        pass_count = sum(1 for r in group if r.verdict == Verdict.PASS)
        fail_count = sum(1 for r in group if r.verdict == Verdict.FAIL)
        total_verdicts = pass_count + fail_count
        if total_verdicts == 0:
            continue
        rows.append(
            CategoryDigestRow(
                category=category,
                pass_rate=pass_count / total_verdicts,
                result_count=len(group),
            )
        )
    return tuple(rows)


def _build_notable_results(
    run: BenchmarkRun, results: tuple[BenchmarkResult, ...]
) -> tuple[NotableResultEntry, ...]:
    entries: dict[tuple[str, str, str], NotableResultEntry] = {}

    def _add(result: BenchmarkResult, note: str) -> None:
        key = (result.task_id, result.provider_id, result.model_name)
        if key not in entries:
            entries[key] = NotableResultEntry(
                task_id=result.task_id,
                provider_id=result.provider_id,
                model_name=result.model_name,
                verdict=result.verdict.value if result.verdict is not None else None,
                note=note,
            )

    for result in results:
        if result.status in _TERMINAL_FAILURE_STATUSES:
            _add(result, f"terminal failure: {result.status.value}")
        elif result.verdict == Verdict.FAIL:
            _add(result, "verdict: FAIL")
        elif (
            result.keyword_verdict is not None
            and result.judge_verdict is not None
            and result.keyword_verdict != result.judge_verdict
        ):
            _add(
                result,
                f"layer disagreement: keyword={result.keyword_verdict.value} "
                f"judge={result.judge_verdict.value}",
            )

    timed_results = [r for r in results if r.total_time_ms is not None]
    if timed_results:
        slowest = max(timed_results, key=lambda r: r.total_time_ms or 0)
        fastest = min(timed_results, key=lambda r: r.total_time_ms or 0)
        _add(slowest, f"slowest result: {slowest.total_time_ms}ms")
        _add(fastest, f"fastest result: {fastest.total_time_ms}ms")

    entries.update(_miscalibration_signals(run, results))

    ordered = list(entries.values())[:_NOTABLE_RESULTS_CAP]
    return tuple(ordered)


def _miscalibration_signals(
    run: BenchmarkRun, results: tuple[BenchmarkResult, ...]
) -> dict[tuple[str, str, str], NotableResultEntry]:
    test_model_count = sum(1 for e in run.models if e.role == ModelRole.TEST)
    if test_model_count < _MIN_MODELS_FOR_MISCALIBRATION_SIGNAL:
        return {}
    by_task: dict[str, list[BenchmarkResult]] = {}
    for result in results:
        by_task.setdefault(result.task_id, []).append(result)
    signals: dict[tuple[str, str, str], NotableResultEntry] = {}
    for task_id, group in by_task.items():
        fail_count = sum(1 for r in group if r.verdict == Verdict.FAIL)
        if fail_count == test_model_count:
            signals[(task_id, "*", "*")] = NotableResultEntry(
                task_id=task_id,
                provider_id="*",
                model_name="*",
                verdict=Verdict.FAIL.value,
                note=(
                    f"all {test_model_count} models failed this task — the golden answer "
                    "or criteria may be mis-specified."
                ),
            )
    return signals
