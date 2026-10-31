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
    Series,
    HydroError,
    Station,
    Basin,
    convert_units,
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


class TestMeasureAndLevelRange(unittest.TestCase):
    """Week 2: sensor readings, calibration and level range from configuration."""

    def setUp(self) -> None:
        self.now = datetime(2026, 10, 18, 12, 0, tzinfo=timezone.utc)

    def test_measure_applies_calibration_and_keeps_status(self) -> None:
        """measure() returns an observation of this sensor with the offset applied."""
        gauge = LevelGauge("USGS-01646500-00065", calibration_offset=0.1)
        obs = gauge.measure(self.now, 2.9, status="Provisional")

        self.assertEqual(obs.sensor_id, "USGS-01646500-00065")
        self.assertAlmostEqual(obs.value, 3.0)
        self.assertEqual(obs.status, "Provisional")

    def test_measure_keeps_missing_value(self) -> None:
        obs = LevelGauge("L-01", level_range=(0.0, 1.0)).measure(self.now, None)

        self.assertTrue(obs.is_missing())

    def test_real_usgs_levels_pass_configured_range(self) -> None:
        """USGS sample levels (2.86-3.22 ft) become meters and pass the range."""
        gauge = LevelGauge("L-01", level_range=(-2.0, 12.0))
        for feet in (2.86, 3.22):
            with self.subTest(feet):
                obs = gauge.measure(self.now, feet, unit="ft")
                self.assertAlmostEqual(obs.value, feet * 0.3048)
        self.assertEqual(gauge.measure(self.now, 12.0).value, 12.0)

    def test_feet_are_converted_before_calibration(self) -> None:
        """The offset is in meters, so it is added after converting feet."""
        gauge = LevelGauge("L-01", calibration_offset=0.1)

        self.assertAlmostEqual(gauge.measure(self.now, 10.0, unit="ft").value, 3.148)

    def test_rain_inches_are_converted_to_millimeters(self) -> None:
        self.assertAlmostEqual(RainGauge("R-01").measure(self.now, 1.0, unit="in").value, 25.4)

    def test_unknown_unit_raises_sensor_error(self) -> None:
        with self.assertRaises(SensorError):
            LevelGauge("L-01").measure(self.now, 1.0, unit="km")
        with self.assertRaises(SensorError):
            convert_units("3.1", "ft", "m")  # Intentional type error

    def test_same_unit_is_not_converted(self) -> None:
        self.assertEqual(convert_units(2, "m", "m"), 2.0)

    def test_level_outside_range_raises_sensor_error(self) -> None:
        gauge = LevelGauge("L-01", level_range=(0.0, 30.0))
        for value in (-0.1, 30.5):
            with self.subTest(value), self.assertRaises(SensorError):
                gauge.measure(self.now, value)

    def test_invalid_level_range_raises_sensor_error(self) -> None:
        for bad in ((5.0, 1.0), (1.0, 1.0), (0.0,), [0.0, 1.0], (0.0, "10"), (False, 1.0)):
            with self.subTest(bad), self.assertRaises(SensorError):
                LevelGauge("L-01", level_range=bad)  # Intentional type error

    def test_no_range_means_no_check(self) -> None:
        """Without a configured range, max_depth does not reject real data."""
        self.assertEqual(LevelGauge("L-01").measure(self.now, 99.0).value, 99.0)


class TestObservationStatus(unittest.TestCase):

    def setUp(self) -> None:
        self.now = datetime.now(timezone.utc)

    def test_status_is_optional(self) -> None:
        self.assertIsNone(Observation(self.now, "L-01", 1.0).status)
        self.assertEqual(Observation(self.now, "L-01", 1.0, "Approved").status, "Approved")

    def test_invalid_status_raises_sensor_error(self) -> None:
        for bad in ("", 5, True):
            with self.subTest(bad), self.assertRaises(SensorError):
                Observation(self.now, "L-01", 1.0, bad)  # Intentional type error


class TestSeriesIterationAndDuplicates(unittest.TestCase):

    def setUp(self) -> None:
        self.now = datetime(2026, 10, 18, 12, 0, tzinfo=timezone.utc)
        self.data = [Observation(self.now + timedelta(minutes=5 * i), "L-01", float(i))
                     for i in range(3)]

    def test_iteration_yields_observations_in_order(self) -> None:
        series = Series("L-01", self.data)

        self.assertEqual(list(series), self.data)
        self.assertEqual([obs.value for obs in series], [0.0, 1.0, 2.0])

    def test_duplicate_timestamp_raises_missing_data_error(self) -> None:
        series = Series("L-01", self.data)
        with self.assertRaises(MissingDataError):
            series.add_observation(Observation(self.data[-1].timestamp, "L-01", 9.0))


class TestStation(unittest.TestCase):

    def test_station_is_a_composition_of_sensors(self) -> None:
        station = Station("USGS-01646500", "Potomac at Little Falls", 38.95, -77.13)
        level = LevelGauge("USGS-01646500-00065")
        temperature = TemperatureSensor("USGS-01646500-00010")
        station.add_sensor(level)
        station.add_sensor(temperature)

        self.assertEqual(len(station), 2)
        self.assertIs(station.get_sensor("USGS-01646500-00065"), level)
        self.assertEqual(station.sensors, [level, temperature])

    def test_duplicate_or_missing_sensor_raises_sensor_error(self) -> None:
        station = Station("S-1", "Station")
        station.add_sensor(RainGauge("R-01"))
        with self.assertRaises(SensorError):
            station.add_sensor(RainGauge("R-01"))
        with self.assertRaises(SensorError):
            station.get_sensor("R-02")
        with self.assertRaises(SensorError):
            station.add_sensor("R-03")  # Intentional type error

    def test_invalid_station_data_raises_hydro_error(self) -> None:
        bad_arguments = [("", "Name"), ("S-1", "  "), ("S-1", "Name", 95.0, 0.0),
                         ("S-1", "Name", 0.0, -181.0), ("S-1", "Name", True, 0.0)]
        for args in bad_arguments:
            with self.subTest(args), self.assertRaises(HydroError):
                Station(*args)


class TestBasin(unittest.TestCase):

    def test_basin_collects_stations(self) -> None:
        basin = Basin("Potomac")
        first, second = Station("S-1", "Upper"), Station("S-2", "Lower")
        basin.add_station(first)
        basin.add_station(second)

        self.assertEqual(len(basin), 2)
        self.assertIs(basin.get_station("S-2"), second)
        self.assertEqual(basin.stations, [first, second])

    def test_invalid_basin_operations_raise_hydro_error(self) -> None:
        basin = Basin("Potomac")
        basin.add_station(Station("S-1", "Upper"))
        with self.assertRaises(HydroError):
            basin.add_station(Station("S-1", "Copy"))
        with self.assertRaises(HydroError):
            basin.get_station("S-9")
        with self.assertRaises(HydroError):
            Basin("")


if __name__ == "__main__":
    unittest.main()
