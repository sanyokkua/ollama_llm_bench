import logging

from PyQt6.QtWidgets import QComboBox


def set_benchmark_run_on_dropdown(run_id: int, combobox: QComboBox, logger: logging.Logger):
    """
    Set the current selection of a dropdown to the item with matching run ID.

    Args:
        run_id: The run ID to select.
        combobox: The QComboBox to update.
        logger: Logger instance for status messages.
    """
    logger.debug(f"Run ID changed to {run_id}")

    # Find the index that has the matching run_id as user data
    for i in range(combobox.count()):
        if combobox.itemData(i) == run_id:
            combobox.setCurrentIndex(i)
            return
    logger.warning(f"Run ID {run_id} not found in dropdown")
