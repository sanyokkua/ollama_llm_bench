import csv
from pathlib import Path
from typing import override

from ollama_llm_bench.backend.core.interfaces import ITableSerializer
from ollama_llm_bench.backend.core.models import AvgSummaryTableItem, SummaryTableItem

TABLE_SUMMARY_HEADER = ["MODEL", "AVG. TIME (s)", "AVG. TOKENS/s", "AVG. SCORE (%)", "PASS%", "AVG. TTFT (ms)"]
TABLE_DETAILED_HEADER = [
    "MODEL",
    "TASK",
    "STATUS",
    "TIME (ms)",
    "Tokens",
    "TOKENS/s",
    "SCORE",
    "COSINE",
    "LAYER",
    "REASON",
]


class TableSerializer(ITableSerializer):
    """
    Concrete implementation of ITableSerializer for exporting benchmark results to CSV and Markdown formats.
    Saves files to a specified output directory.
    """

    def __init__(self, root_dir: Path):
        """
        Initialize the table serializer.

        Args:
            root_dir: Directory where output files will be saved.
        """
        self.root_dir = Path(root_dir)
        self.root_dir.mkdir(parents=True, exist_ok=True)

    def save_summary_as_csv(self, items: list[AvgSummaryTableItem]) -> None:
        """
        Export averaged summary results to a CSV file.

        Args:
            items: List of averaged summary items to save.
        """
        file_path = self.root_dir / "summary.csv"
        with file_path.open(mode="w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(TABLE_SUMMARY_HEADER)
            for item in items:
                writer.writerow(
                    [
                        item.model_name,
                        round(item.avg_time_ms / 1000, 3),
                        round(item.avg_tokens_per_second, 3),
                        round(item.avg_score * 100, 2),
                        round(item.pass_rate * 100, 2),
                        round(item.avg_ttft_ms, 0) if item.avg_ttft_ms is not None else "",
                    ],
                )

    def save_summary_as_md(self, items: list[AvgSummaryTableItem]) -> None:
        """
        Export averaged summary results to a Markdown file.

        Args:
            items: List of averaged summary items to save.
        """
        file_path = self.root_dir / "summary.md"
        with file_path.open(mode="w", encoding="utf-8") as f:
            f.write("| " + " | ".join(TABLE_SUMMARY_HEADER) + " |\n")
            f.write("|" + "|".join(["---"] * len(TABLE_SUMMARY_HEADER)) + "|\n")
            for item in items:
                f.write(
                    f"| {item.model_name} | "
                    f"{round(item.avg_time_ms / 1000, 3)} | "
                    f"{round(item.avg_tokens_per_second, 3)} | "
                    f"{round(item.avg_score * 100, 2)} | "
                    f"{round(item.pass_rate * 100, 2)} | "
                    f"{round(item.avg_ttft_ms, 0) if item.avg_ttft_ms is not None else ''} |\n"
                )

    def save_details_as_csv(self, items: list[SummaryTableItem]) -> None:
        """
        Export detailed benchmark results to a CSV file.

        Args:
            items: List of detailed result items to save.
        """
        file_path = self.root_dir / "details.csv"
        with file_path.open(mode="w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(TABLE_DETAILED_HEADER)
            for item in items:
                writer.writerow(
                    [
                        item.model_name,
                        item.task_id,
                        item.task_status,
                        item.time_ms,
                        item.tokens,
                        round(item.tokens_per_second, 3),
                        round(item.score, 3),
                        round(item.cosine_similarity, 3) if item.cosine_similarity is not None else "",
                        item.resolution_layer,
                        item.score_reason,
                    ],
                )

    def save_details_as_md(self, items: list[SummaryTableItem]) -> None:
        """
        Export detailed benchmark results to a Markdown file.

        Args:
            items: List of detailed result items to save.
        """
        file_path = self.root_dir / "details.md"
        with file_path.open(mode="w", encoding="utf-8") as f:
            f.write("| " + " | ".join(TABLE_DETAILED_HEADER) + " |\n")
            f.write("|" + "|".join(["---"] * len(TABLE_DETAILED_HEADER)) + "|\n")
            for item in items:
                f.write(
                    f"| {item.model_name} | {item.task_id} | {item.task_status} | "
                    f"{item.time_ms} | {item.tokens} | {round(item.tokens_per_second, 3)} | "
                    f"{round(item.score, 3)} | "
                    f"{round(item.cosine_similarity, 3) if item.cosine_similarity is not None else ''} | "
                    f"{item.resolution_layer} | {item.score_reason} |\n"
                )

    @override
    def save_summary_as_csv_to_path(self, path: Path, items: list[AvgSummaryTableItem]) -> None:
        """Export averaged summary results to a CSV file at the given path.

        Args:
            path: Full file path to write to.
            items: List of averaged summary items to save.
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open(mode="w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(TABLE_SUMMARY_HEADER)
            for item in items:
                writer.writerow(
                    [
                        item.model_name,
                        round(item.avg_time_ms / 1000, 3),
                        round(item.avg_tokens_per_second, 3),
                        round(item.avg_score * 100, 2),
                        round(item.pass_rate * 100, 2),
                        round(item.avg_ttft_ms, 0) if item.avg_ttft_ms is not None else "",
                    ],
                )

    @override
    def save_summary_as_md_to_path(self, path: Path, items: list[AvgSummaryTableItem]) -> None:
        """Export averaged summary results to a Markdown file at the given path.

        Args:
            path: Full file path to write to.
            items: List of averaged summary items to save.
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open(mode="w", encoding="utf-8") as f:
            f.write("| " + " | ".join(TABLE_SUMMARY_HEADER) + " |\n")
            f.write("|" + "|".join(["---"] * len(TABLE_SUMMARY_HEADER)) + "|\n")
            for item in items:
                f.write(
                    f"| {item.model_name} | "
                    f"{round(item.avg_time_ms / 1000, 3)} | "
                    f"{round(item.avg_tokens_per_second, 3)} | "
                    f"{round(item.avg_score * 100, 2)} | "
                    f"{round(item.pass_rate * 100, 2)} | "
                    f"{round(item.avg_ttft_ms, 0) if item.avg_ttft_ms is not None else ''} |\n"
                )

    @override
    def save_details_as_csv_to_path(self, path: Path, items: list[SummaryTableItem]) -> None:
        """Export detailed benchmark results to a CSV file at the given path.

        Args:
            path: Full file path to write to.
            items: List of detailed result items to save.
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open(mode="w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(TABLE_DETAILED_HEADER)
            for item in items:
                writer.writerow(
                    [
                        item.model_name,
                        item.task_id,
                        item.task_status,
                        item.time_ms,
                        item.tokens,
                        round(item.tokens_per_second, 3),
                        round(item.score, 3),
                        round(item.cosine_similarity, 3) if item.cosine_similarity is not None else "",
                        item.resolution_layer,
                        item.score_reason,
                    ],
                )

    @override
    def save_details_as_md_to_path(self, path: Path, items: list[SummaryTableItem]) -> None:
        """Export detailed benchmark results to a Markdown file at the given path.

        Args:
            path: Full file path to write to.
            items: List of detailed result items to save.
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open(mode="w", encoding="utf-8") as f:
            f.write("| " + " | ".join(TABLE_DETAILED_HEADER) + " |\n")
            f.write("|" + "|".join(["---"] * len(TABLE_DETAILED_HEADER)) + "|\n")
            for item in items:
                f.write(
                    f"| {item.model_name} | {item.task_id} | {item.task_status} | "
                    f"{item.time_ms} | {item.tokens} | {round(item.tokens_per_second, 3)} | "
                    f"{round(item.score, 3)} | "
                    f"{round(item.cosine_similarity, 3) if item.cosine_similarity is not None else ''} | "
                    f"{item.resolution_layer} | {item.score_reason} |\n"
                )
