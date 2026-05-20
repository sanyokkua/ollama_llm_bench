import logging

from PySide6.QtWidgets import QComboBox


def set_benchmark_run_on_dropdown(run_id: int, combobox: QComboBox, logger: logging.Logger) -> None:
    """
    Set the current selection of a dropdown to the item with matching run ID.

    Args:
        run_id: The run ID to select.
        combobox: The QComboBox to update.
        logger: Logger instance for status messages.
    """
    logger.debug("Run ID changed to %s", run_id)

    # Find the index that has the matching run_id as user data
    for i in range(combobox.count()):
        if combobox.itemData(i) == run_id:
            combobox.setCurrentIndex(i)
            return
    logger.debug("Run ID %s not found in dropdown", run_id)
