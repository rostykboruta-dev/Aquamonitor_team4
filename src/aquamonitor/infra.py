import functools
import logging
import time
from collections.abc import Callable
from typing import Any

logger = logging.getLogger("aquamonitor")


def setup_logging(log_filename: str = "aquamonitor.log") -> None:
    """Configure logging to write INFO and higher messages to a file.

    Args:
        log_filename: Path of the log file.
    """
    logging.basicConfig(
        filename=log_filename,
        encoding="utf-8",
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        force=True,
    )


def timed(func: Callable[..., Any]) -> Callable[..., Any]:
    """Log the execution time of the decorated function."""

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        start = time.perf_counter()
        try:
            return func(*args, **kwargs)
        finally:
            logger.info("%s took %.4f s", func.__name__, time.perf_counter() - start)

    return wrapper


def log_call(func: Callable[..., Any]) -> Callable[..., Any]:
    """Log each call of the decorated function and any exception it raises."""

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        logger.info("call %s", func.__name__)
        try:
            return func(*args, **kwargs)
        except Exception:
            logger.exception("%s failed", func.__name__)
            raise

    return wrapper