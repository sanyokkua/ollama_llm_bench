"""Recursive, idempotent creation of ``<app-data>`` on first launch.

Source of truth: ``docs/v3_specification/08_Cross_Cutting/08-K_platform_specifics.md``
§13 (EC-K1); ``docs/v3_specification/10_Domain_and_Data/07_FILE_LAYOUT.md`` §9-10.
"""

from pathlib import Path

from ollama_llm_bench.backend.errors import ConfigurationError


def create_app_data_dir_impl(app_data_root: Path) -> Path:
    """Create ``<app-data>`` recursively and idempotently.

    A second call on an already-existing tree is a no-op (``exist_ok=True``). A
    non-ASCII path is created and returned without a ``UnicodeError`` or mojibake —
    ``pathlib.Path`` carries the path as a Unicode string throughout, so no manual
    encode/decode step is introduced here (EC-PLAT-4).

    Args:
        app_data_root: The resolved ``<app-data>`` directory to create, typically
            ``PlatformProfile.app_data_root``.

    Returns:
        The same ``app_data_root``, once the directory is confirmed to exist.

    Raises:
        ConfigurationError: The directory could not be created because the
            process lacks the filesystem permission to do so, or because of
            another OS-level failure such as insufficient disk space
            (EC-K1, EC-PLAT-1).
    """
    try:
        app_data_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    except OSError as exc:
        reason = exc.strerror or str(exc)
        raise ConfigurationError(
            message=(
                f"Cannot create the application data directory at '{app_data_root}': {reason}."
            )
        ) from exc
    return app_data_root
