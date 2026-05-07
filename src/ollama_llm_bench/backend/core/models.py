"""V2 core domain models: frozen dataclasses and StrEnum definitions for benchmark data."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


class RunMode(StrEnum):
    """Execution mode for a benchmark run."""

    SPEED = "speed"
    FULL_GRADING = "full_grading"
    PROMPT_EVAL = "prompt_eval"
    PERFORMANCE = "performance"


class TaskType(StrEnum):
    """Primary evaluation routing key that determines which eval layers apply."""

    CODE_GENERATION = "code_generation"
    CODE_REVIEW = "code_review"
    REASONING = "reasoning"
    TRANSLATION = "translation"
    TEXT_REWRITE = "text_rewrite"
    FACTUAL_QA = "factual_qa"
    DATA_EXTRACTION = "data_extraction"
    SUMMARIZATION = "summarization"


class Difficulty(StrEnum):
    """Relative difficulty of a benchmark task used for results breakdown."""

    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class ResponseScope(StrEnum):
    """Cosine similarity matching strategy for Layer 3 evaluation."""

    EXACT = "exact"
    CONTAINS = "contains"
    COVERS = "covers"


class ProviderType(StrEnum):
    """Category of LLM provider used for routing and client construction."""

    OPENAI_COMPATIBLE = "openai_compatible"
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"


class BenchmarkRunStatus(StrEnum):
    """Status of a benchmark run indicating completion or failure state."""

    NOT_COMPLETED = "NOT_COMPLETED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class BenchmarkResultStatus(StrEnum):
    """Status of an individual benchmark result during execution and evaluation."""

    NOT_COMPLETED = "NOT_COMPLETED"
    WAITING_FOR_JUDGE = "WAITING_FOR_JUDGE"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class PipelineStage(StrEnum):
    """Pipeline execution stage for a benchmark run."""

    INITIALIZING = "Initializing"
    BENCHMARKING = "Benchmarking"
    JUDGING = "Judging"
    FINISHED = "Finished"
    FAILED = "Failed"


class EvalLayer(StrEnum):
    """Evaluation pipeline layer identifier."""

    RULE_BASED = "rule_based"
    KEYWORD = "keyword"
    COSINE = "cosine"
    LLM_JUDGE = "llm_judge"


class EvalVerdict(StrEnum):
    """Verdict produced by an evaluation layer."""

    PASS = "pass"
    FAIL = "fail"
    UNKNOWN = "unknown"


class PromptInputSize(StrEnum):
    """Input token-size tier for performance benchmark prompts."""

    TINY = "tiny"
    SMALL = "small"
    MEDIUM = "medium"
    LARGE = "large"
    HUGE = "huge"


class PromptOutputSize(StrEnum):
    """Output-size tier controlling how many sentences the model must generate."""

    XS = "xs"
    SM = "sm"
    MD = "md"
    LG = "lg"
    XL = "xl"


class PauseReason(StrEnum):
    """Reason a benchmark run was paused."""

    USER = "user"
    EVENT_POLICY = "event_policy"
    PROVIDER_ERROR = "provider_error"


class StopReason(StrEnum):
    """Reason a benchmark run was stopped before completion."""

    USER = "user"
    FATAL_ERROR = "fatal_error"


class LogEntryType(StrEnum):
    """Type of structured log entry emitted during benchmark execution."""

    TASK_START = "task_start"
    PROMPT = "prompt"
    STREAM_CHUNK = "stream_chunk"
    THINKING_BLOCK = "thinking_block"
    INFERENCE_COMPLETE = "inference_complete"
    JUDGE_RESULT = "judge_result"
    ERROR = "error"
    SYSTEM = "system"


@dataclass(frozen=True, slots=True, kw_only=True)
class PerformanceConfig:
    """Matrix configuration for Performance run mode."""

    input_sizes: tuple[PromptInputSize, ...]
    output_sizes: tuple[PromptOutputSize, ...]
    repeat_count: int


@dataclass(frozen=True, kw_only=True)
class RequiredTerms:
    """Term constraints used by the Layer 2 keyword evaluator."""

    exact: tuple[str, ...] = ()
    semantic: tuple[str, ...] = ()
    forbidden: tuple[str, ...] = ()


@dataclass(frozen=True, kw_only=True)
class BenchmarkTask:
    """V2 benchmark task definition with evaluation metadata and grading criteria."""

    task_id: str
    category: str
    sub_category: str
    task_type: TaskType
    question: str
    golden_answer: str
    pass_criteria: str
    fail_criteria: str
    difficulty: Difficulty | None = None
    response_scope: ResponseScope | None = None
    required_terms: RequiredTerms | None = None
    source_language: str | None = None
    target_language: str | None = None
    source_material: str | None = None
    fail_example: str | None = None


@dataclass(frozen=True, kw_only=True)
class BenchmarkRun:
    """Immutable representation of a benchmark run with metadata and status."""

    run_id: int
    timestamp: str
    judge_model: str
    status: BenchmarkRunStatus
    run_mode: RunMode = RunMode.FULL_GRADING
    judge_provider_id: str = ""
    embedding_provider_id: str | None = None
    embedding_model: str | None = None
    task_file_paths: tuple[str, ...] = ()
    models_json: str = "[]"
    total_tasks: int = 0
    completed_tasks: int = 0
    judge_summary: str | None = None
    performance_config: str | None = None
    perf_analysis_result: str | None = None
    run_name: str | None = None


@dataclass(frozen=True, kw_only=True)
class BenchmarkResult:
    """V2 benchmark result capturing inference metrics, evaluation layers, and final verdict."""

    # Group 1 — Record Identity
    result_id: int = 0
    run_id: int = 0
    run_type: str = ""
    created_at: str = ""
    completed_at: str | None = None

    # Group 2 — Provider & Model Identity
    provider_id: str = ""
    provider_type: str = ""
    model_name: str = ""
    model_family: str | None = None
    model_size_b: float | None = None
    quantization_label: str | None = None

    # Group 3 — Task Identity
    task_id: str = ""
    task_category: str = ""
    task_type: str = ""
    task_difficulty: str | None = None
    response_scope: str | None = None
    source_language: str | None = None
    target_language: str | None = None

    # Group 4 — Prompt Snapshot
    prompt_version: str = "v1"
    prompt_hash: str = ""
    user_prompt_sent: str = ""
    system_prompt_sent: str | None = None
    golden_answer: str = ""

    # Group 5 — Raw Inference Output
    raw_response: str | None = None
    sanitized_response: str | None = None
    response_char_length: int | None = None
    has_thinking_block: bool = False

    # Group 6 — Performance Metrics
    status: BenchmarkResultStatus = BenchmarkResultStatus.NOT_COMPLETED
    total_time_ms: int | None = None
    ttft_ms: int | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    tokens_per_second: float | None = None

    # Group 7 — Layer 1: Rule-Based
    rule_check_result: str | None = None
    rule_check_flag: str | None = None
    rule_check_resolved: bool = False

    # Group 8 — Layer 2: Keyword
    keyword_check_result: str | None = None
    missing_exact_terms: str | None = None
    found_forbidden_terms: str | None = None
    semantic_term_scores: str | None = None
    keyword_check_resolved: bool = False

    # Group 9 — Layer 3: Cosine Similarity
    cosine_similarity: float | None = None
    cosine_embedding_model: str | None = None
    cosine_strategy: str | None = None
    cosine_auto_pass: bool = False
    cosine_resolved: bool = False

    # Group 10 — Layer 4: LLM Judge
    judge_result: str | None = None
    judge_score: float | None = None
    judge_reasoning: str | None = None
    judge_prompt_template: str | None = None
    judge_time_ms: int | None = None
    judge_completion_tokens: int | None = None

    # Group 11 — Final Verdict
    final_verdict: str | None = None
    resolution_layer: str | None = None

    # Group 12 — Error Tracking
    has_inference_error: bool = False
    inference_error_message: str | None = None
    has_judge_error: bool = False
    judge_error_message: str | None = None


@dataclass(frozen=True, kw_only=True)
class PromptVariant:
    """Prompt variant record used in prompt_eval run mode to test template alternatives."""

    variant_id: str
    run_id: int
    variant_label: str
    user_prompt_template: str
    created_at: str
    system_prompt: str | None = None


@dataclass(frozen=True, kw_only=True)
class AppSetting:
    """Key-value application setting persisted in the app_settings table."""

    key: str
    value: str
    updated_at: str


@dataclass(frozen=True, kw_only=True)
class ProviderConfig:
    """Configuration for a single LLM provider endpoint."""

    provider_id: str
    label: str
    provider_type: ProviderType
    api_key: str
    api_key_raw: str = ""
    azure_deployment: str | None = None
    azure_api_version: str | None = None
    enabled: bool = True
    base_url: str | None = None
    default_models: tuple[str, ...] = ()


@dataclass(frozen=True, kw_only=True)
class EmbeddingConfig:
    """Configuration for the embedding provider used in cosine similarity evaluation."""

    provider_id: str
    model: str


@dataclass(frozen=True, kw_only=True)
class ProvidersConfig:
    """Root configuration object loaded from providers.yaml."""

    providers: tuple[ProviderConfig, ...]
    embedding: EmbeddingConfig


@dataclass(frozen=True, kw_only=True)
class ProviderRegistryReloadedEvent:
    """Event emitted after the provider registry is reloaded from disk."""


@dataclass(frozen=True, slots=True, kw_only=True)
class PreviousRunsRefreshedEvent:
    """Event emitted after the Previous Runs list is refreshed from the database."""


@dataclass(frozen=True, slots=True, kw_only=True)
class ModelDescriptor:
    """Resolved model identity combining provider metadata and parsed model name parts."""

    provider_id: str
    provider_type: str
    model_name: str
    display_label: str
    model_family: str | None = None
    model_size_b: float | None = None
    quantization_label: str | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class ParsedModelName:
    """Structured result of parsing an Ollama-style model name string."""

    model_family: str | None = None
    model_size_b: float | None = None
    quantization_label: str | None = None


@dataclass(frozen=True)
class AvgSummaryTableItem:
    """Aggregated performance metrics for a model across all tasks in a run."""

    model_name: str = ""
    avg_time_ms: float = 0.0
    avg_tokens_per_second: float = 0.0
    avg_score: float = 0.0
    avg_ttft_ms: float | None = None
    pass_rate: float = 0.0


@dataclass(frozen=True)
class SummaryTableItem:
    """Detailed performance metrics for a model on a specific task within a run."""

    model_name: str = ""
    task_id: str = ""
    task_category: str = ""
    task_status: str = ""
    time_ms: int = 0
    tokens: int = 0
    tokens_per_second: float = 0.0
    score: float = 0.0
    score_reason: str = ""
    cosine_similarity: float | None = None
    resolution_layer: str = ""


@dataclass(frozen=True)
class InferenceResponse:
    """Response from an LLM inference call, including generated content and metadata."""

    llm_response: str = ""
    total_time_ms: int = 0
    completion_tokens: int = 0
    prompt_tokens: int | None = None
    ttft_ms: int | None = None
    has_error: bool = False
    error_message: str | None = None


@dataclass(frozen=True, slots=True)
class StreamChunk:
    """A single token delta emitted during streaming inference."""

    delta_content: str
    is_final: bool = False
    finish_reason: str | None = None


@dataclass(frozen=True)
class ReporterStatusMsg:
    """Status message broadcast during benchmark execution to report progress."""

    current_run_id: int
    current_stage: str = ""
    current_model: str = ""
    current_task: str = ""
    tasks_total: int = 0
    tasks_completed: int = 0
    start_time_ms: float = 0
    end_time_ms: float = 0
    task_start_ms: float = 0


@dataclass(frozen=True, slots=True, kw_only=True)
class RunStartEvent:
    """Event object used to trigger a new benchmark run via the RunConfigPanel."""

    run_mode: RunMode
    judge_provider: str
    judge_model: str
    test_provider: str
    test_models: tuple[str, ...]
    task_paths: tuple[Path, ...]
    streaming_enabled: bool = True
    warmup_enabled: bool = True
    reasoning_effort: str = "default"
    performance_config: PerformanceConfig | None = None
    performance_analysis_enabled: bool = False


@dataclass(frozen=True, slots=True, kw_only=True)
class EvaluationResult:
    """Result produced by a single evaluation layer during the grading pipeline.

    The required fields capture the core verdict; the optional layer-specific
    metadata fields are populated only by the layer that produces them. Callers
    that construct ``EvaluationResult`` without keyword arguments for the
    metadata fields receive empty/None defaults — no existing call sites need
    updating.
    """

    verdict: EvalVerdict
    score: float  # 0.0 to 1.0
    reasoning: str
    is_terminal: bool  # True = this verdict terminates the eval pipeline
    layer: EvalLayer
    # Layer-specific metadata (all optional; empty/None = not applicable for this layer)
    missing_exact_terms: tuple[str, ...] = ()
    found_forbidden_terms: tuple[str, ...] = ()
    semantic_term_scores: tuple[float, ...] = ()
    judge_time_ms: int | None = None
    judge_completion_tokens: int | None = None
    judge_prompt_template: str | None = None


# Lifecycle events


@dataclass(frozen=True, slots=True, kw_only=True)
class BenchmarkStartedEvent:
    """Emitted when a benchmark run transitions from INITIALIZING to BENCHMARKING."""

    run_id: int
    total_tasks: int
    models: tuple[ModelDescriptor, ...]
    run_mode: RunMode
    run_name: str | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class BenchmarkPausedEvent:
    """Emitted when execution is paused at a stage boundary."""

    run_id: int
    pause_reason: PauseReason
    paused_at_stage: PipelineStage


@dataclass(frozen=True, slots=True, kw_only=True)
class BenchmarkResumedEvent:
    """Emitted when a paused benchmark run is resumed."""

    run_id: int


@dataclass(frozen=True, slots=True, kw_only=True)
class BenchmarkStoppedEvent:
    """Emitted when a benchmark run is stopped before completion."""

    run_id: int
    stop_reason: StopReason


@dataclass(frozen=True, slots=True, kw_only=True)
class BenchmarkFinishedEvent:
    """Emitted when a benchmark run completes all stages successfully."""

    run_id: int
    total_time_ms: float
    completed_count: int
    failed_count: int


# Switch events


@dataclass(frozen=True, slots=True, kw_only=True)
class ProviderSwitchEvent:
    """Emitted when the active inference provider changes between task groups."""

    run_id: int
    from_provider_id: str | None
    to_provider_id: str
    provider_label: str


@dataclass(frozen=True, slots=True, kw_only=True)
class ProviderHealthCheckEvent:
    """Emitted after a provider health check at the start of each provider group."""

    run_id: int
    provider_id: str
    is_healthy: bool
    error_message: str | None


@dataclass(frozen=True, slots=True, kw_only=True)
class ModelSwitchEvent:
    """Emitted when inference switches to a different model within a provider."""

    run_id: int
    from_model: str | None
    to_model: ModelDescriptor


@dataclass(frozen=True, slots=True, kw_only=True)
class TaskSwitchEvent:
    """Emitted when inference begins a new task for the current model."""

    run_id: int
    model: ModelDescriptor
    task_id: str
    task_category: str
    task_type: TaskType
    task_number: int
    tasks_total: int


@dataclass(frozen=True, slots=True, kw_only=True)
class TaskRetryEvent:
    """Emitted at the start of each retry attempt (not the first attempt)."""

    run_id: int
    task_id: str
    attempt: int
    total_attempts: int
    retry_reason: str = ""
    attempt_durations_ms: tuple[int, ...] = ()
    min_timeout_seconds: int = 0
    max_timeout_seconds: int = 0


@dataclass(frozen=True, slots=True, kw_only=True)
class ModeSwitchEvent:
    """Emitted when the pipeline transitions between execution stages."""

    run_id: int
    from_stage: PipelineStage
    to_stage: PipelineStage


# Completion events


@dataclass(frozen=True, slots=True, kw_only=True)
class TaskCompletedEvent:
    """Emitted when a single task's inference is complete."""

    run_id: int
    result_id: int
    model: ModelDescriptor
    task_id: str
    status: BenchmarkResultStatus
    total_time_ms: float | None
    ttft_ms: float | None
    final_verdict: str | None


