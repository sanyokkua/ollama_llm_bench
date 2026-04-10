from abc import ABCMeta

from PySide6.QtCore import QObject


class MetaQObjectABC(type(QObject), ABCMeta):  # type: ignore[misc]
    """
    Metaclass combining QObject and ABCMeta.
    Allows abstract methods in QObject-derived classes.
    """
