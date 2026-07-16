"""``WorkspaceHint`` — the contract-local hint payload for a workspace switch.

Source of truth: ``docs/v3_specification/08_Cross_Cutting/08-E_interfaces_contracts.md``
§19 (Workspace Controller). ``WorkspaceHint`` is declared contract-local there rather than
in ``10_Domain_and_Data/02_DTOS_AND_ENUMS.md`` — this module is its owning module.
"""

import msgspec

__all__: list[str] = ["WorkspaceHint"]


class WorkspaceHint(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """Optional guidance applied to the destination workspace on a switch.

    Attributes:
        open_paths: Task-editor file paths to pre-open on arrival; empty when
            no file should be pre-opened.
        focus_widget: The object name of the child widget to focus on
            arrival, e.g. ``"progress"`` or ``"result_summary"``; ``None``
            when no particular child should receive focus.
    """

    open_paths: tuple[str, ...] = ()
    focus_widget: str | None = None
