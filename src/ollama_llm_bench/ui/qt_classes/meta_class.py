from abc import ABCMeta

from PySide6.QtCore import QObject


# mypy cannot resolve the metaclass produced by type(QObject) (the Shiboken/PySide6
# metaclass) when combined with ABCMeta — a known PySide6 + mypy ecosystem limitation.
# The class is correct at runtime; the ignore below suppresses the spurious [misc] error.
class MetaQObjectABC(type(QObject), ABCMeta):  # type: ignore[misc]
    """Metaclass combining QObject and ABCMeta to allow abstract methods in QObject-derived classes."""
