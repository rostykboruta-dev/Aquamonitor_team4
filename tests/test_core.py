import math
import unittest

from datetime import datetime, timedelta, timezone
from pathlib import Path

from aquamonitor.core import (
    evaluate_forecast,
    walk_forward,
    calculate_metrics,
    forecast_timestamps,
    hours_to_steps,
    interpolation_error,
    linear_interpolate,
    moving_average,
    moving_median,
    moving_std,
    naive_forecast,
    nearest_interpolate,
)
from aquamonitor.dataio import parse_usgs_json
from aquamonitor.domain import MissingDataError, Observation, Series

START = datetime(2026, 10, 18, 12, 0, tzinfo=timezone.utc)
SAMPLE = Path(__file__).parent / "data" / "usgs_sample.json"


def make_series(points: list[tuple[int, float | None]]) -> Series:
    """Build a Series from (minutes after START, value) pairs."""
    return Series("S1", [Observation(START + timedelta(minutes=m), "S1", v) for m, v in points])


class TestRollingStats(unittest.TestCase):
    """Tests for pure Python rolling statistics."""

    def test_moving_average_values(self) -> None:
        """Moving average uses partial windows at the start of the series."""
        self.assertEqual(
            moving_average([1, 2, 3, 4, 5], 3), [1.0, 1.5, 2.0, 3.0, 4.0]
        )

    def test_moving_median_odd_and_even_windows(self) -> None:
        """Moving median handles odd and even window lengths."""
        self.assertEqual(
            moving_median([5, 1, 3, 2, 4], 3), [5.0, 3.0, 3.0, 2.0, 3.0]
        )
        self.assertEqual(moving_median([1, 2, 3, 4], 4)[-1], 2.5)

    def test_moving_std_sample_formula(self) -> None:
        """Moving std uses N - 1 and returns 0.0 for a single-point window."""
        result = moving_std([1, 3], 2)
        self.assertEqual(result[0], 0.0)
        self.assertAlmostEqual(result[1], math.sqrt(2))
        self.assertAlmostEqual(
            moving_std([2, 4, 4, 4, 5, 5, 7, 9], 8)[-1], 2.138089935
        )

    def test_result_length_equals_input_length(self) -> None:
        """Every function returns one value per input value."""
        data = [1.0, 2.0, 3.0, 4.0, 5.0]
        for func in (moving_average, moving_median, moving_std):
            self.assertEqual(len(func(data, 3)), len(data))
            self.assertEqual(len(func(data, 10)), len(data))

    def test_window_one_returns_same_values(self) -> None:
        """A window of one leaves average and median unchanged."""
        self.assertEqual(moving_average([3, 1, 2], 1), [3.0, 1.0, 2.0])
        self.assertEqual(moving_median([3, 1, 2], 1), [3.0, 1.0, 2.0])

    def test_invalid_window_raises_value_error(self) -> None:
        """Non-positive, boolean or non-integer window is rejected."""
        for bad in (0, -1, True, 2.5):
            with self.assertRaises(ValueError):
                moving_average([1, 2, 3], bad)

    def test_empty_values_raise_value_error(self) -> None:
        """An empty series is rejected."""
        for func in (moving_average, moving_median, moving_std):
            with self.assertRaises(ValueError):
                func([], 3)

    def test_non_numeric_values_raise_type_error(self) -> None:
        """None and strings inside the series are rejected."""
        with self.assertRaises(TypeError):
            moving_median([1.0, None, 3.0], 2)
        with self.assertRaises(TypeError):
            moving_std([1.0, "a", 3.0], 2)


