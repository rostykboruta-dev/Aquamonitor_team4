from collections.abc import Iterator
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


def _is_number(value: object) -> bool:
    """Returns True for int or float values, but not for bool."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


# Factors that convert a value from a source unit to the project unit.
UNIT_FACTORS: dict[tuple[str, str], float] = {
    ("ft", "m"): 0.3048,
    ("in", "mm"): 25.4,
}


def convert_units(value: int | float, from_unit: str, to_unit: str) -> float:
    """Converts a value between units, e.g. USGS feet to meters.

    Raises:
        SensorError: If value is not a number or the conversion is unknown.
    """
    if not _is_number(value):
        raise SensorError("Value to convert must be a number.")
    if from_unit == to_unit:
        return float(value)
    try:
        return float(value) * UNIT_FACTORS[(from_unit, to_unit)]
    except KeyError:
        raise SensorError(f"Cannot convert {from_unit!r} to {to_unit!r}.") from None


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

    def validate_value(self, value: float) -> None:
        """Checks a calibrated value; the base sensor accepts any number.

        Subclasses override it to reject physically impossible values.
        """

    def measure(
        self,
        timestamp: datetime,
        raw_value: int | float | None,
        status: str | None = None,
        unit: str | None = None,
    ) -> "Observation":
        """Creates an observation of this sensor from a raw reading.

        The reading is converted to the sensor unit, then the calibration
        offset (given in the sensor unit) is applied and the value is validated.
        A missing reading (None) stays missing.

        Args:
            timestamp (datetime): Timezone-aware time of the reading.
            raw_value (int | float | None): Value as the source reported it.
            status (str | None): Data status from the source, e.g. "Provisional".
            unit (str | None): Unit of raw_value, e.g. "ft" from USGS;
                None means it is already in the sensor unit.

        Raises:
            SensorError: If the value is not a number, the unit cannot be
                converted or the value fails validation.
        """
        value = None
        if raw_value is not None:
            if unit is not None:
                raw_value = convert_units(raw_value, unit, self.unit)
            value = self.apply_calibration(raw_value)
            self.validate_value(value)
        return Observation(timestamp, self.sensor_id, value, status)


class LevelGauge(Sensor):
    """Water level gauge sensor (in meters).

    USGS reports gauge height in feet, so readings from it are converted with
    measure(..., unit="ft").

    Args:
        max_depth (int | float): Descriptive depth of the channel; it is not
            used for validation because a constant does not fit every river.
        level_range (tuple[float, float] | None): Allowed (minimum, maximum)
            level, taken from the configuration; None disables the check.

    Raises:
        SensorError: If max_depth is not a positive number or level_range is
            not a pair of numbers with minimum below maximum.
    """

    def __init__(
        self,
        sensor_id: str,
        name: str = "Level Gauge",
        unit: str = "m",
        calibration_offset: float = 0.0,
        max_depth: int | float = 15.0,
        level_range: tuple[float, float] | None = None,
    ) -> None:
        super().__init__(sensor_id, name, unit, calibration_offset)
        if (
            isinstance(max_depth, bool)
            or not isinstance(max_depth, (int, float))
            or max_depth <= 0
        ):
            raise SensorError("max_depth must be a positive number.")
        self.max_depth: float = float(max_depth)

        if level_range is not None:
            if (
                not isinstance(level_range, tuple)
                or len(level_range) != 2
                or not all(_is_number(limit) for limit in level_range)
                or level_range[0] >= level_range[1]
            ):
                raise SensorError("level_range must be (minimum, maximum) numbers.")
            level_range = (float(level_range[0]), float(level_range[1]))
        self.level_range: tuple[float, float] | None = level_range

    def validate_value(self, value: float) -> None:
        """Rejects a level outside level_range.

        Raises:
            SensorError: If the level is outside the allowed range.
        """
        if self.level_range is not None:
            low, high = self.level_range
            if not low <= value <= high:
                raise SensorError(
                    f"level {value} {self.unit} is outside [{low}, {high}]."
                )


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
        status (str | None): Data status from the source, e.g. "Provisional"
            or "Approved" for USGS; None if the source does not give one.

    Raises:
        SensorError: If timestamp is invalid/naive, sensor_id is empty, value
            has incorrect type, or status is not a non-empty string or None.
    """

    def __init__(
        self,
        timestamp: datetime,
        sensor_id: str,
        value: int | float | None,
        status: str | None = None,
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
        if status is not None and (not isinstance(status, str) or not status):
            raise SensorError("status must be a non-empty string or None.")

        self.timestamp: datetime = timestamp
        self.sensor_id: str = sensor_id
        self.value: float | None = value
        self.status: str | None = status

    def is_missing(self) -> bool:
        """Returns True if the observation value is missing."""
        return self.value is None

    def __repr__(self) -> str:
        status = f", status={self.status!r}" if self.status is not None else ""
        return (
            f"Observation(timestamp={self.timestamp.isoformat()!r}, "
            f"sensor_id={self.sensor_id!r}, value={self.value}{status})"
        )


class Series:
    """A collection of observations for a specific sensor.

    Args:
        sensor_id (str): Identifier of the sensor associated with this series.
        observations (list[Observation] | None): Optional initial list of observations.

    Raises:
        SensorError: If sensor_id is empty, observations is not a list,
            observation type is invalid, or sensor_id mismatches.
        MissingDataError: If timestamps are not strictly increasing.
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
            MissingDataError: If the timestamp is not later than the previous one
                (an earlier time or a duplicate).
        """
        if not isinstance(observation, Observation):
            raise SensorError("Can only add Observation objects.")
        if observation.sensor_id != self.sensor_id:
            raise SensorError("Observation sensor_id does not match the series.")
        if self._observations:
            previous = self._observations[-1].timestamp
            if observation.timestamp < previous:
                raise MissingDataError("Chronology violation: timestamp is earlier than previous.")
            if observation.timestamp == previous:
                raise MissingDataError("Chronology violation: duplicate timestamp.")
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

    def __iter__(self) -> Iterator[Observation]:
        """Iterates over the observations in chronological order."""
        return iter(self._observations)


def _check_coordinate(value: float | None, limit: float, name: str) -> float | None:
    """Validates a latitude or longitude; None means unknown.

    Raises:
        HydroError: If the value is not a number within [-limit, limit].
    """
    if value is None:
        return None
    if not _is_number(value) or not -limit <= value <= limit:
        raise HydroError(f"{name} must be a number in [-{limit}, {limit}].")
    return float(value)


class Station:
    """A hydrological station as a composition of its sensors.

    Args:
        code (str): Station code, e.g. "USGS-01646500".
        name (str): Human-readable name of the station.
        latitude (float | None): Latitude in degrees, None if unknown.
        longitude (float | None): Longitude in degrees, None if unknown.

    Raises:
        HydroError: If code or name is empty or a coordinate is out of range.
    """

    def __init__(
        self,
        code: str,
        name: str,
        latitude: float | None = None,
        longitude: float | None = None,
    ) -> None:
        if not isinstance(code, str) or not code.strip():
            raise HydroError("Station code must be a non-empty string.")
        if not isinstance(name, str) or not name.strip():
            raise HydroError("Station name must be a non-empty string.")

        self.code: str = code
        self.name: str = name
        self.latitude: float | None = _check_coordinate(latitude, 90.0, "latitude")
        self.longitude: float | None = _check_coordinate(longitude, 180.0, "longitude")
        self._sensors: dict[str, Sensor] = {}

    def add_sensor(self, sensor: Sensor) -> None:
        """Attaches a sensor to the station.

        Raises:
            SensorError: If sensor is not a Sensor or its id is already used.
        """
        if not isinstance(sensor, Sensor):
            raise SensorError("Can only add Sensor objects.")
        if sensor.sensor_id in self._sensors:
            raise SensorError(f"Sensor {sensor.sensor_id!r} is already on the station.")
        self._sensors[sensor.sensor_id] = sensor

    def get_sensor(self, sensor_id: str) -> Sensor:
        """Returns the sensor with the given id.

        Raises:
            SensorError: If the station has no such sensor.
        """
        try:
            return self._sensors[sensor_id]
        except KeyError:
            raise SensorError(f"Station {self.code!r} has no sensor {sensor_id!r}.") from None

    @property
    def sensors(self) -> list[Sensor]:
        """Sensors of the station in the order they were added."""
        return list(self._sensors.values())

    def __len__(self) -> int:
        return len(self._sensors)

    def __repr__(self) -> str:
        return f"Station(code={self.code!r}, name={self.name!r}, sensors={len(self)})"


class Basin:
    """A river basin as a collection of stations.

    Args:
        name (str): Name of the basin, e.g. "Potomac".

    Raises:
        HydroError: If name is empty.
    """

    def __init__(self, name: str) -> None:
        if not isinstance(name, str) or not name.strip():
            raise HydroError("Basin name must be a non-empty string.")
        self.name: str = name
        self._stations: dict[str, Station] = {}

    def add_station(self, station: Station) -> None:
        """Adds a station to the basin.

        Raises:
            HydroError: If station is not a Station or its code is already used.
        """
        if not isinstance(station, Station):
            raise HydroError("Can only add Station objects.")
        if station.code in self._stations:
            raise HydroError(f"Station {station.code!r} is already in the basin.")
        self._stations[station.code] = station

    def get_station(self, code: str) -> Station:
        """Returns the station with the given code.

        Raises:
            HydroError: If the basin has no such station.
        """
        try:
            return self._stations[code]
        except KeyError:
            raise HydroError(f"Basin {self.name!r} has no station {code!r}.") from None

    @property
    def stations(self) -> list[Station]:
        """Stations of the basin in the order they were added."""
        return list(self._stations.values())

    def __len__(self) -> int:
        return len(self._stations)