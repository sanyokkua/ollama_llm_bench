from dataclasses import dataclass
from enum import StrEnum
from typing import Optional


@dataclass(frozen=True)
class BenchmarkTaskAnswer:
    """
    Represents the expected and acceptable answers for a benchmark task.
    """
    most_expected: str
    good_answer: str
    pass_option: str


@dataclass(frozen=True)
class BenchmarkTask:
    """
    Represents a single benchmark task with its metadata and expected answers.
    """
    task_id: str
    category: str
    sub_category: str
    question: str
    expected_answer: BenchmarkTaskAnswer
    incorrect_direction: str


class BenchmarkRunStatus(StrEnum):
    """
    Status of a benchmark run indicating completion or failure state.
    """
    NOT_COMPLETED = 'NOT_COMPLETED'
    COMPLETED = 'COMPLETED'
    FAILED = 'FAILED'


class BenchmarkResultStatus(StrEnum):
    """
    Status of an individual benchmark result during execution and evaluation.
    """
    NOT_COMPLETED = 'NOT_COMPLETED'
    WAITING_FOR_JUDGE = 'WAITING_FOR_JUDGE'
    COMPLETED = 'COMPLETED'
    FAILED = 'FAILED'


@dataclass(frozen=True)
class BenchmarkRun:
    """
    Immutable representation of a benchmark run with metadata and status.
    """
    run_id: int
    timestamp: str
    judge_model: str
    status: BenchmarkRunStatus


@dataclass(frozen=True)
class BenchmarkResult:
    """
    Immutable representation of a single model's result on a specific benchmark task.
    """
    result_id: int
    run_id: int
    task_id: str
    model_name: str
    status: BenchmarkResultStatus = BenchmarkResultStatus.NOT_COMPLETED
    llm_response: Optional[str] = None
    time_taken_ms: Optional[int] = None
    tokens_generated: Optional[int] = None
    evaluation_score: Optional[float] = None
    evaluation_reason: Optional[str] = None
    error_message: Optional[str] = None


@dataclass(frozen=True)
class AvgSummaryTableItem:
    """
    Aggregated performance metrics for a model across all tasks in a run.
    """
    model_name: str = ''
    avg_time_ms: float = 0.0
    avg_tokens_per_second: float = 0.0
    avg_score: float = 0.0


@dataclass(frozen=True)
class SummaryTableItem:
    """
    Detailed performance metrics for a model on a specific task within a run.
    """
    model_name: str = ''
    task_id: str = ''
    task_status: str = ''
    time_ms: int = 0
    tokens: int = 0
    tokens_per_second: float = 0.0
    score: float = 0.0
    score_reason: str = ''


@dataclass(frozen=True)
class InferenceResponse:
    """
    Response from an LLM inference call, including generated content and metadata.
    """
    llm_response: str = ''
    time_taken_ms: int = 0
    tokens_generated: int = 0
    has_error: bool = False
    error_message: Optional[str] = None


@dataclass(frozen=True)
class ReporterStatusMsg:
    """
    Status message broadcast during benchmark execution to report progress.
    """
    current_run_id: int
    current_stage: str = ''
    current_model: str = ''
    current_task: str = ''
    tasks_total: int = 0
    tasks_completed: int = 0
    start_time_ms: float = 0
    end_time_ms: float = 0


@dataclass(frozen=True)
class NewRunWidgetStartEvent:
    """
    Event object used to trigger a new benchmark run with selected models.
    """
    judge_model: str
    models: tuple[str, ...]
