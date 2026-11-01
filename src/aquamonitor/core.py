import math
from bisect import bisect_left
from collections.abc import Callable
from datetime import datetime, timedelta
from statistics import median

from aquamonitor.domain import MissingDataError, Observation, Series


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


def _gap_context(series: Series) -> tuple[list[float | None], list[float], list[int]]:
    """Return values, timestamps in seconds and indexes of known values.

    Raises:
        TypeError: If series is not a Series.
        MissingDataError: If the series is not empty but has no known values.
    """
    if not isinstance(series, Series):
        raise TypeError("series must be a Series.")
    values = series.values()
    times = [moment.timestamp() for moment in series.timestamps()]
    known = [i for i, value in enumerate(values) if value is not None]
    if values and not known:
        raise MissingDataError("series has no values to interpolate from.")
    return values, times, known


def _check_gap(seconds: float, limit: float | None) -> None:
    """Raise MissingDataError if a gap is longer than the limit in seconds."""
    if limit is not None and seconds > limit:
        raise MissingDataError(f"gap of {seconds / 3600:.1f} h is longer than allowed.")


def linear_interpolate(series: Series, max_gap: timedelta | None = None) -> list[float]:
    """Fill missing values (None) by linear interpolation in time.

    A gap between two known points is filled on the straight line between
    them, weighted by real time, so uneven steps are handled correctly.
    Gaps at the start or the end of the series take the nearest known value.

    Args:
        series: Time series with possible missing values.
        max_gap: Longest gap that may be filled (time between the known
            neighbours, or to the nearest known point at the edges);
            None means no limit.

    Returns:
        One value per observation, without None; an empty series gives [].

    Raises:
        TypeError: If series is not a Series.
        MissingDataError: If the series has no known values at all or a gap
            is longer than max_gap.
    """
    values, times, known = _gap_context(series)
    limit = None if max_gap is None else max_gap.total_seconds()
    result: list[float] = []
    for i, value in enumerate(values):
        if value is not None:
            result.append(value)
            continue
        k = bisect_left(known, i)
        if k == 0 or k == len(known):
            edge = known[min(k, len(known) - 1)]
            _check_gap(abs(times[edge] - times[i]), limit)
            result.append(values[edge])
            continue
        left, right = known[k - 1], known[k]
        span = times[right] - times[left]
        _check_gap(span, limit)
        share = (times[i] - times[left]) / span if span else 0.0
        result.append(values[left] + (values[right] - values[left]) * share)
    return result


def nearest_interpolate(series: Series) -> list[float]:
    """Fill missing values (None) with the value of the nearest known point in time.

    When both neighbours are equally far, the earlier one is used.

    Raises:
        TypeError: If series is not a Series.
        MissingDataError: If the series has no known values at all.
    """
    values, times, known = _gap_context(series)
    result: list[float] = []
    for i, value in enumerate(values):
        if value is None:
            k = bisect_left(known, i)
            neighbours = known[max(k - 1, 0): k + 1]
            value = values[min(neighbours, key=lambda j: abs(times[j] - times[i]))]
        result.append(value)
    return result


INTERPOLATORS: dict[str, Callable[[Series], list[float]]] = {
    "linear": linear_interpolate,
    "nearest": nearest_interpolate,
}


def interpolation_error(series: Series, method: str = "linear", every: int = 5) -> float:
    """Check interpolation quality on artificially removed points.

    Every `every`-th known point inside the series is hidden, the series is
    interpolated, and the restored values are compared with the true ones.

    Args:
        series: Series with enough known values.
        method: "linear" or "nearest".
        every: Hide each `every`-th known point (2 or more).

    Returns:
        Mean absolute error on the hidden points, in the unit of the series.

    Raises:
        ValueError: If method is unknown, every is less than 2, or the series
            is too short to hide any point.
    """
    if method not in INTERPOLATORS:
        raise ValueError(f"method must be one of {sorted(INTERPOLATORS)}.")
    if not isinstance(every, int) or isinstance(every, bool) or every < 2:
        raise ValueError("every must be an integer of at least 2.")
    values, _, known = _gap_context(series)
    hidden = {i for n, i in enumerate(known[1:-1], start=1) if n % every == 0}
    if not hidden:
        raise ValueError("series is too short to hide points for the check.")
    damaged = Series(series.sensor_id, [
        Observation(moment, series.sensor_id, None if i in hidden else values[i])
        for i, moment in enumerate(series.timestamps())
    ])
    restored = INTERPOLATORS[method](damaged)
    return sum(abs(restored[i] - values[i]) for i in hidden) / len(hidden)


def _check_horizon(horizon: int) -> None:
    """Raise ValueError if horizon is not a positive integer."""
    if not isinstance(horizon, int) or isinstance(horizon, bool) or horizon <= 0:
        raise ValueError("horizon must be an integer greater than 0.")