class TestInterpolation(unittest.TestCase):
    """Week 2: filling gaps and checking the quality of the filling."""

    def test_linear_uses_real_time_between_points(self) -> None:
        """A gap 10 minutes into a 40-minute interval gets a quarter of the change."""
        series = make_series([(0, 1.0), (10, None), (40, 5.0)])

        self.assertEqual(linear_interpolate(series), [1.0, 2.0, 5.0])

    def test_gaps_at_the_edges_take_the_nearest_known_value(self) -> None:
        series = make_series([(0, None), (5, 2.0), (10, 4.0), (15, None)])

        self.assertEqual(linear_interpolate(series), [2.0, 2.0, 4.0, 4.0])
        self.assertEqual(nearest_interpolate(series), [2.0, 2.0, 4.0, 4.0])

    def test_nearest_takes_the_closer_point_and_the_earlier_on_a_tie(self) -> None:
        series = make_series([(0, 1.0), (2, None), (5, None), (10, 9.0), (12, None), (14, 3.0)])

        self.assertEqual(nearest_interpolate(series), [1.0, 1.0, 1.0, 9.0, 9.0, 3.0])

    def test_result_has_no_gaps_and_works_with_moving_average(self) -> None:
        series = make_series([(0, 1.0), (5, None), (10, None), (15, 4.0)])
        filled = linear_interpolate(series)

        self.assertEqual(filled, [1.0, 2.0, 3.0, 4.0])
        self.assertEqual(moving_average(filled, 2)[-1], 3.5)

    def test_empty_series_gives_empty_list(self) -> None:
        self.assertEqual(linear_interpolate(Series("S1")), [])

    def test_bad_input_is_rejected(self) -> None:
        with self.assertRaises(MissingDataError):
            linear_interpolate(make_series([(0, None), (5, None)]))
        with self.assertRaises(TypeError):
            nearest_interpolate([1.0, None])  # type: ignore[arg-type]

    def test_quality_check_on_hidden_points(self) -> None:
        """On a straight line linear interpolation is exact, nearest is not."""
        series = make_series([(5 * i, 0.1 * i) for i in range(20)])

        self.assertAlmostEqual(interpolation_error(series, "linear", every=3), 0.0)
        self.assertAlmostEqual(interpolation_error(series, "nearest", every=3), 0.1)

    def test_quality_check_rejects_bad_arguments(self) -> None:
        series = make_series([(5 * i, float(i)) for i in range(10)])
        with self.assertRaises(ValueError):
            interpolation_error(series, "cubic")
        with self.assertRaises(ValueError):
            interpolation_error(series, every=1)
        with self.assertRaises(ValueError):
            interpolation_error(make_series([(0, 1.0), (5, 2.0)]))

    def test_quality_on_real_usgs_sample(self) -> None:
        """On 5-minute USGS data linear interpolation errs by less than 0.05 ft."""
        observations = parse_usgs_json(SAMPLE.read_text(encoding="utf-8"))
        series = Series(observations[0].sensor_id, observations)

        self.assertLess(interpolation_error(series, "linear"), 0.05)


class TestNaiveForecast(unittest.TestCase):

    def test_repeats_the_last_value(self) -> None:
        self.assertEqual(naive_forecast([2.0, 3.0, 3.5], 3), [3.5, 3.5, 3.5])

    def test_invalid_horizon_or_values(self) -> None:
        for bad in (0, -1, True, 2.5):
            with self.subTest(bad), self.assertRaises(ValueError):
                naive_forecast([1.0], bad)
        with self.assertRaises(ValueError):
            naive_forecast([], 3)
        with self.assertRaises(TypeError):
            naive_forecast([1.0, None], 3)

    def test_hours_to_steps_for_five_minute_data(self) -> None:
        stamps = [START + timedelta(minutes=5 * i) for i in range(10)]

        self.assertEqual(hours_to_steps(stamps, 12), 144)
        self.assertEqual(hours_to_steps(stamps, 0.01), 1)

    def test_hours_to_steps_rejects_bad_input(self) -> None:
        stamps = [START, START + timedelta(minutes=5)]
        for bad_hours in (0, -3, True):
            with self.subTest(bad_hours), self.assertRaises(ValueError):
                hours_to_steps(stamps, bad_hours)
        with self.assertRaises(ValueError):
            hours_to_steps([START], 12)
        with self.assertRaises(ValueError):
            hours_to_steps([START, START], 12)


class TestMaxGap(unittest.TestCase):

    def test_max_gap_blocks_long_gaps_only(self) -> None:
        series = make_series([(0, 1.0), (60, None), (120, 3.0), (130, None), (140, 5.0)])

        with self.assertRaises(MissingDataError):
            linear_interpolate(series, max_gap=timedelta(hours=1))
        self.assertEqual(linear_interpolate(series, max_gap=timedelta(hours=2))[1], 2.0)
        self.assertEqual(linear_interpolate(series)[1], 2.0)

    def test_max_gap_applies_to_the_edges(self) -> None:
        series = make_series([(0, None), (180, 4.0)])

        with self.assertRaises(MissingDataError):
            linear_interpolate(series, max_gap=timedelta(hours=1))


