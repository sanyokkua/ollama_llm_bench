"""Cross-boundary DTOs and enums owned by the platform-detection module.

Source of truth: ``docs/v3_specification/08_Cross_Cutting/08-K_platform_specifics.md``
§2 (the platform detector and the platform profile).

``PlatformKind`` is declared locally here — not in ``backend.domain`` — because nothing
outside ``backend/platform/`` needs it yet, mirroring how ``backend/errors`` keeps its
own local ``ErrorCategory`` rather than centralizing every enum in ``backend/domain/``.
"""

from enum import StrEnum
from pathlib import Path

import msgspec

__all__: list[str] = [
    "PlatformKind",
    "PlatformProfile",
]


class PlatformKind(StrEnum):
    """The four host classifications the platform detector can produce (§2).

    ``UNKNOWN`` is a genuine, sanctioned outcome — not an error — for a host the
    detector cannot classify; the application then falls back to Linux conventions.
    """

    MACOS = "macos"
    WINDOWS = "windows"
    LINUX = "linux"
    UNKNOWN = "unknown"


class PlatformProfile(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """The immutable, once-resolved platform profile every later module consults (§2).

    Produced once by the platform detector at launch and cached in the composition
    root for the process lifetime. No field is ever re-derived after construction —
    a later caller needing an OS-specific value reads it from this profile.
    """

    kind: PlatformKind
    os_version: str
    app_data_root: Path
    home_path: Path
    desktop_path: Path
    path_separator: str
    line_ending: str
    case_sensitive_fs: bool
    supports_native_dark_mode: bool
    file_manager_label: str
