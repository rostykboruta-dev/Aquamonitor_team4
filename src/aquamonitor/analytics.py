import math
from collections.abc import Callable
from datetime import datetime
from typing import Any, Literal

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
        f"{header_title:<20} | {'Min':<8} | {'Max':<8} | {'Avg':<8} | "
        f"{'Count':<6} | {'Missing':<8}",
        "-" * 74,
    ]

    for time_key, agg in stats.items():
        lines.append(
            f"{time_key:<20} | {_fmt(agg['min'])} | {_fmt(agg['max'])} | {_fmt(agg['avg'])} | "
            f"{agg['count']:<6} | {agg['missing_count']:<8}"
        )

    lines.append("-" * 74)
    return "\n".join(lines)


# Common look of every project plot; change it here, not in each function.
PLOT_STYLE: dict[str, Any] = {
    "figsize": (10, 4),
    "dpi": 100,
    "observed_color": "#1f77b4",
    "forecast_color": "#d62728",
    "grid_alpha": 0.3,
}


def styled_figure(title: str, xlabel: str, ylabel: str) -> tuple[Any, Any]:
    """Create a matplotlib figure and axes in the common project style.

    matplotlib is imported here, so the rest of the package works without it.
    The figure does not use pyplot and needs no window, which suits tests
    and the tkinter window of sprint 2.

    Returns:
        tuple: (Figure, Axes).
    """
    from matplotlib.figure import Figure

    fig = Figure(figsize=PLOT_STYLE["figsize"], dpi=PLOT_STYLE["dpi"])
    ax = fig.add_subplot()
    ax.set_title(title)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.grid(True, alpha=PLOT_STYLE["grid_alpha"])
    return fig, ax


def build_time_series_plot(
    series: Series,
    output_path: str,
    forecast: list[tuple[datetime, float]] | None = None,
    unit: str = "m",
) -> None:
    """Save a PNG line plot of the observed levels and, optionally, the forecast.

    Missing values break the line instead of being drawn as zero.

    Args:
        series (Series): Observed levels.
        output_path (str): Where to save the image (PNG).
        forecast (list[tuple[datetime, float]] | None): Forecast points (time, level).
        unit (str): Unit for the y axis label.

    Raises:
        ValueError: If the series has no known values.
    """
    observations = list(series)
    if not any(obs.value is not None for obs in observations):
        raise ValueError("series has no values to plot.")
    fig, ax = styled_figure(f"Water level, sensor {series.sensor_id}", "Time (UTC)",
                            f"Level, {unit}")
    ax.plot([obs.timestamp for obs in observations],
            [math.nan if obs.value is None else obs.value for obs in observations],
            color=PLOT_STYLE["observed_color"], label="Observed")
    if forecast:
        ax.plot([moment for moment, _ in forecast], [value for _, value in forecast],
                color=PLOT_STYLE["forecast_color"], linestyle="--", label="Forecast")
    ax.legend()
    fig.autofmt_xdate()
    fig.savefig(output_path)


def build_level_histogram(series: Series, output_path: str, bins: int = 20,
                          unit: str = "m") -> None:
    """Save a PNG histogram of the observed levels (missing values are skipped).

    Raises:
        ValueError: If bins is not a positive integer or there are no known values.
    """
    if not isinstance(bins, int) or isinstance(bins, bool) or bins < 1:
        raise ValueError("bins must be a positive integer.")
    values = [obs.value for obs in series if obs.value is not None]
    if not values:
        raise ValueError("series has no values to plot.")
    fig, ax = styled_figure(f"Distribution of levels, sensor {series.sensor_id}",
                            f"Level, {unit}", "Number of observations")
    ax.hist(values, bins=bins, color=PLOT_STYLE["observed_color"])
    fig.savefig(output_path)


def format_metrics_table(metrics: dict[str, float], unit: str = "m") -> str:
    """Format forecast quality metrics as a console table.

    RMSE and MAE are shown in the series unit, MAPE in percent, R2 without a
    unit; a NaN metric (undefined, e.g. MAPE when all facts are 0) is a dash.

    Args:
        metrics (dict[str, float]): Result of core.calculate_metrics.
        unit (str): Unit of the series for RMSE and MAE.

    Returns:
        str: The table text; the caller prints it.
    """
    units = {"RMSE": unit, "MAE": unit, "MAPE": "%", "R2": ""}
    lines = [f"{'Metric':<8} | {'Value':>10}", "-" * 26]
    for name, value in metrics.items():
        shown = "-" if math.isnan(value) else f"{value:.4f}"
        lines.append(f"{name:<8} | {shown:>10} {units.get(name, '')}".rstrip())
    return "\n".join(lines)
