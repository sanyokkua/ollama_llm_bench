import csv
from pathlib import Path

from ollama_llm_bench.core.interfaces import ITableSerializer
from ollama_llm_bench.core.models import AvgSummaryTableItem, SummaryTableItem

TABLE_SUMMARY_HEADER = ["MODEL", "AVG. TIME (s)", "AVG. TOKENS/s", "AVG. SCORE (%)"]
TABLE_DETAILED_HEADER = ["MODEL", "TASK", "STATUS", "TIME (ms)", "Tokens", "TOKENS/s", "SCORE", "REASON"]


class TableSerializer(ITableSerializer):
    def __init__(self, root_dir: Path):
        self.root_dir = Path(root_dir)
        self.root_dir.mkdir(parents=True, exist_ok=True)

    def save_summary_as_csv(self, items: list[AvgSummaryTableItem]):
        file_path = self.root_dir / "summary.csv"
        with file_path.open(mode="w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(TABLE_SUMMARY_HEADER)
            for item in items:
                writer.writerow([
                    item.model_name,
                    round(item.avg_time_ms / 1000, 3),  # seconds
                    round(item.avg_tokens_per_second, 3),
                    round(item.avg_score * 100, 2)  # percentage
                ],
                )

    def save_summary_as_md(self, items: list[AvgSummaryTableItem]):
        file_path = self.root_dir / "summary.md"
        with file_path.open(mode="w", encoding="utf-8") as f:
            f.write("| " + " | ".join(TABLE_SUMMARY_HEADER) + " |\n")
            f.write("|" + "|".join(["---"] * len(TABLE_SUMMARY_HEADER)) + "|\n")
            for item in items:
                f.write(f"| {item.model_name} | "
                        f"{round(item.avg_time_ms / 1000, 3)} | "
                        f"{round(item.avg_tokens_per_second, 3)} | "
                        f"{round(item.avg_score * 100, 2)} |\n",
                        )

    def save_details_as_csv(self, items: list[SummaryTableItem]):
        file_path = self.root_dir / "details.csv"
        with file_path.open(mode="w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(TABLE_DETAILED_HEADER)
            for item in items:
                writer.writerow([
                    item.model_name,
                    item.task_id,
                    item.task_status,
                    item.time_ms,
                    item.tokens,
                    round(item.tokens_per_second, 3),
                    round(item.score, 3),
                    item.score_reason
                ],
                )

    def save_details_as_md(self, items: list[SummaryTableItem]):
        file_path = self.root_dir / "details.md"
        with file_path.open(mode="w", encoding="utf-8") as f:
            f.write("| " + " | ".join(TABLE_DETAILED_HEADER) + " |\n")
            f.write("|" + "|".join(["---"] * len(TABLE_DETAILED_HEADER)) + "|\n")
            for item in items:
                f.write(f"| {item.model_name} | {item.task_id} | {item.task_status} | "
                        f"{item.time_ms} | {item.tokens} | {round(item.tokens_per_second, 3)} | "
                        f"{round(item.score, 3)} | {item.score_reason} |\n",
                        )