def naive_forecast(values: list[float], horizon: int) -> list[float]:
    """Forecast the next `horizon` steps by repeating the last value.

    This is the baseline model for Demonstration 1.

    Raises:
        ValueError: If horizon is not a positive integer or values is empty.
        TypeError: If values contains non-numeric items (fill gaps first).
    """
    _check_horizon(horizon)
    _validate(values, 1)
    return [float(values[-1])] * horizon


def _median_step(timestamps: list[datetime]) -> timedelta:
    """Return the median interval between timestamps.

    Raises:
        ValueError: If there are fewer than two timestamps or they do not increase.
    """
    if len(timestamps) < 2:
        raise ValueError("at least two timestamps are needed to know the step.")
    step = median(b - a for a, b in zip(timestamps, timestamps[1:]))
    if step <= timedelta(0):
        raise ValueError("timestamps must increase.")
    return step


def hours_to_steps(timestamps: list[datetime], hours: float) -> int:
    """Convert a horizon in hours to a number of steps of the series.

    The step is the median interval between timestamps, so a few irregular
    gaps do not change it. For 5-minute data 12 hours give 144 steps.

    Raises:
        ValueError: If hours is not a positive number, there are fewer than
            two timestamps, or the timestamps do not increase.
    """
    if not isinstance(hours, (int, float)) or isinstance(hours, bool) or hours <= 0:
        raise ValueError("hours must be a positive number.")
    return max(1, round(timedelta(hours=hours) / _median_step(timestamps)))


def forecast_timestamps(timestamps: list[datetime], steps: int) -> list[datetime]:
    """Return the times of the next `steps` forecast points after the series.

    The step is the median interval between `timestamps`, so the result
    can be drawn on the time axis next to the facts.

    Raises:
        ValueError: If steps is not a positive integer or the step is unknown.
    """
    _check_horizon(steps)
    step = _median_step(timestamps)
    return [timestamps[-1] + step * n for n in range(1, steps + 1)]


def calculate_metrics(y_true: list[float], y_pred: list[float]) -> dict[str, float]:
    """Compare a forecast with the facts: RMSE, MAE, MAPE (%) and R2.

    MAPE skips points where the true value is 0 and is NaN if all of them are 0.
    R2 is NaN when the true values are all equal.

    Raises:
        ValueError: If the lists are empty or have different lengths.
        TypeError: If a list contains non-numeric items.
    """
    _validate(y_true, 1)
    _validate(y_pred, 1)
    if len(y_true) != len(y_pred):
        raise ValueError("y_true and y_pred must have the same length.")
    errors = [p - t for t, p in zip(y_true, y_pred)]
    ratios = [abs(e / t) for t, e in zip(y_true, errors) if t != 0]
    mean_true = _mean(y_true)
    total = sum((t - mean_true) ** 2 for t in y_true)
    return {
        "RMSE": math.sqrt(_mean([e * e for e in errors])),
        "MAE": _mean([abs(e) for e in errors]),
        "MAPE": _mean(ratios) * 100 if ratios else math.nan,
        "R2": 1 - sum(e * e for e in errors) / total if total else math.nan,
    }


def evaluate_forecast(
        values: list[float],
        horizon: int,
        forecaster: Callable[[list[float], int], list[float]] = naive_forecast,
) -> dict[str, float]:
    """Hold out the last `horizon` points, forecast them and return the metrics.

    Args:
        values: Series without gaps (fill them with linear_interpolate first).
        horizon: Number of held-out points, in steps of the series.
        forecaster: Model `(history, horizon) -> forecast`; naive by default.

    Raises:
        ValueError: If horizon is invalid or the series is not longer than it.
    """
    _check_horizon(horizon)
    _validate(values, 1)
    if len(values) <= horizon:
        raise ValueError("series must be longer than the horizon.")
    return calculate_metrics(values[-horizon:], forecaster(values[:-horizon], horizon))


def walk_forward(
        values: list[float],
        horizon: int,
        min_train: int,
        forecaster: Callable[[list[float], int], list[float]] = naive_forecast,
) -> dict[str, float]:
    """Average the metrics over windows that grow by `horizon` points each time.

    For each cut the model sees `values[:cut]` and forecasts the next `horizon`
    points; windows where a metric is NaN are left out of its average.

    Raises:
        ValueError: If horizon or min_train is invalid or the series is too
            short for one window.
    """
    _check_horizon(horizon)
    _check_horizon(min_train)
    _validate(values, 1)
    cuts = range(min_train, len(values) - horizon + 1, horizon)
    if not cuts:
        raise ValueError("series is too short for walk-forward evaluation.")
    runs = [
        calculate_metrics(values[c:c + horizon], forecaster(values[:c], horizon))
        for c in cuts
    ]
    result: dict[str, float] = {}
    for name in runs[0]:
        good = [run[name] for run in runs if not math.isnan(run[name])]
        result[name] = _mean(good) if good else math.nan
    return result
