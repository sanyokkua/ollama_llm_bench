"""ViewModel-adjacent enums and event types owned by ui/shared (08-L §8, §9; 08-D §5, §6)."""

from enum import StrEnum

import msgspec


class BadgeStatus(StrEnum):
    """The five semantic badge statuses 08-L §8 / 08-D §5 map to a base colour role."""

    PASS = "pass"  # noqa: S105  # display status, not a credential
    FAIL = "fail"
    WARNING = "warning"
    INFO = "info"
    NEUTRAL = "neutral"


class FilterSelectionChanged(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """The current checked-option set emitted by MultiCheckFilterButton (STORY-051-AC-3)."""

    selected_keys: tuple[str, ...]