@dataclass(frozen=True, slots=True, kw_only=True)
class JudgeStartedEvent:
    """Emitted when evaluation of a result begins at a specific layer."""

    run_id: int
    result_id: int
    layer: EvalLayer


@dataclass(frozen=True, slots=True, kw_only=True)
class JudgeCompletedEvent:
    """Emitted when an evaluation layer produces a verdict for a result."""

    run_id: int
    result_id: int
    layer: EvalLayer
    verdict: EvalVerdict
    resolved: bool  # True = terminal verdict produced
    task_id: str = ""
    reasoning: str | None = None
    score: float | None = None
    judge_model: str | None = None
    judge_provider_id: str | None = None
    judge_prompt_template: str | None = None
    resolution_layer: str | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class JudgeEvalStartedEvent:
    """Emitted once per result before the 4-layer evaluation pipeline begins."""

    run_id: int
    result_id: int
    task_id: str
    task_type: TaskType
    judge_provider_id: str
    judge_model: str
    result_number: int
    results_total: int


@dataclass(frozen=True, slots=True, kw_only=True)
class JudgeEvalRetryEvent:
    """Emitted at the start of each retry of the LLM judge call (not the first attempt)."""

    run_id: int
    task_id: str
    judge_model: str
    attempt: int
    total_attempts: int


