"""Cross-cutting Qt-free infrastructure: Clock, two-stream logging, OS path resolution.

Source of truth: ``docs/v3_specification/08_Cross_Cutting/08-E_interfaces_contracts.md``
§5 (Clock); ``docs/v3_specification/16_Engineering_Standards/06_LOGGING_STANDARD.md``;
``docs/v3_specification/10_Domain_and_Data/07_FILE_LAYOUT.md``.

This module gives every other module the small, cross-cutting infrastructure it depends
on to be deterministically testable and correctly observable: an injectable time source
(``Clock``), the application's two independent, correctly-redacted log streams
(``configure_logging`` for ``app.*``, ``open_run_log`` for ``run.*``), and a resolved
on-disk path API layered over the platform-detected application-data root
(``app_log_path``, ``run_log_path``, and their parent-directory variants).
"""

from ollama_llm_bench.backend.infra.api import (
    acquire_instance_lock,
    app_log_dir,
    app_log_path,
    configure_logging,
    make_system_clock,
    open_run_log,
    run_log_dir,
    run_log_path,
)
from ollama_llm_bench.backend.infra.models import (
    InstanceLockOutcome,
    InstanceLockRecord,
    InstanceLockResult,
)
from ollama_llm_bench.backend.infra.protocols import Clock, InstanceLockHandle, PlatformDetector

__all__: list[str] = [
    "Clock",
    "InstanceLockHandle",
    "InstanceLockOutcome",
    "InstanceLockRecord",
    "InstanceLockResult",
    "PlatformDetector",
    "acquire_instance_lock",
    "app_log_dir",
    "app_log_path",
    "configure_logging",
    "make_system_clock",
    "open_run_log",
    "run_log_dir",
    "run_log_path",
]
