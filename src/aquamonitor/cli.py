import argparse
import configparser
import json
import os
import sys
from statistics import median
from typing import Any

from aquamonitor.analytics import generate_console_report
from aquamonitor.core import hours_to_steps, linear_interpolate, naive_forecast
from aquamonitor.dataio import clean_observations, fetch_usgs_json, parse_usgs_json
from aquamonitor.domain import HydroError, Observation, Series
from aquamonitor.infra import log_call, logger, setup_logging, timed

CONFIG_SECTION = "aquamonitor"


def load_config(config_path: str) -> dict[str, Any]:
    """Read configuration parameters from a JSON or INI file.

    A JSON file must hold one object with the settings at the top level.
    An INI file keeps them in the [aquamonitor] section; values stay strings.
    Both give the same flat dictionary, e.g. {"horizon": 12, "group_by": "day"}.

    Args:
        config_path (str): Path to the configuration file (.json or .ini).

    Returns:
        dict[str, Any]: Configuration settings; {} if the file does not exist.

    Raises:
        ValueError: If the extension is not .json or .ini, the JSON is broken
            or is not an object, or the INI file is broken.
    """
    if not os.path.exists(config_path):
        logger.warning("Configuration file %r not found, using defaults.", config_path)
        return {}

    if config_path.endswith(".json"):
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)  # JSONDecodeError is a ValueError
        if not isinstance(data, dict):
            raise ValueError(f"configuration {config_path!r} must be a JSON object.")
        return data
    if config_path.endswith(".ini"):
        config = configparser.ConfigParser()
        try:
            config.read(config_path, encoding="utf-8")
        except configparser.Error as exc:
            raise ValueError(f"broken configuration {config_path!r}: {exc}") from exc
        if not config.has_section(CONFIG_SECTION):
            logger.warning("No [%s] section in %r, using defaults.", CONFIG_SECTION, config_path)
            return {}
        return dict(config[CONFIG_SECTION])
    raise ValueError("Configuration format must be .json or .ini")


def _read_text(path: str) -> str:
    """Read a UTF-8 text file and return its content."""
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _pick_series(observations: list[Observation], sensor_id: str | None) -> Series:
    """Build a Series for one sensor from a mixed list of observations.

    Raises:
        HydroError: If there are no observations, the sensor is unknown,
            or several sensors are present and none was chosen.
    """
    ids = sorted({obs.sensor_id for obs in observations})
    if not ids:
        raise HydroError("input contains no observations.")
    if sensor_id is None:
        if len(ids) > 1:
            raise HydroError(f"several sensors, choose one with --sensor: {', '.join(ids)}")
        sensor_id = ids[0]
    elif sensor_id not in ids:
        raise HydroError(f"sensor {sensor_id!r} not found; available: {', '.join(ids)}")
    return Series(sensor_id, [obs for obs in observations if obs.sensor_id == sensor_id])


def _load_series(path: str, sensor_id: str | None) -> Series:
    """Read a saved USGS JSON file, clean it and return one sensor as a Series."""
    observations, rejected = clean_observations(parse_usgs_json(_read_text(path)))
    if rejected:
        logger.warning("rejected %d records: %s", len(rejected), "; ".join(rejected[:5]))
        print(f"[CLEAN] Rejected {len(rejected)} records (details in the log).", file=sys.stderr)
    return _pick_series(observations, sensor_id)


@log_call
@timed
def _run_fetch(args: argparse.Namespace, config: dict[str, Any]) -> None:
    """Download USGS data and save the JSON text to a file."""
    period = args.period or config.get("period", "P7D")
    text = fetch_usgs_json(args.site, period=period)
    count = len(parse_usgs_json(text))
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"[FETCH] Saved {count} records to {args.out}")


@log_call
@timed
def _run_report(args: argparse.Namespace, config: dict[str, Any]) -> None:
    """Read a saved JSON file and print the summary report."""
    group_by = args.group_by or config.get("group_by", "day")
    print(generate_console_report(_load_series(args.input, args.sensor), group_by))


@log_call
@timed
def _run_forecast(args: argparse.Namespace, config: dict[str, Any]) -> None:
    """Fill gaps in a saved series and print a naive forecast for the horizon."""
    hours = args.horizon if args.horizon is not None else float(config.get("horizon", 12))
    series = _load_series(args.input, args.sensor)
    values = linear_interpolate(series)
    stamps = series.timestamps()
    steps = hours_to_steps(stamps, hours)
    step = median(b - a for a, b in zip(stamps, stamps[1:]))
    forecast = naive_forecast(values, steps)
    print(f"\n=== NAIVE FORECAST FOR SENSOR: {series.sensor_id} ===")
    print(f"Last observation : {stamps[-1].isoformat()}  {values[-1]:.2f}")
    print(f"Horizon          : {hours} h ({steps} steps of {step})")
    print(f"Forecast         : {forecast[0]:.2f} for every step until {(stamps[-1] + step * steps).isoformat()}")


def main() -> None:
    """Parse command-line arguments and execute the corresponding command"""
    parser = argparse.ArgumentParser(
        prog="aquamonitor",
        description="AquaMonitor — CLI tool for hydrological data processing and analysis",
    )
    parser.add_argument(
        "--config", default="config.json", help="Path to configuration file (.json / .ini)"
    )

    subparsers = parser.add_subparsers(dest="command", help="CLI commands")

    fetch_parser = subparsers.add_parser("fetch", help="Download USGS data to a file")
    fetch_parser.add_argument("--site", required=True, help="USGS site number, e.g. 01646500")
    fetch_parser.add_argument("--period", help="ISO 8601 period, e.g. P7D (default P7D)")
    fetch_parser.add_argument("--out", required=True, help="Path to the output JSON file")

    forecast_parser = subparsers.add_parser("forecast", help="Forecast hydrological indicators")
    forecast_parser.add_argument("--input", required=True, help="Path to input file")
    forecast_parser.add_argument("--sensor", help="Sensor id if the file has several")
    forecast_parser.add_argument("--horizon", type=float, help="Forecast horizon in hours (default 12)")

    report_parser = subparsers.add_parser("report", help="Generate summary report")
    report_parser.add_argument("--input", required=True, help="Path to input file")
    report_parser.add_argument("--sensor", help="Sensor id if the file has several")
    report_parser.add_argument(
        "--group-by", choices=["day", "week", "month"], help="Aggregation period (default day)"
    )

    args = parser.parse_args()

    setup_logging()

    try:
        config = load_config(args.config)
        if args.command == "fetch":
            _run_fetch(args, config)
        elif args.command == "report":
            _run_report(args, config)
        elif args.command == "forecast":
            _run_forecast(args, config)
        else:
            parser.print_help()
            sys.exit(1)
    except (HydroError, ValueError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()