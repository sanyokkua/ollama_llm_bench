"""``NotificationService`` Protocol (08-E §20) -- the sole sanctioned surface for a
controller to raise a user-visible message. UI primitives never throw to the user;
they call this service instead.
"""

from typing import Protocol


class NotificationService(Protocol):
    """User-facing notifications: toasts and modal error dialogs."""

    def show_info(self, text: str, duration_ms: int = 5000) -> None:
        """Show a transient informational toast.

        fast-synchronous; must be called on the Qt main thread. Never raises.

        Args:
            text: The message to display, exactly as the caller means it to
                appear. UI/display surfaces do not apply redaction (redaction
                is scoped to the ``app.*`` log pipeline and provider-SDK
                error-message wrapping at the adapter boundary --
                ``08_Cross_Cutting/08-E_interfaces_contracts.md`` §22).
            duration_ms: How long the toast stays visible, in milliseconds.
        """
        ...

    def show_warning(self, text: str, duration_ms: int = 5000) -> None:
        """Show a transient warning toast.

        fast-synchronous; must be called on the Qt main thread. Never raises.

        Args:
            text: The message to display, exactly as the caller means it to
                appear. UI/display surfaces do not apply redaction (redaction
                is scoped to the ``app.*`` log pipeline and provider-SDK
                error-message wrapping at the adapter boundary --
                ``08_Cross_Cutting/08-E_interfaces_contracts.md`` §22).
            duration_ms: How long the toast stays visible, in milliseconds.
        """
        ...

    def show_error(self, text: str, *, blocking: bool = False) -> None:
        """Show an error notification.

        A transient toast when ``blocking`` is ``False``; a modal dialog when
        ``True``. fast-synchronous; must be called on the Qt main thread.
        Never raises.

        Args:
            text: The message to display, exactly as the caller means it to
                appear. UI/display surfaces do not apply redaction (redaction
                is scoped to the ``app.*`` log pipeline and provider-SDK
                error-message wrapping at the adapter boundary --
                ``08_Cross_Cutting/08-E_interfaces_contracts.md`` §22).
            blocking: Selects a modal dialog (``True``) or a toast (``False``).
        """
        ...
