from dataclasses import dataclass
from enum import StrEnum
from typing import Optional


@dataclass(frozen=True)
class BenchmarkTaskAnswer:
    most_expected: str
    good_answer: str
    pass_option: str


@dataclass(frozen=True)
class BenchmarkTask:
    task_id: str
    category: str
    sub_category: str
    question: str
    expected_answer: BenchmarkTaskAnswer
    incorrect_direction: str


class BenchmarkRunStatus(StrEnum):
    NOT_COMPLETED = 'NOT_COMPLETED'
    COMPLETED = 'COMPLETED'
    FAILED = 'FAILED'


class BenchmarkResultStatus(StrEnum):
    NOT_COMPLETED = 'NOT_COMPLETED'
    WAITING_FOR_JUDGE = 'WAITING_FOR_JUDGE'
    COMPLETED = 'COMPLETED'
    FAILED = 'FAILED'


@dataclass(frozen=True)
class BenchmarkRun:
    run_id: int
    timestamp: str
    judge_model: str
    status: BenchmarkRunStatus


@dataclass(frozen=True)
class BenchmarkResult:
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
    model_name: str
    avg_time_ms: float
    avg_tokens_per_second: float
    avg_score: float


@dataclass(frozen=True)
class SummaryTableItem:
    model_name: str
    task_id: str
    task_status: str
    time_ms: int
    tokens: int
    tokens_per_second: float
    score: float
    score_reason: str


@dataclass(frozen=True)
class InferenceResponse:
    llm_response: str = ''
    time_taken_ms: int = 0
    tokens_generated: int = 0
    has_error: bool = False
    error_message: Optional[str] = None


# Will be sent on each status update from thread to UI via signal

@dataclass(frozen=True)
class ReporterStatusMsg:
    total_amount_of_tasks: int
    completed_amount_of_tasks: int
    current_model_name: str
    current_task_id: str
    total_amount_of_tasks_for_model: int
    completed_amount_of_tasks_for_model: int
    run_status: BenchmarkRunStatus
    task_status: BenchmarkResultStatus


@dataclass(frozen=True)
class NewRunWidgetStartEvent:
    judge_model: str
    models: tuple[str, ...]
