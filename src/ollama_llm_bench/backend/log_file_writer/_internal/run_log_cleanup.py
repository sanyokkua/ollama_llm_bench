"""Startup count-based run-log cleanup (STORY-037-AC-2, EC-FL-10, §8.2).

Only the count rule from §8.2 is implemented here — the age rule and the orphan rule
are explicitly out of scope for this module and are left to a future story.
"""

from pathlib import Path
import re
from typing import Final

_RUN_LOG_PATTERN: Final[re.Pattern[str]] = re.compile(r"^run_.+_(?P<unix_ts>\d+)\.log$")

DEFAULT_RUN_LOG_KEEP_COUNT: Final[int] = 200


def cleanup_run_logs_by_count(*, run_log_dir: Path, keep_count: int) -> int:
    """Delete the oldest run-log files beyond ``keep_count``, oldest-timestamp first.

    A file not matching the ``run_<run_id>_<unix_ts>.log`` template is left untouched.
    The directory not existing is not an error — it simply has nothing to clean up.

    Args:
        run_log_dir: The ``<app-data>/logs/run/`` directory to prune.
        keep_count: How many run-log files to retain (200 default per §8.2).

    Returns:
        The number of files deleted.
    """
    if not run_log_dir.is_dir():
        return 0

    matched: list[tuple[int, Path]] = []
    for candidate in run_log_dir.iterdir():
        if not candidate.is_file():
            continue
        match = _RUN_LOG_PATTERN.match(candidate.name)
        if match is None:
            continue
        matched.append((int(match.group("unix_ts")), candidate))

    matched.sort(key=lambda entry: entry[0])
    excess = matched[: max(0, len(matched) - keep_count)]
    for _, path in excess:
        path.unlink()
    return len(excess)
