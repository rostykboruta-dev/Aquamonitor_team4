from typing import Literal
from aquamonitor.domain import Observation, Series


def aggregate_by_period(
    series: Series, period: Literal["day", "week", "month"] = "day"
) -> dict[str, dict[str, float | int]]:
    """Group observations by day, week, or month and compute statistical aggregates.

    Args:
        series (Series): Time series containing hydrological observations.
        period (Literal["day", "week", "month"]): Aggregation period interval.
            Defaults to "day".

    Returns:
        dict[str, dict[str, float | int]]: A dictionary mapping each period key
            (e.g., 'YYYY-MM-DD', 'YYYY-Www', 'YYYY-MM') to its statistical aggregates
            ('min', 'max', 'avg', 'count', 'missing_count').

    Raises:
        ValueError: If an unsupported aggregation period is specified.
    """
    grouped: dict[str, list[Observation]] = {}

    for obs in series._observations:
        if period == "day":
            key = obs.timestamp.strftime("%Y-%m-%d")
        elif period == "week":
            year, week, _ = obs.timestamp.isocalendar()
            key = f"{year}-W{week:02d}"
        elif period == "month":
            key = obs.timestamp.strftime("%Y-%m")
        else:
            raise ValueError("Period must be one of: 'day', 'week', or 'month'")

        if key not in grouped:
            grouped[key] = []
        grouped[key].append(obs)

    result: dict[str, dict[str, float | int]] = {}

    for time_key, obs_list in grouped.items():
        valid_vals: list[float] = [
            obs.value for obs in obs_list if obs.value is not None
        ]
        missing_cnt = sum(1 for obs in obs_list if obs.is_missing())
        total_cnt = len(obs_list)

        if valid_vals:
            min_val = float(min(valid_vals))
            max_val = float(max(valid_vals))
            avg_val = float(sum(valid_vals) / len(valid_vals))
        else:
            min_val = max_val = avg_val = 0.0

        result[time_key] = {
            "min": round(min_val, 2),
            "max": round(max_val, 2),
            "avg": round(avg_val, 2),
            "count": total_cnt,
            "missing_count": missing_cnt,
        }

    return result


def generate_console_report(
    series: Series, period: Literal["day", "week", "month"] = "day"
) -> str:
    """Format and print a consolidated summary report table to the console.

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
    }[period]

    lines = [
        f"\n=== SUMMARY REPORT FOR SENSOR: {series.sensor_id} ({period.upper()}) ===",
        f"{header_title:<20} | {'Min':<8} | {'Max':<8} | {'Avg':<8} | {'Count':<6} | {'Missing':<8}",
        "-" * 74,
    ]

    for time_key, agg in stats.items():
        lines.append(
            f"{time_key:<20} | {agg['min']:<8.2f} | {agg['max']:<8.2f} | {agg['avg']:<8.2f} | {agg['count']:<6} | {agg['missing_count']:<8}"
        )

    lines.append("-" * 74)
    report_str = "\n".join(lines)
    print(report_str)
    return report_str