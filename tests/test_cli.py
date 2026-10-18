import io
import json
import os
import tempfile
import unittest
from unittest.mock import patch

from aquamonitor.cli import load_config, main


class TestCLI(unittest.TestCase):
    """Unit tests for CLI interface and config loader"""

    def test_load_config_json(self) -> None:
        """Test loading configuration from a JSON file"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = os.path.join(tmp_dir, "config.json")
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump({"setting": "enabled"}, f)

            data = load_config(config_path)
            self.assertEqual(data, {"setting": "enabled"})

    def test_load_config_ini(self) -> None:
        """Test loading configuration from an INI file"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = os.path.join(tmp_dir, "config.ini")
            with open(config_path, "w", encoding="utf-8") as f:
                f.write("[section]\nkey = value\n")

            data = load_config(config_path)
            self.assertEqual(data, {"section": {"key": "value"}})

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

    def test_cli_fetch_command(self) -> None:
        """Test running 'aquamonitor fetch --input test.json'"""
        test_args = ["aquamonitor", "fetch", "--input", "test.json"]
        with patch("sys.argv", test_args), patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            main()
            captured = mock_stdout.getvalue()
            self.assertIn("[FETCH] Processing file: test.json", captured)

    def test_cli_report_command(self) -> None:
        """Test running 'aquamonitor report --input data.json'"""
        test_args = ["aquamonitor", "report", "--input", "data.json"]
        with patch("sys.argv", test_args), patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            main()
            captured = mock_stdout.getvalue()
            self.assertIn("[REPORT] Generating report from file: data.json", captured)


if __name__ == "__main__":
    unittest.main()