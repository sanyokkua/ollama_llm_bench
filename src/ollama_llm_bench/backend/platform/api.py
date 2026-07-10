"""Public surface for ``backend/platform/``: OS classification and app-data paths.

Source of truth: ``docs/v3_specification/08_Cross_Cutting/08-K_platform_specifics.md``
§§2-3, 13; ``docs/v3_specification/10_Domain_and_Data/07_FILE_LAYOUT.md`` §1.
"""

import os
from pathlib import Path
import platform as _stdlib_platform
import sys

import icontract

from ollama_llm_bench.backend.platform._internal.app_data_dir import create_app_data_dir_impl
from ollama_llm_bench.backend.platform._internal.detector import InjectablePlatformDetector
from ollama_llm_bench.backend.platform.protocols import PlatformDetector

__all__: list[str] = [
    "create_app_data_dir",
    "make_platform_detector",
]


@icontract.ensure(
    lambda result: result is not None,
    "make_platform_detector must always return a usable PlatformDetector — a "
    "violation here means this factory's own wiring is broken, not that the host "
    "is unclassifiable (an unclassifiable host is a sanctioned UNKNOWN outcome, "
    "not a missing detector)",
)
def make_platform_detector() -> PlatformDetector:
    """Construct the default ``PlatformDetector`` bound to the real host environment.

    Reads the real ``sys.platform``, ``os.environ``, and ``Path.home()`` exactly
    once at construction time; the returned detector's ``detect()`` never re-reads
    them afterward.

    Returns:
        A ``PlatformDetector`` bound to this process's real platform identity.
    """
    return InjectablePlatformDetector(
        platform_identifier=sys.platform,
        environ=os.environ,
        home_path=Path.home(),
        os_version=_platform_version_string(),
    )


def _platform_version_string() -> str:
    """Return a human-readable OS version string for diagnostics.

    Returns:
        The standard-library ``platform.platform()`` string describing this host.
    """
    return _stdlib_platform.platform()


@icontract.require(
    lambda app_data_root: app_data_root.is_absolute(),
    "app_data_root must be an absolute path — this codebase's own PlatformDetector "
    "never resolves a relative app-data root, so a relative path here indicates a "
    "bug in the caller, not a bad environment",
)
@icontract.ensure(
    lambda result, app_data_root: result == app_data_root,
    "create_app_data_dir must return exactly the path it was asked to create",
)
def create_app_data_dir(app_data_root: Path) -> Path:
    """Create ``<app-data>`` recursively and idempotently (EC-K1).

    A second call on an already-existing tree is a no-op. Never silently
    continues with a non-writable path: a permission failure raises a typed
    ``ConfigurationError`` naming the attempted path rather than being swallowed.

    Args:
        app_data_root: The resolved ``<app-data>`` directory to create, typically
            ``PlatformProfile.app_data_root``.

    Returns:
        The same ``app_data_root``, once the directory is confirmed to exist.

    Raises:
        ConfigurationError: The directory could not be created because the
            process lacks the filesystem permission to do so.
    """
    return create_app_data_dir_impl(app_data_root)
