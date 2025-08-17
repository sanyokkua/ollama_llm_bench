from abc import ABCMeta

from PyQt6.QtCore import QObject


class MetaQObjectABC(type(QObject), ABCMeta):
    """
    Metaclass combining QObject and ABCMeta.
    Allows abstract methods in QObject-derived classes.
    """
