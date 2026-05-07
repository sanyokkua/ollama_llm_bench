"""Run mode display constants for the Left Panel UI."""

from ollama_llm_bench.backend.core.models import PipelineStage, RunMode

RUN_MODE_LABELS: dict[RunMode, str] = {
    RunMode.PERFORMANCE: "System Benchmark",
    RunMode.SPEED: "Task Performance",
    RunMode.PROMPT_EVAL: "Prompt Quality Analysis",
    RunMode.FULL_GRADING: "Comprehensive Evaluation",
}

RUN_MODE_DESCRIPTIONS: dict[RunMode, str] = {
    RunMode.PERFORMANCE: "Measures pure inference speed across input/output size tiers with configurable repeat counts. No evaluation layers.",
    RunMode.SPEED: "Benchmarks per-task throughput: TTFT, tokens/s, total time. Inference only — no evaluation.",
    RunMode.PROMPT_EVAL: "Tests N prompt variants against one model. Runs full evaluation per variant.",
    RunMode.FULL_GRADING: "Inference + all 4 evaluation layers (rule-based, keyword, cosine, LLM judge). Default mode.",
}

RUN_MODE_ORDER: list[RunMode] = [
    RunMode.PERFORMANCE,
    RunMode.SPEED,
    RunMode.PROMPT_EVAL,
    RunMode.FULL_GRADING,
]

STAGE_SEQUENCE_BY_MODE: dict[RunMode, tuple[PipelineStage, ...]] = {
    RunMode.SPEED: (PipelineStage.INITIALIZING, PipelineStage.BENCHMARKING, PipelineStage.FINISHED),
    RunMode.FULL_GRADING: (
        PipelineStage.INITIALIZING,
        PipelineStage.BENCHMARKING,
        PipelineStage.JUDGING,
        PipelineStage.FINISHED,
    ),
    RunMode.PROMPT_EVAL: (
        PipelineStage.INITIALIZING,
        PipelineStage.BENCHMARKING,
        PipelineStage.JUDGING,
        PipelineStage.FINISHED,
    ),
    RunMode.PERFORMANCE: (
        PipelineStage.INITIALIZING,
        PipelineStage.BENCHMARKING,
        PipelineStage.FINISHED,
    ),
}
