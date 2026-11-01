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
        with patch("sys.argv", ["aquamonitor"]), patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            with self.assertRaises(SystemExit) as ctx:
                main()

        self.assertEqual(ctx.exception.code, 1)
        self.assertIn("usage", mock_stdout.getvalue())


if __name__ == "__main__":
    unittest.main()