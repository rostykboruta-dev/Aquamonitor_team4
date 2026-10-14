import argparse
import configparser
import json
import os
import sys
from typing import Any


def load_config(config_path: str) -> dict[str, Any]:
    """Read and parse configuration parameters from a JSON or INI file.

    Args:
        config_path (str): Path to the configuration file (.json or .ini).

    Returns:
        dict[str, Any]: A dictionary containing configuration settings.

    Raises:
        ValueError: If the file extension is not supported (.json or .ini).
    """
    if not os.path.exists(config_path):
        print(f"Warning: Configuration file '{config_path}' not found.")
        return {}

    if config_path.endswith(".json"):
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    elif config_path.endswith(".ini"):
        config = configparser.ConfigParser()
        config.read(config_path, encoding="utf-8")
        return {section: dict(config[section]) for section in config.sections()}
    else:
        raise ValueError("Configuration format must be .json or .ini")


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

    fetch_parser = subparsers.add_parser("fetch", help="Fetch and parse data file")
    fetch_parser.add_argument("--input", required=True, help="Path to input file")

    forecast_parser = subparsers.add_parser("forecast", help="Forecast hydrological indicators")
    forecast_parser.add_argument("--sensor", required=True, help="Sensor ID")
    forecast_parser.add_argument("--window", type=int, default=5, help="Window size for calculation")

    report_parser = subparsers.add_parser("report", help="Generate summary report")
    report_parser.add_argument("--input", required=True, help="Path to input file")

    args = parser.parse_args()

    config = load_config(args.config)

    if args.command == "fetch":
        print(f"[FETCH] Processing file: {args.input}")
    elif args.command == "forecast":
        print(f"[FORECAST] Forecasting for sensor '{args.sensor}' (window={args.window})")
    elif args.command == "report":
        print(f"[REPORT] Generating report from file: {args.input}")
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()