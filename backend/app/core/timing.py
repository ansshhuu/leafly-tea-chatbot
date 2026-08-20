import logging
import time
from contextlib import asynccontextmanager

_logger = logging.getLogger("timing")


@asynccontextmanager
async def timed(label: str):
    start = time.perf_counter()
    try:
        yield
    finally:
        elapsed_ms = (time.perf_counter() - start) * 1000
        _logger.info("%s took %.1fms", label, elapsed_ms)
