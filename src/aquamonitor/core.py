from collections.abc import Callable


def _validate(values: list[float], window: int) -> None:
    """Validate rolling-statistics arguments.

    Raises:
        ValueError: If window is not a positive integer or values is empty.
        TypeError: If values contains non-numeric items (including None).
    """
    if not isinstance(window, int) or isinstance(window, bool) or window <= 0:
        raise ValueError("window must be an integer greater than 0.")
    if not values:
        raise ValueError("values must not be empty.")
    for value in values:
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise TypeError("values must contain only numbers (no None).")


def _mean(chunk: list[float]) -> float:
    """Return the arithmetic mean of a window."""
    return sum(chunk) / len(chunk)


def _median(chunk: list[float]) -> float:
    """Return the median of a window."""
    ordered = sorted(chunk)
    mid = len(ordered) // 2
    if len(ordered) % 2 == 1:
        return float(ordered[mid])
    return (ordered[mid - 1] + ordered[mid]) / 2


def _sample_std(chunk: list[float]) -> float:
    """Return the sample standard deviation (N - 1) of a window.

    A window with a single element yields 0.0.
    """
    if len(chunk) < 2:
        return 0.0
    mean = _mean(chunk)
    variance = sum((x - mean) ** 2 for x in chunk) / (len(chunk) - 1)
    return variance ** 0.5


def _rolling(
        values: list[float],
        window: int,
        stat: Callable[[list[float]], float],
) -> list[float]:
    """Apply a statistic to a trailing window ending at each position.

    At the start of the series, where fewer than `window` points are
    available, the statistic is computed over all points seen so far.
    The result has the same length as `values`.
    """
    _validate(values, window)
    return [
        float(stat(values[max(0, i - window + 1): i + 1]))
        for i in range(len(values))
    ]


def moving_average(values: list[float], window: int) -> list[float]:
    """Calculate the moving average of a series.

    Args:
        values: Numeric time series values.
        window: Size of the trailing window, must be greater than 0.

    Returns:
        Moving averages, one per input value.

    Raises:
        ValueError: If window is invalid or values is empty.
        TypeError: If values contains non-numeric items.
    """
    return _rolling(values, window, _mean)


def moving_median(values: list[float], window: int) -> list[float]:
    """Calculate the moving median of a series.

    Args:
        values: Numeric time series values.
        window: Size of the trailing window, must be greater than 0.

    Returns:
        Moving medians, one per input value.

    Raises:
        ValueError: If window is invalid or values is empty.
        TypeError: If values contains non-numeric items.
    """
    return _rolling(values, window, _median)


def moving_std(values: list[float], window: int) -> list[float]:
    """Calculate the moving sample standard deviation of a series.

    Uses Bessel's correction (N - 1); a window of one element gives 0.0.

    Args:
        values: Numeric time series values.
        window: Size of the trailing window, must be greater than 0.

    Returns:
        Moving standard deviations, one per input value.

    Raises:
        ValueError: If window is invalid or values is empty.
        TypeError: If values contains non-numeric items.
    """
    return _rolling(values, window, _sample_std)
