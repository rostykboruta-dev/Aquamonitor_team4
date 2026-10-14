import configparser
import json
import os
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
