import asyncio
from datetime import UTC, datetime, timedelta
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime: ...

    async def sleep(self, seconds: float) -> None: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)

    async def sleep(self, seconds: float) -> None:
        await asyncio.sleep(seconds)


class FakeClock:
    def __init__(self, current: datetime):
        self._current = current

    def now(self) -> datetime:
        return self._current

    def advance(self, *, seconds: float) -> None:
        self._current += timedelta(seconds=seconds)

    async def sleep(self, seconds: float) -> None:
        self.advance(seconds=seconds)
