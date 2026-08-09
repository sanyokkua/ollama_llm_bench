"""Startup run-log retention cleanup (STORY-037-AC-2, STORY-088-AC-2, EC-FL-10, §8.2).

Both retention rules from ``12_Quality_and_NFRs/07_RESOURCE_LIMITS.md`` §5 live
here: the count rule (at most 200 files) and the age rule (none older than 90
days). §5 requires both to be applied, "whichever removes more files governs" —
and because each rule deletes a prefix of the same ascending-timestamp-sorted
list, the union of the two deletion sets is exactly the longer prefix, so
``max()`` of the two prefix lengths implements the rule faithfully.

The orphan rule stays out of scope: §5 defines an orphan as "a log whose run was
deleted", which requires knowing which run ids still exist — a dependency on the
runs store that this module deliberately does not have. STORY-115 owns it,
together with wiring the prune into application startup.
"""

from datetime import UTC, datetime
from pathlib import Path
import re
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from ollama_llm_bench.backend.domain import Iso8601Utc
    from ollama_llm_bench.backend.infra.protocols import Clock

_RUN_LOG_PATTERN: Final[re.Pattern[str]] = re.compile(r"^run_.+_(?P<unix_ts>\d+)\.log$")
_SECONDS_PER_DAY: Final[int] = 86_400

DEFAULT_RUN_LOG_KEEP_COUNT: Final[int] = 200
DEFAULT_RUN_LOG_MAX_AGE_DAYS: Final[int] = 90


def _scan_run_logs(run_log_dir: Path) -> list[tuple[int, Path]]:
    """Return every run-log file as ``(unix_ts, path)``, oldest timestamp first.

    A file not matching the ``run_<run_id>_<unix_ts>.log`` template is skipped,
    as is any non-file entry. A missing directory yields an empty list.
    """
    if not run_log_dir.is_dir():
        return []

    matched: list[tuple[int, Path]] = []
    for candidate in run_log_dir.iterdir():
        if not candidate.is_file():
            continue
        match = _RUN_LOG_PATTERN.match(candidate.name)
        if match is None:
            continue
        matched.append((int(match.group("unix_ts")), candidate))

    matched.sort(key=lambda entry: entry[0])
    return matched


def _delete_oldest(matched: list[tuple[int, Path]], delete_count: int) -> int:
    """Delete the first ``delete_count`` entries of an oldest-first list."""
    for _, path in matched[:delete_count]:
        path.unlink()
    return delete_count


def age_cutoff_unix_ts(*, now_utc: "Iso8601Utc", max_age_days: int) -> int:
    """Return the oldest ``unix_ts`` a run log may carry and still be retained.

    A run log whose timestamp is strictly below the returned value is older than
    ``max_age_days`` and is pruned; one exactly on it is not yet older and stays.

    Args:
        now_utc: The current instant as read from the injected ``Clock``. A
            timezone-naive value is treated as UTC — ``datetime.timestamp()``
            would otherwise silently assume local time and shift the cutoff.
        max_age_days: The retention window in days (90 per §5).

    Returns:
        The cutoff as a Unix timestamp in seconds.
    """
    moment = datetime.fromisoformat(now_utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return int(moment.timestamp()) - max_age_days * _SECONDS_PER_DAY


def cleanup_run_logs_by_count(*, run_log_dir: Path, keep_count: int) -> int:
    """Delete the oldest run-log files beyond ``keep_count``, oldest-timestamp first.

    The count rule in isolation. Production callers use
    ``cleanup_run_logs_by_count_and_age``; this remains the unit under test for
    the count rule on its own.

    Args:
        run_log_dir: The ``<app-data>/logs/run/`` directory to prune.
        keep_count: How many run-log files to retain (200 default per §5).

    Returns:
        The number of files deleted.
    """
    matched = _scan_run_logs(run_log_dir)
    return _delete_oldest(matched, max(0, len(matched) - keep_count))


def cleanup_run_logs_by_count_and_age(
    *, run_log_dir: Path, keep_count: int, clock: "Clock", max_age_days: int
) -> int:
    """Apply both §5 retention rules, oldest-timestamp first.

    Deletes the oldest files until at most ``keep_count`` remain **and** none is
    older than ``max_age_days``. Both rules delete a prefix of the same sorted
    list, so the governing deletion is the longer of the two prefixes — §5's
    "whichever removes more files governs".

    Args:
        run_log_dir: The ``<app-data>/logs/run/`` directory to prune.
        keep_count: How many run-log files to retain (200 default per §5).
        clock: The injected time source; its ``now_utc()`` anchors the age cutoff.
        max_age_days: The retention window in days (90 default per §5).

    Returns:
        The number of files deleted.
    """
    matched = _scan_run_logs(run_log_dir)
    excess_by_count = max(0, len(matched) - keep_count)
    cutoff = age_cutoff_unix_ts(now_utc=clock.now_utc(), max_age_days=max_age_days)
    expired_count = sum(1 for unix_ts, _ in matched if unix_ts < cutoff)
    return _delete_oldest(matched, max(excess_by_count, expired_count))
