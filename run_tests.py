"""Run every test of the project: python run_tests.py

Works without `pip install -e .`, because it puts src/ on the import path
itself. The exit code is 0 when all tests pass and 1 otherwise, so the
script can be used in automation.
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main() -> int:
    """Discover the tests in tests/ and run them; return the exit code."""
    sys.path.insert(0, str(ROOT / "src"))
    suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"), top_level_dir=str(ROOT))
    # stdout instead of the default stderr, so IDEs do not paint a passing run red.
    result = unittest.TextTestRunner(stream=sys.stdout, verbosity=1).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
