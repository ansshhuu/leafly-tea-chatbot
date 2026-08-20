from datetime import datetime, timezone

from app.core.config import settings


class RateLimiter:
    def __init__(self, rpm_limit: int, rpd_limit: int) -> None:
        self.rpm_limit = rpm_limit
        self.rpd_limit = rpd_limit
        self._minute_key: str | None = None
        self._minute_count = 0
        self._day_key: str | None = None
        self._day_count = 0

    def _refresh(self, now: datetime) -> None:
        minute_key = now.strftime("%Y%m%d%H%M")
        day_key = now.strftime("%Y%m%d")
        if minute_key != self._minute_key:
            self._minute_key = minute_key
            self._minute_count = 0
        if day_key != self._day_key:
            self._day_key = day_key
            self._day_count = 0

    def is_within_limits(self) -> bool:
        self._refresh(datetime.now(timezone.utc))
        return self._minute_count < self.rpm_limit and self._day_count < self.rpd_limit

    def record_call(self) -> None:
        self._refresh(datetime.now(timezone.utc))
        self._minute_count += 1
        self._day_count += 1


rate_limiter = RateLimiter(rpm_limit=settings.gemini_rpm_limit, rpd_limit=settings.gemini_rpd_limit)
