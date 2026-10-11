import math
import unittest

from aquamonitor.core import moving_average, moving_median, moving_std


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


if __name__ == "__main__":
    unittest.main()