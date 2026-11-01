from datetime import datetime, timezone
import io
import unittest
from unittest.mock import patch

from aquamonitor.analytics import aggregate_by_period, generate_console_report
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


if __name__ == "__main__":
    unittest.main()