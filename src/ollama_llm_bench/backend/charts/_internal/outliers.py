"""The IQR x 1.5 outlier rule shared by kinds 1, 3, and 12 (`13_CHART_AGGREGATORS.md` §6.6)."""

from collections.abc import Sequence
import statistics

_MIN_VALUES_FOR_FENCES = 2  # fewer values carries no statistical basis for an IQR fence


def iqr_fences(values: Sequence[float]) -> tuple[float, float]:
    """Return the Tukey fences `(Q1 - 1.5*IQR, Q3 + 1.5*IQR)` for `values` (§6.6).

    Args:
        values: The group's plotted values. Fewer than two values carries no
            statistical basis for a fence, so every value is treated as kept.

    Returns:
        The `(lower, upper)` fence; a value outside `[lower, upper]` is an
        outlier. `(-inf, inf)` when `values` has fewer than two elements.
    """
    if len(values) < _MIN_VALUES_FOR_FENCES:
        return (float("-inf"), float("inf"))
    q1, _q2, q3 = statistics.quantiles(values, n=4, method="exclusive")
    iqr = q3 - q1
    return (q1 - 1.5 * iqr, q3 + 1.5 * iqr)


def partition_outliers[T](
    items: Sequence[tuple[float, T]],
) -> tuple[list[tuple[float, T]], list[tuple[float, T]]]:
    """Split `(value, tag)` pairs into `(kept, outliers)` by the IQR x 1.5 rule (§6.6).

    Args:
        items: Each plotted value paired with an opaque tag (for example a
            `ResultId`) carried through to the outlier side unchanged.

    Returns:
        `(kept, outliers)`; `kept` holds every pair whose value is inside the
        fences computed from all of `items`'s values, `outliers` the rest.
    """
    lower, upper = iqr_fences([value for value, _tag in items])
    kept = [pair for pair in items if lower <= pair[0] <= upper]
    outliers = [pair for pair in items if not (lower <= pair[0] <= upper)]
    return kept, outliers


def mean_dropping_outliers(values: Sequence[float], *, drop_outliers: bool) -> tuple[float, int]:
    """Compute the mean of `values`, optionally excluding IQR x 1.5 outliers first (§6.6, §7.1, §7.3).

    Args:
        values: The group's non-null plotted values; never empty.
        drop_outliers: When `True`, outliers are excluded before the mean is
            taken; a group left with no non-outlier value falls back to the
            full set rather than producing an undefined mean.

    Returns:
        `(mean, n)` where `n` is the count of values that actually contributed
        to the mean — the group's post-outlier-removal sample size (§6.5a).
    """
    working = list(values)
    if drop_outliers and len(working) >= _MIN_VALUES_FOR_FENCES:
        kept, _outliers = partition_outliers([(value, None) for value in working])
        if kept:
            working = [value for value, _tag in kept]
    return sum(working) / len(working), len(working)


def five_number_summary(values: Sequence[float]) -> tuple[float, float, float, float, float]:
    """Compute `(min, Q1, median, Q3, max)` over `values` (§7.12).

    Args:
        values: A model group's non-null plotted values; never empty.

    Returns:
        The five-number summary; every element equals the single value when
        `values` has exactly one element.
    """
    if len(values) == 1:
        only = values[0]
        return (only, only, only, only, only)
    q1, _q2, q3 = statistics.quantiles(values, n=4, method="exclusive")
    return (min(values), q1, statistics.median(values), q3, max(values))
