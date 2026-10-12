from datetime import datetime


class HydroError(Exception):
    """Base project exception."""


class SensorError(HydroError):
    """Sensor or sensor parameter error."""


class CalibrationError(SensorError):
    """Sensor calibration error."""


class MissingDataError(HydroError):
    """Missing data or chronology violation error."""


class ThresholdError(HydroError):
    """Threshold violation error (not raised yet)."""


class Sensor:
    """Base class for all hydrological sensors.

    Args:
        sensor_id (str): Unique identifier of the sensor.
        name (str): Human-readable name of the sensor.
        unit (str): Unit of measurement.
        calibration_offset (float): Calibration offset to apply to raw values.

    Raises:
        SensorError: If sensor_id is empty or not a string.
        CalibrationError: If calibration_offset is not a number or is a boolean.
    """

    def __init__(
        self,
        sensor_id: str,
        name: str,
        unit: str,
        calibration_offset: float = 0.0,
    ) -> None:
        if not isinstance(sensor_id, str) or not sensor_id:
            raise SensorError("sensor_id must be a non-empty string.")
        if isinstance(calibration_offset, bool) or not isinstance(
            calibration_offset, (int, float)
        ):
            raise CalibrationError("calibration_offset must be a number.")

        self.sensor_id: str = sensor_id
        self.name: str = name
        self.unit: str = unit
        self.calibration_offset: float = float(calibration_offset)

    def apply_calibration(self, raw_value: int | float) -> float:
        """Applies calibration offset to the raw value.

        Args:
            raw_value (int | float): The raw measured value to calibrate.

        Raises:
            SensorError: If raw_value is not a number or is a boolean.
        """
        if isinstance(raw_value, bool) or not isinstance(
            raw_value, (int, float)
        ):
            raise SensorError("Raw value must be a number.")
        return float(raw_value) + self.calibration_offset


class LevelGauge(Sensor):
    """Water level gauge sensor (in meters).

    Raises:
        SensorError: If max_depth is not a positive number.
    """

    def __init__(
        self,
        sensor_id: str,
        name: str = "Level Gauge",
        unit: str = "m",
        calibration_offset: float = 0.0,
        max_depth: int | float = 15.0,
    ) -> None:
        super().__init__(sensor_id, name, unit, calibration_offset)
        if (
            isinstance(max_depth, bool)
            or not isinstance(max_depth, (int, float))
            or max_depth <= 0
        ):
            raise SensorError("max_depth must be a positive number.")
        self.max_depth: float = float(max_depth)


class RainGauge(Sensor):
    """Precipitation sensor (in millimeters)."""

    def __init__(
        self,
        sensor_id: str,
        name: str = "Rain Gauge",
        unit: str = "mm",
        calibration_offset: float = 0.0,
    ) -> None:
        super().__init__(sensor_id, name, unit, calibration_offset)


class TemperatureSensor(Sensor):
    """Water or air temperature sensor (in degC)."""

    def __init__(
        self,
        sensor_id: str,
        name: str = "Temp Sensor",
        unit: str = "degC",
        calibration_offset: float = 0.0,
    ) -> None:
        super().__init__(sensor_id, name, unit, calibration_offset)


class Observation:
    """A single measurement entity at a hydrological station.

    Args:
        timestamp (datetime): UTC or timezone-aware datetime of the observation.
        sensor_id (str): ID of the sensor that recorded the observation.
        value (int | float | None): Measured value or None if missing.

    Raises:
        SensorError: If timestamp is invalid/naive, sensor_id is empty, or value has incorrect type.
    """

    def __init__(
        self,
        timestamp: datetime,
        sensor_id: str,
        value: int | float | None,
    ) -> None:
        if not isinstance(timestamp, datetime):
            raise SensorError("timestamp must be a datetime object.")
        if timestamp.tzinfo is None:
            raise SensorError("timestamp must contain timezone info (tzinfo).")
        if not isinstance(sensor_id, str) or not sensor_id:
            raise SensorError("sensor_id must be a non-empty string.")

        if value is not None:
            if isinstance(value, bool) or not isinstance(
                value, (int, float)
            ):
                raise SensorError("value must be a number or None.")
            value = float(value)

        self.timestamp: datetime = timestamp
        self.sensor_id: str = sensor_id
        self.value: float | None = value

    def is_missing(self) -> bool:
        """Returns True if the observation value is missing."""
        return self.value is None

    def __repr__(self) -> str:
        return (
            f"Observation(timestamp={self.timestamp.isoformat()!r}, "
            f"sensor_id={self.sensor_id!r}, value={self.value})"
        )


class Series:
    """A collection of observations for a specific sensor.

    Args:
        sensor_id (str): Identifier of the sensor associated with this series.
        observations (list[Observation] | None): Optional initial list of observations.

    Raises:
        SensorError: If sensor_id is empty, observations is not a list,
            observation type is invalid, or sensor_id mismatches.
        MissingDataError: If any observation violates chronology.
    """

    def __init__(
        self,
        sensor_id: str,
        observations: list[Observation] | None = None,
    ) -> None:
        if not isinstance(sensor_id, str) or not sensor_id:
            raise SensorError("sensor_id must be a non-empty string.")

        self.sensor_id: str = sensor_id
        self._observations: list[Observation] = []

        if observations is not None:
            if not isinstance(observations, list):
                raise SensorError("observations must be a list.")
            for obs in observations:
                self.add_observation(obs)

    def add_observation(self, observation: Observation) -> None:
        """Adds a single observation to the series with validation checks.

        Args:
            observation (Observation): The observation object to add.

        Raises:
            SensorError: If observation is not an Observation instance or sensor_id mismatches.
            MissingDataError: If the observation timestamp violates chronology.
        """
        if not isinstance(observation, Observation):
            raise SensorError("Can only add Observation objects.")
        if observation.sensor_id != self.sensor_id:
            raise SensorError("Observation sensor_id does not match the series.")
        if (
            self._observations
            and observation.timestamp < self._observations[-1].timestamp
        ):
            raise MissingDataError("Chronology violation: timestamp is earlier than previous.")
        self._observations.append(observation)

    def values(self) -> list[float | None]:
        """Returns a list of all measurement values."""
        return [obs.value for obs in self._observations]

    def timestamps(self) -> list[datetime]:
        """Returns a list of all timestamps."""
        return [obs.timestamp for obs in self._observations]

    def get_valid_observations(self) -> list[Observation]:
        """Returns a list of observations without missing values."""
        return [obs for obs in self._observations if not obs.is_missing()]

    def count_missing(self) -> int:
        """Returns the count of missing measurements."""
        return sum(1 for obs in self._observations if obs.is_missing())

    def __len__(self) -> int:
        return len(self._observations)