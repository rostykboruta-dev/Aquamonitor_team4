from datetime import datetime, timezone
import io
import unittest
from unittest.mock import patch

import os
import tempfile

from aquamonitor.analytics import (
    aggregate_by_period,
    build_level_histogram,
    build_time_series_plot,
    format_metrics_table,
    generate_console_report,
    styled_figure,
)
from aquamonitor.domain import Observation, Series


class TestAnalytics(unittest.TestCase):
    """Unit tests for analytics and reporting functions."""

    def setUp(self) -> None:
        """Set up a sample Series for testing."""
        obs1 = Observation(
            timestamp=datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc),
            sensor_id="S1",
            value=10.0,
        )
        obs2 = Observation(
            timestamp=datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc),
            sensor_id="S1",
            value=20.0,
        )
        obs3 = Observation(
            timestamp=datetime(2026, 1, 2, 10, 0, tzinfo=timezone.utc),
            sensor_id="S1",
            value=None,
        )
        self.sample_series = Series(sensor_id="S1", observations=[obs1, obs2, obs3])

    def test_aggregate_by_period_day(self) -> None:
        """Test period aggregation by day."""
        stats = aggregate_by_period(self.sample_series, period="day")

        self.assertIn("2026-01-01", stats)
        self.assertEqual(stats["2026-01-01"]["min"], 10.0)
        self.assertEqual(stats["2026-01-01"]["max"], 20.0)
        self.assertEqual(stats["2026-01-01"]["avg"], 15.0)
        self.assertEqual(stats["2026-01-01"]["count"], 2)
        self.assertEqual(stats["2026-01-01"]["missing_count"], 0)

        self.assertIn("2026-01-02", stats)
        self.assertIsNone(stats["2026-01-02"]["min"])
        self.assertIsNone(stats["2026-01-02"]["max"])
        self.assertIsNone(stats["2026-01-02"]["avg"])
        self.assertEqual(stats["2026-01-02"]["count"], 1)
        self.assertEqual(stats["2026-01-02"]["missing_count"], 1)

    def test_aggregate_by_period_invalid_period(self) -> None:
        """Test that invalid period raises ValueError."""
        with self.assertRaises(ValueError):
            aggregate_by_period(self.sample_series, period="year")  # type: ignore

    def test_generate_console_report(self) -> None:
        """Test that the report is returned as text and not printed."""
        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            report = generate_console_report(self.sample_series, period="day")

            self.assertIn("SUMMARY REPORT FOR SENSOR: S1", report)
            self.assertIn("2026-01-01", report)
            self.assertIn("15.00", report)
            self.assertEqual(mock_stdout.getvalue(), "")

    def test_report_shows_dash_for_period_without_values(self) -> None:
        """Test that a period with only missing values shows dashes, not zeros."""
        report = generate_console_report(self.sample_series, period="day")
        row = next(line for line in report.splitlines() if line.startswith("2026-01-02"))

        self.assertIn("-", row)
        self.assertNotIn("0.00", row)



class TestPlots(unittest.TestCase):
    """Week 3: the two matplotlib plots and their common style."""

    def setUp(self) -> None:
        start = datetime(2026, 10, 18, 12, 0, tzinfo=timezone.utc)
        self.series = Series("S1", [
            Observation(start.replace(minute=5 * i), "S1", None if i == 3 else 1.0 + 0.1 * i)
            for i in range(8)
        ])
        self.forecast = [(start.replace(hour=13, minute=5 * i), 1.7) for i in range(4)]
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def path(self, name: str) -> str:
        return os.path.join(self.tmp.name, name)

    def test_time_series_plot_with_gap_and_forecast_is_saved(self) -> None:
        build_time_series_plot(self.series, self.path("level.png"), forecast=self.forecast)

        with open(self.path("level.png"), "rb") as f:
            self.assertEqual(f.read(8), b"\x89PNG\r\n\x1a\n")

    def test_histogram_is_saved(self) -> None:
        build_level_histogram(self.series, self.path("hist.png"), bins=5)

        self.assertGreater(os.path.getsize(self.path("hist.png")), 0)

    def test_common_style_sets_labels_and_grid(self) -> None:
        _, ax = styled_figure("Title", "Time", "Level, m")

        self.assertEqual((ax.get_title(), ax.get_xlabel(), ax.get_ylabel()),
                         ("Title", "Time", "Level, m"))

    def test_bad_input_raises_value_error(self) -> None:
        empty = Series("S1", [Observation(datetime(2026, 1, 1, tzinfo=timezone.utc), "S1", None)])
        with self.assertRaises(ValueError):
            build_time_series_plot(empty, self.path("a.png"))
        with self.assertRaises(ValueError):
            build_level_histogram(empty, self.path("b.png"))
        for bins in (0, -2, True, 2.5):
            with self.subTest(bins), self.assertRaises(ValueError):
                build_level_histogram(self.series, self.path("c.png"), bins=bins)



class TestMetricsTable(unittest.TestCase):

    def test_values_units_and_nan(self) -> None:
        metrics = {"RMSE": 0.0123, "MAE": 0.01, "MAPE": float("nan"), "R2": 0.5}
        table = format_metrics_table(metrics)

        self.assertIn("RMSE     |     0.0123 m", table)
        self.assertIn("MAPE     |          -", table)
        self.assertIn("R2       |     0.5000", table)


if __name__ == "__main__":
    unittest.main()
