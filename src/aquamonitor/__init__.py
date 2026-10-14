from .domain import (
    # Exceptions
    HydroError,
    SensorError,
    CalibrationError,
    MissingDataError,
    ThresholdError,
    # Sensors
    Sensor,
    LevelGauge,
    RainGauge,
    TemperatureSensor,
    # Data and series
    Observation,
    Series,
)

__version__ = "0.1.0"

__all__ = [
    # Exceptions
    "HydroError",
    "SensorError",
    "CalibrationError",
    "MissingDataError",
    "ThresholdError",
    # Sensors
    "Sensor",
    "LevelGauge",
    "RainGauge",
    "TemperatureSensor",
    # Data and series
    "Observation",
    "Series",
]
