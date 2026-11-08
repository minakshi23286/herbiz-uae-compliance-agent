"""Injectable clock. All times are explicit and use Asia/Dubai (UTC+04:00, no daylight saving).

HerBiz / Compliance Operations Agent. Standard library only.
"""
from __future__ import annotations

import datetime as dt

try:
    from zoneinfo import ZoneInfo
    DUBAI = ZoneInfo("Asia/Dubai")
except Exception:  # pragma: no cover - tzdata missing; Dubai has a fixed offset
    DUBAI = dt.timezone(dt.timedelta(hours=4), "Asia/Dubai")


class SystemClock:
    def now(self) -> dt.datetime:
        return dt.datetime.now(DUBAI).replace(microsecond=0)

    def today(self) -> dt.date:
        return self.now().date()


class FixedClock(SystemClock):
    """Test and demo clock. `advance` moves time forward so retries and history keep an order."""

    def __init__(self, iso: str):
        t = dt.datetime.fromisoformat(iso)
        self._t = t if t.tzinfo else t.replace(tzinfo=DUBAI)

    def now(self) -> dt.datetime:
        return self._t

    def advance(self, **kw) -> None:
        self._t = self._t + dt.timedelta(**kw)


def iso(t: dt.datetime) -> str:
    return t.astimezone(DUBAI).isoformat()
