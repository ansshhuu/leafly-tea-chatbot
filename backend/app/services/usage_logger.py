import logging
from pathlib import Path

LOG_DIR = Path(__file__).resolve().parents[2] / "logs"
LOG_DIR.mkdir(exist_ok=True)

_logger = logging.getLogger("gemini_usage")
_logger.setLevel(logging.INFO)
if not _logger.handlers:
    handler = logging.FileHandler(LOG_DIR / "gemini_usage.log", encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
    _logger.addHandler(handler)
    _logger.propagate = False


def log_call(session_id: str, tokens_used: int | None, cached: bool, fallback: bool) -> None:
    _logger.info(
        "session=%s cached=%s fallback=%s tokens=%s",
        session_id,
        cached,
        fallback,
        tokens_used if tokens_used is not None else "unknown",
    )
