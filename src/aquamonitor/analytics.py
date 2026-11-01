from collections.abc import Callable
from datetime import datetime
from typing import Literal

from aquamonitor.domain import Observation, Series

Period = Literal["day", "week", "month"]


def _week_key(moment: datetime) -> str:
    """Return the ISO 8601 week key, e.g. '2026-W01'."""
    year, week, _ = moment.isocalendar()
    return f"{year}-W{week:02d}"


_PERIOD_KEYS: dict[str, Callable[[datetime], str]] = {
    "day": lambda moment: moment.strftime("%Y-%m-%d"),
    "week": _week_key,
    "month": lambda moment: moment.strftime("%Y-%m"),
}


def aggregate_by_period(
    series: Series, period: Period = "day"
) -> dict[str, dict[str, float | int | None]]:
    """Group observations by day, week, or month and compute statistical aggregates.

    Weeks follow ISO 8601, so 2025-12-29 belongs to '2026-W01'.
    A period in which every value is missing gets None for min, max and avg.

    Args:
        series (Series): Time series containing hydrological observations.
        period (Literal["day", "week", "month"]): Aggregation period interval.
            Defaults to "day".

    Returns:
        dict[str, dict[str, float | int | None]]: A dictionary mapping each period
            key (e.g., 'YYYY-MM-DD', 'YYYY-Www', 'YYYY-MM') in chronological order
            to its statistical aggregates ('min', 'max', 'avg', 'count',
            'missing_count').

    Raises:
        ValueError: If an unsupported aggregation period is specified.
    """
    if period not in _PERIOD_KEYS:
        raise ValueError("Period must be one of: 'day', 'week', or 'month'")
    make_key = _PERIOD_KEYS[period]

    grouped: dict[str, list[Observation]] = {}
    for obs in series:
        grouped.setdefault(make_key(obs.timestamp), []).append(obs)

    result: dict[str, dict[str, float | int | None]] = {}
    for time_key, obs_list in grouped.items():
        valid_vals = [obs.value for obs in obs_list if obs.value is not None]
        if valid_vals:
            min_val: float | None = round(min(valid_vals), 2)
            max_val: float | None = round(max(valid_vals), 2)
            avg_val: float | None = round(sum(valid_vals) / len(valid_vals), 2)
        else:
            min_val = max_val = avg_val = None

        result[time_key] = {
            "min": min_val,
            "max": max_val,
            "avg": avg_val,
            "count": len(obs_list),
            "missing_count": len(obs_list) - len(valid_vals),
        }
    return result


def _fmt(value: float | None) -> str:
    """Format a statistic for the report table; None becomes a dash."""
    return f"{value:<8.2f}" if value is not None else f"{'-':<8}"


def generate_console_report(series: Series, period: Period = "day") -> str:
    """Build a consolidated summary report table; the caller prints it.

    A period without known values shows '-' instead of numbers.

    Args:
        series (Series): Time series containing hydrological observations.
        period (Literal["day", "week", "month"]): Aggregation period interval.
            Defaults to "day".

    Returns:
        str: The formatted plain-text console report.
    """
    stats = aggregate_by_period(series, period)

    header_title = {
        "day": "Date (YYYY-MM-DD)",
        "week": "Week (YYYY-Www)",
        "month": "Month (YYYY-MM)",
    }[period]  # period is already validated by aggregate_by_period

    lines = [
        f"\n=== SUMMARY REPORT FOR SENSOR: {series.sensor_id} ({period.upper()}) ===",
        f"{header_title:<20} | {'Min':<8} | {'Max':<8} | {'Avg':<8} | {'Count':<6} | {'Missing':<8}",
        "-" * 74,
    ]

    for time_key, agg in stats.items():
        lines.append(
            f"{time_key:<20} | {_fmt(agg['min'])} | {_fmt(agg['max'])} | {_fmt(agg['avg'])} | {agg['count']:<6} | {agg['missing_count']:<8}"
        )

    lines.append("-" * 74)
    return "\n".join(lines)