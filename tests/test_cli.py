import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from aquamonitor.cli import load_config, main


SAMPLE = Path(__file__).parent / "data" / "usgs_sample.json"


class TestCLI(unittest.TestCase):
    """Unit tests for CLI interface and config loader"""

    def setUp(self) -> None:
        """Keep main() from creating aquamonitor.log in the working directory"""
        patcher = patch("aquamonitor.cli.setup_logging")
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_load_config_json(self) -> None:
        """Test loading configuration from a JSON file"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = os.path.join(tmp_dir, "config.json")
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump({"setting": "enabled"}, f)

            data = load_config(config_path)
            self.assertEqual(data, {"setting": "enabled"})

    def test_load_config_ini(self) -> None:
        """Test loading the [aquamonitor] section of an INI file as a flat dict"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = os.path.join(tmp_dir, "config.ini")
            with open(config_path, "w", encoding="utf-8") as f:
                f.write("[aquamonitor]\nkey = value\n")

            data = load_config(config_path)
            self.assertEqual(data, {"key": "value"})

    def test_load_config_ini_without_section(self) -> None:
        """Test returning empty dict when an INI file has no [aquamonitor] section"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = os.path.join(tmp_dir, "config.ini")
            with open(config_path, "w", encoding="utf-8") as f:
                f.write("[other]\nkey = value\n")

            self.assertEqual(load_config(config_path), {})

    def test_load_config_file_not_found(self) -> None:
        """Test returning empty dict when config file does not exist"""
        data = load_config("non_existent_config.json")
        self.assertEqual(data, {})

    def test_load_config_unsupported_extension(self) -> None:
        """Test raising ValueError for unsupported file extensions"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = os.path.join(tmp_dir, "config.txt")
            with open(config_path, "w", encoding="utf-8") as f:
                f.write("content")

            with self.assertRaises(ValueError):
                load_config(config_path)

    def test_load_config_invalid_content(self) -> None:
        """Test raising ValueError for a JSON array, broken JSON and broken INI"""
        cases = {"list.json": "[1, 2]", "broken.json": "{oops", "broken.ini": "no section header"}
        with tempfile.TemporaryDirectory() as tmp_dir:
            for name, text in cases.items():
                config_path = os.path.join(tmp_dir, name)
                with open(config_path, "w", encoding="utf-8") as f:
                    f.write(text)

                with self.subTest(name), self.assertRaises(ValueError):
                    load_config(config_path)

    def test_cli_fetch_requires_site_and_out(self) -> None:
        """Test that 'fetch' without --site and --out is rejected by the parser"""
        test_args = ["aquamonitor", "fetch", "--input", "test.json"]
        with patch("sys.argv", test_args), patch("sys.stderr", new_callable=io.StringIO):
            with self.assertRaises(SystemExit) as ctx:
                main()

        self.assertEqual(ctx.exception.code, 2)

    def test_cli_without_command_exits_with_code_1(self) -> None:
        """Test that running 'aquamonitor' without a command prints help and exits with 1"""
        with (
            patch("sys.argv", ["aquamonitor"]),
            patch("sys.stdout", new_callable=io.StringIO) as mock_stdout,
        ):
            with self.assertRaises(SystemExit) as ctx:
                main()

        self.assertEqual(ctx.exception.code, 1)
        self.assertIn("usage", mock_stdout.getvalue())

    def run_main(self, *args: str) -> str:
        """Run main() with the given arguments and return what it printed"""
        with (
            patch("sys.argv", ["aquamonitor", *args]),
            patch("sys.stdout", new_callable=io.StringIO) as out,
            patch("sys.stderr", new_callable=io.StringIO),
        ):
            main()
        return out.getvalue()

    def test_report_plot_saves_histogram(self) -> None:
        """Test that 'report --plot' saves a PNG histogram next to the table"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            image = os.path.join(tmp_dir, "hist.png")
            printed = self.run_main("report", "--input", str(SAMPLE), "--plot", image)

            self.assertIn("SUMMARY REPORT", printed)
            with open(image, "rb") as f:
                self.assertEqual(f.read(8), b"\x89PNG\r\n\x1a\n")

    def test_forecast_plot_saves_line_plot(self) -> None:
        """Test that 'forecast --plot' saves the observed + forecast PNG"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            image = os.path.join(tmp_dir, "forecast.png")
            printed = self.run_main("forecast", "--input", str(SAMPLE), "--plot", image)

            self.assertIn("[PLOT] Saved forecast plot", printed)
            self.assertGreater(os.path.getsize(image), 0)

    def test_forecast_prints_metrics_when_data_is_long_enough(self) -> None:
        """Test that the 48-point sample allows a 1-hour (12 points) evaluation"""
        printed = self.run_main("forecast", "--input", str(SAMPLE), "--horizon", "1")

        self.assertIn("Quality on the last 1.0 h held out (12 points)", printed)
        self.assertIn("RMSE", printed)

    def test_forecast_too_long_for_the_data_still_prints_forecast(self) -> None:
        """Test that 12 hours on a 4-hour sample prints the forecast and a note, not an error"""
        printed = self.run_main("forecast", "--input", str(SAMPLE), "--horizon", "12")

        self.assertIn("NAIVE FORECAST", printed)
        self.assertIn("Not enough data to evaluate", printed)

    def test_plot_to_missing_folder_exits_with_code_1(self) -> None:
        """Test that a plot path in a folder that does not exist gives an error, not a traceback"""
        image = os.path.join("no_such_folder", "x.png")
        with self.assertRaises(SystemExit) as ctx:
            self.run_main("report", "--input", str(SAMPLE), "--plot", image)

        self.assertEqual(ctx.exception.code, 1)


if __name__ == "__main__":
    unittest.main()
