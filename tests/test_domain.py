import unittest
from datetime import datetime, timezone, timedelta
from aquamonitor.domain import (
    Sensor,
    LevelGauge,
    RainGauge,
    TemperatureSensor,
    SensorError,
    CalibrationError,
    MissingDataError,
    Observation,
    Series
)


class TestSensors(unittest.TestCase):
    """Test suite for verifying sensor validation and calibration."""

    def test_empty_sensor_id_raises_sensor_error(self) -> None:
        """Verify that SensorError is raised when sensor_id is empty."""
        with self.assertRaises(SensorError):
            Sensor(sensor_id="", name="Level Sensor", unit="m")

    def test_invalid_calibration_offset_type_raises_calibration_error(self) -> None:
        """Verify that CalibrationError is raised for non-numeric offsets (string and bool)."""
        # Case 1: String instead of number
        with self.assertRaises(CalibrationError):
            Sensor(
                sensor_id="S-01",
                name="Sensor",
                unit="m",
                calibration_offset="abc",  # Intentional type error
            )

        # Case 2: Boolean value (edge case)
        with self.assertRaises(CalibrationError):
            Sensor(
                sensor_id="S-02",
                name="Sensor",
                unit="m",
                calibration_offset=True,  # Intentional type error
            )

    def test_apply_calibration_correct_calculation(self) -> None:
        """Verify the correct application of the calibration offset."""
        sensor = Sensor(
            sensor_id="S-01",
            name="Level Sensor",
            unit="m",
            calibration_offset=0.5,
        )
        self.assertAlmostEqual(sensor.apply_calibration(10.0), 10.5)

    def test_invalid_max_depth_raises_sensor_error(self) -> None:
        """Verify that SensorError is raised for LevelGauge when max_depth <= 0."""
        # Zero value
        with self.assertRaises(SensorError):
            LevelGauge(sensor_id="L-01", max_depth=0)

        # Negative value
        with self.assertRaises(SensorError):
            LevelGauge(sensor_id="L-02", max_depth=-5.0)

    def test_apply_calibration_non_numeric_raw_value_raises_sensor_error(self) -> None:
        """Verify that SensorError is raised when passing an invalid raw_value."""
        sensor = Sensor(sensor_id="S-01", name="Sensor", unit="m")
        with self.assertRaises(SensorError):
            sensor.apply_calibration("abc")  # Intentional type error

    def test_subclasses_default_values(self) -> None:
        """Verify default values for sensor subclasses."""
        rain_sensor = RainGauge(sensor_id="R-01")
        temp_sensor = TemperatureSensor(sensor_id="T-01")
        level_sensor = LevelGauge(sensor_id="L-01")

        self.assertEqual(rain_sensor.unit, "mm")
        self.assertEqual(temp_sensor.unit, "degC")
        self.assertEqual(level_sensor.unit, "m")
        self.assertEqual(level_sensor.max_depth, 15.0)


class TestObservation(unittest.TestCase):

    def setUp(self) -> None:
        self.now = datetime.now(timezone.utc)
        self.sensor_id = "L-01"

    def test_observation_creation_and_float_conversion(self) -> None:
        """Verify successful observation creation and int-to-float conversion."""
        obs = Observation(self.now, self.sensor_id, 10)
        self.assertEqual(obs.value, 10.0)
        self.assertFalse(obs.is_missing())

    def test_observation_with_none_value(self) -> None:
        """Verify observation creation with a missing value."""
        obs = Observation(self.now, self.sensor_id, None)
        self.assertIsNone(obs.value)
        self.assertTrue(obs.is_missing())

    def test_invalid_value_type_raises_error(self) -> None:
        """Verify that SensorError is raised when passing an invalid value type."""
        with self.assertRaises(SensorError):
            Observation(self.now, self.sensor_id, "invalid")  # Intentional type error

        with self.assertRaises(SensorError):
            Observation(self.now, self.sensor_id, True)  # Intentional type error

    def test_naive_timestamp_raises_error(self) -> None:
        """Verify that SensorError is raised when passing a timezone-naive datetime."""
        naive_dt = datetime.now()
        with self.assertRaises(SensorError):
            Observation(naive_dt, self.sensor_id, 10.0)


class TestSeries(unittest.TestCase):

    def setUp(self) -> None:
        self.sensor_id = "L-01"
        self.now = datetime.now(timezone.utc)
        self.obs_valid = Observation(self.now, self.sensor_id, 12.5)
        self.obs_missing = Observation(self.now + timedelta(seconds=1), self.sensor_id, None)

    def test_series_add_and_len(self) -> None:
        """Verify adding observations and series length."""
        series = Series(self.sensor_id)
        series.add_observation(self.obs_valid)
        self.assertEqual(len(series), 1)

    def test_mismatched_sensor_id_raises_error(self) -> None:
        """Verify error when adding an observation with a different sensor_id."""
        series = Series("L-01")
        other_obs = Observation(self.now, "L-02", 5.0)
        with self.assertRaises(SensorError):
            series.add_observation(other_obs)

    def test_valid_observations_and_missing_count(self) -> None:
        """Verify valid data filtering and missing data counting."""
        series = Series(self.sensor_id, [self.obs_valid, self.obs_missing])
        self.assertEqual(len(series.get_valid_observations()), 1)
        self.assertEqual(series.count_missing(), 1)

    def test_series_values_and_timestamps(self) -> None:
        """Verify retrieval of value lists (including None) and timestamps."""
        series = Series(self.sensor_id, [self.obs_valid, self.obs_missing])

        self.assertEqual(series.values(), [12.5, None])
        self.assertEqual(series.timestamps(), [self.now, self.now + timedelta(seconds=1)])

    def test_chronology_violation_raises_missing_data_error(self) -> None:
        """Verify that MissingDataError is raised on chronology violation during addition."""
        series = Series(self.sensor_id)
        series.add_observation(self.obs_valid)

        past_obs = Observation(self.now - timedelta(minutes=10), self.sensor_id, 5.0)
        with self.assertRaises(MissingDataError):
            series.add_observation(past_obs)


if __name__ == "__main__":
    unittest.main()
