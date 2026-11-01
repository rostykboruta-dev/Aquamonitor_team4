import logging
import os
import tempfile
import unittest
from unittest.mock import patch

from aquamonitor.infra import log_call, setup_logging, timed

LOGGER = "aquamonitor"


class TestTimed(unittest.TestCase):

    def test_returns_result_and_logs_duration(self) -> None:
        @timed
        def add(a: int, b: int = 0) -> int:
            return a + b

        with self.assertLogs(LOGGER, level="INFO") as logs:
            self.assertEqual(add(2, b=3), 5)

        self.assertEqual(len(logs.records), 1)
        self.assertRegex(logs.output[0], r"add took \d+\.\d{4} s")

    def test_measures_real_time(self) -> None:
        """The logged duration is the difference of perf_counter readings."""

        @timed
        def work() -> None:
            pass

        with patch("aquamonitor.infra.time.perf_counter", side_effect=[10.0, 12.5]), \
                self.assertLogs(LOGGER, level="INFO") as logs:
            work()

        self.assertIn("work took 2.5000 s", logs.output[0])

    def test_failed_call_is_timed_and_exception_passes_through(self) -> None:
        @timed
        def broken() -> None:
            raise KeyError("boom")

        with self.assertLogs(LOGGER, level="INFO") as logs, self.assertRaises(KeyError):
            broken()

        self.assertIn("broken took", logs.output[0])

    def test_keeps_name_and_docstring(self) -> None:
        @timed
        def documented() -> None:
            """Docstring."""

        self.assertEqual(documented.__name__, "documented")
        self.assertEqual(documented.__doc__, "Docstring.")


class TestLogCall(unittest.TestCase):

    def test_logs_call_and_returns_result(self) -> None:
        @log_call
        def double(x: int) -> int:
            return 2 * x

        with self.assertLogs(LOGGER, level="INFO") as logs:
            self.assertEqual(double(4), 8)

        self.assertEqual(logs.output, [f"INFO:{LOGGER}:call double"])

    def test_error_is_logged_with_traceback_and_reraised(self) -> None:
        @log_call
        def divide(a: int, b: int) -> float:
            return a / b

        with self.assertLogs(LOGGER, level="INFO") as logs, \
                self.assertRaises(ZeroDivisionError):
            divide(1, 0)

        error = logs.records[-1]
        self.assertEqual(error.levelno, logging.ERROR)
        self.assertEqual(error.getMessage(), "divide failed")
        self.assertIs(error.exc_info[0], ZeroDivisionError)

    def test_keeps_name(self) -> None:
        @log_call
        def named() -> None:
            pass

        self.assertEqual(named.__name__, "named")


class TestDecoratorStack(unittest.TestCase):
    """cli.py uses @log_call over @timed; the order of records matters for reading the log."""

    def test_order_of_records_for_a_failing_command(self) -> None:
        @log_call
        @timed
        def command() -> None:
            raise ValueError("bad input")

        with self.assertLogs(LOGGER, level="INFO") as logs, self.assertRaises(ValueError):
            command()

        messages = [record.getMessage() for record in logs.records]
        self.assertEqual(messages[0], "call command")
        self.assertRegex(messages[1], r"^command took ")
        self.assertEqual(messages[2], "command failed")


class TestSetupLogging(unittest.TestCase):

    def setUp(self) -> None:
        root = logging.getLogger()
        self._saved = (root.handlers[:], root.level)
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "test.log")

    def tearDown(self) -> None:
        root = logging.getLogger()
        for handler in root.handlers:
            handler.close()
        root.handlers, level = self._saved[0], self._saved[1]
        root.setLevel(level)
        self.tmp.cleanup()

    def _read_log(self) -> str:
        for handler in logging.getLogger().handlers:
            handler.flush()
        with open(self.path, encoding="utf-8") as f:
            return f.read()

    def test_writes_info_and_errors_but_not_debug(self) -> None:
        setup_logging(self.path)
        logger = logging.getLogger(LOGGER)
        logger.debug("hidden detail")
        logger.info("рівень води 3.72 м")
        logger.error("sensor offline")

        text = self._read_log()
        self.assertNotIn("hidden detail", text)
        self.assertRegex(text, r"\d{4}-\d{2}-\d{2} [\d:,]+ INFO aquamonitor: рівень води 3.72 м")
        self.assertIn("ERROR aquamonitor: sensor offline", text)

    def test_decorated_failure_reaches_the_file(self) -> None:
        setup_logging(self.path)

        @log_call
        def explode() -> None:
            raise RuntimeError("disk full")

        with self.assertRaises(RuntimeError):
            explode()

        text = self._read_log()
        self.assertIn("explode failed", text)
        self.assertIn("RuntimeError: disk full", text)

    def test_repeated_setup_replaces_handler(self) -> None:
        """force=True: a second call switches the file instead of adding a handler."""
        other = os.path.join(self.tmp.name, "other.log")
        setup_logging(self.path)
        setup_logging(other)
        logging.getLogger(LOGGER).info("only in other")

        self.assertEqual(len(logging.getLogger().handlers), 1)
        self.assertNotIn("only in other", self._read_log())


if __name__ == "__main__":
    unittest.main()