# Inference started event


@dataclass(frozen=True, slots=True, kw_only=True)
class InferenceStartedEvent:
    """Emitted immediately before inference begins; carries the prompt for log display."""

    run_id: int
    result_id: int
    model: ModelDescriptor
    task_id: str
    user_prompt: str
    system_prompt: str | None
    stage: PipelineStage


# Streaming event


@dataclass(frozen=True, slots=True, kw_only=True)
class StreamingChunkEvent:
    """Emitted at 20 Hz max with buffered streaming token chunks."""

    run_id: int
    result_id: int
    model_name: str
    task_id: str
    chunk_text: str
    is_thinking_block: bool


# Progress event


@dataclass(frozen=True, slots=True, kw_only=True)
class JudgeSummaryEvent:
    """Emitted after a post-run judge summary is generated."""

    run_id: int
    summary_text: str


@dataclass(frozen=True, slots=True, kw_only=True)
class PerfAnalysisEvent:
    """Emitted after a performance analysis is generated for a run."""

    run_id: int
    analysis_text: str


@dataclass(frozen=True, slots=True, kw_only=True)
class ProgressUpdateEvent:
    """Emitted after each task completion with full progress metrics."""

    run_id: int
    stage: PipelineStage
    current_provider: str
    current_model: str
    current_task: str
    tasks_completed: int
    tasks_total: int
    start_time_ms: float
    current_time_ms: float
    estimated_remaining_ms: float | None
    task_start_ms: float = 0.0
    counts_by_status: dict[str, int] | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class AppSettingsChangedEvent:
    """Emitted after one or more app settings are saved via the Settings dialog."""

    changed_keys: tuple[str, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class ModelSelectionKey:
    """Composite key identifying a model by provider and name for cross-provider selection."""

    provider_id: str
    model_name: str


@dataclass(frozen=True, slots=True, kw_only=True)
class AdvancedRunOptions:
    """Effective advanced options for a single run, with override tracking."""

    streaming_enabled: bool
    warmup_enabled: bool
    reasoning_effort: str  # "default" | "low" | "medium" | "high"
    streaming_is_override: bool
    warmup_is_override: bool
    reasoning_is_override: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class RunSummary:
    """Immutable snapshot of all Left Panel inputs gathered at Start time."""

    run_mode: RunMode
    judge_provider_id: str | None
    judge_model_name: str | None
    selected_models: list[ModelSelectionKey]
    task_file_paths: list[Path]
    advanced_options: AdvancedRunOptions
    performance_input_sizes: list[str]
    performance_output_sizes: list[str]
    performance_repeats: int
    judge_run_analysis_enabled: bool
