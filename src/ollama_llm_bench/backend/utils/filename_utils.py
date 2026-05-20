"""Filename sanitization utilities."""

import re
from datetime import datetime


def sanitize_filename(name: str) -> str:
    """Replace characters that are illegal in Windows and POSIX filenames with underscores.

    Replaces: < > : " / \\ | ? * and ASCII control characters (0x00-0x1F).

    Args:
        name: Raw filename string (no directory component).

    Returns:
        Sanitized string safe for use as a filename on all major platforms.
    """
    sanitized = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name)
    return sanitized or "_"


def default_export_filename(run_name: str, report_type: str, ext: str) -> str:
    """Build a default export filename from run name, report type, and extension.

    Args:
        run_name: Raw run name (will be sanitized).
        report_type: Short label for the report (e.g. ``"summary"``, ``"detailed"``).
        ext: File extension without leading dot (e.g. ``"csv"``, ``"md"``).

    Returns:
        Sanitized filename with timestamp, e.g. ``"my_run_2024-01-15_10-30_summary.csv"``.
    """
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    safe_name = sanitize_filename(run_name)
    return f"{safe_name}_{timestamp}_{report_type}.{ext}"
