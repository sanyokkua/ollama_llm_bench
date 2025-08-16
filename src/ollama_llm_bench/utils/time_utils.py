import time


def calculate_elapsed_time(start_time: float, end_time: float) -> tuple[float, float, float, float]:
    # Calculate duration in milliseconds (properly rounded)
    total_ms = int(round((end_time - start_time) * 1000))

    # Break down into hours, minutes, seconds, ms
    hours, rem = divmod(total_ms, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    seconds, milliseconds = divmod(rem, 1000)

    return hours, minutes, seconds, milliseconds


def format_elapsed_time(start_time: float, end_time: float) -> str:
    hours, minutes, seconds, milliseconds = calculate_elapsed_time(start_time, end_time)
    return f"Spent time: {hours} hours, {minutes} minutes, {seconds} seconds, {milliseconds} ms"


def format_elapsed_time_interval(start_time: float, end_time: float):
    """Format start/end times and duration between two timestamps"""
    # Format start/end as HHMMSS (UTC time)
    start_str = time.strftime("%H:%M:%S", time.gmtime(start_time))
    end_str = time.strftime("%H:%M:%S", time.gmtime(end_time))

    elapsed = format_elapsed_time(start_time, end_time)

    return f"Start time {start_str}, End time {end_str}. {elapsed}"