class TestForecastTimestamps(unittest.TestCase):

    def test_forecast_timestamps_continue_the_series(self) -> None:
        stamps = [START + timedelta(minutes=5 * i) for i in range(4)]

        result = forecast_timestamps(stamps, 3)

        self.assertEqual(result[0], START + timedelta(minutes=20))
        self.assertEqual(result[-1], START + timedelta(minutes=30))

    def test_forecast_timestamps_reject_bad_input(self) -> None:
        stamps = [START + timedelta(minutes=5 * i) for i in range(4)]

        with self.assertRaises(ValueError):
            forecast_timestamps(stamps[:1], 3)
        with self.assertRaises(ValueError):
            forecast_timestamps(stamps, 0)


class TestMetrics(unittest.TestCase):

    def test_metrics_on_hand_calculated_example(self) -> None:
        """Errors 1, -1, 2 on facts 2, 4, 8 give known RMSE, MAE, MAPE and R2."""
        result = calculate_metrics([2, 4, 8], [3, 3, 10])

        self.assertAlmostEqual(result["RMSE"], math.sqrt(2.0))
        self.assertAlmostEqual(result["MAE"], 4 / 3)
        self.assertAlmostEqual(result["MAPE"], (0.5 + 0.25 + 0.25) / 3 * 100)
        self.assertAlmostEqual(result["R2"], 1 - 6 / (56 / 3))

    def test_perfect_forecast_and_zero_facts(self) -> None:
        perfect = calculate_metrics([1.0, 2.0, 3.0], [1.0, 2.0, 3.0])
        self.assertEqual((perfect["RMSE"], perfect["MAE"], perfect["R2"]), (0.0, 0.0, 1.0))

        with_zero = calculate_metrics([0, 2], [1, 3])
        self.assertAlmostEqual(with_zero["MAPE"], 50.0)
        self.assertTrue(math.isnan(calculate_metrics([0, 0], [1, 1])["MAPE"]))
        self.assertTrue(math.isnan(calculate_metrics([5, 5], [5, 6])["R2"]))

    def test_bad_input_is_rejected(self) -> None:
        for y_true, y_pred in (([1, 2], [1]), ([], []), ([1], [])):
            with self.subTest((y_true, y_pred)), self.assertRaises(ValueError):
                calculate_metrics(y_true, y_pred)
        with self.assertRaises(TypeError):
            calculate_metrics([1, None], [1, 2])  # type: ignore[list-item]


class TestEvaluation(unittest.TestCase):

    def test_evaluate_forecast_holds_out_the_last_points(self) -> None:
        """The naive forecast repeats 3, the held-out facts are 4 and 5."""
        result = evaluate_forecast([1, 2, 3, 4, 5], 2)

        self.assertAlmostEqual(result["MAE"], 1.5)
        self.assertAlmostEqual(result["RMSE"], math.sqrt(2.5))

    def test_evaluate_forecast_rejects_bad_horizon(self) -> None:
        for horizon in (0, -1, 5, 1.5, True):
            with self.subTest(horizon), self.assertRaises(ValueError):
                evaluate_forecast([1, 2, 3, 4, 5], horizon)  # type: ignore[arg-type]

    def test_walk_forward_on_a_straight_line(self) -> None:
        """On 0, 1, 2, ... the naive forecast for 1 step is always off by 1."""
        result = walk_forward([float(i) for i in range(10)], horizon=1, min_train=3)

        self.assertAlmostEqual(result["MAE"], 1.0)
        self.assertAlmostEqual(result["RMSE"], 1.0)

    def test_walk_forward_averages_several_windows(self) -> None:
        """Two windows of 2 points are averaged into one result."""
        result = walk_forward([1.0, 2.0, 3.0, 4.0, 5.0, 6.0], horizon=2, min_train=2)

        self.assertAlmostEqual(result["MAE"], 1.5)

    def test_walk_forward_rejects_short_series(self) -> None:
        with self.assertRaises(ValueError):
            walk_forward([1.0, 2.0, 3.0], horizon=2, min_train=3)

    def test_real_sample_metrics_use_the_cli_horizon(self) -> None:
        observations = parse_usgs_json(SAMPLE.read_text(encoding="utf-8"))
        values = linear_interpolate(Series(observations[0].sensor_id, observations))

        result = evaluate_forecast(values, 12)

        self.assertGreaterEqual(result["MAE"], 0.0)
        self.assertGreaterEqual(result["RMSE"], result["MAE"])


if __name__ == "__main__":
    unittest.main()
