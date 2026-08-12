import asyncio
from collections.abc import Awaitable, Callable
from contextlib import suppress


class WorkerUnavailableError(RuntimeError):
    pass


class TaskWorker:
    def __init__(
        self,
        execute: Callable[[str], Awaitable[None]],
        recover_startup: Callable[[], Awaitable[list[str]]] | None = None,
        converge_cancelled: Callable[[str], Awaitable[None]] | None = None,
        *,
        max_concurrency: int = 1,
    ):
        if max_concurrency < 1:
            raise ValueError("max_concurrency_must_be_positive")
        self.execute = execute
        self.recover_startup = recover_startup
        self.converge_cancelled = converge_cancelled
        self.max_concurrency = max_concurrency
        self.queue: asyncio.Queue[str | None] = asyncio.Queue()
        self._loop_task: asyncio.Task[None] | None = None
        self._stopping = False

    @property
    def is_running(self) -> bool:
        return (
            self._loop_task is not None
            and not self._loop_task.done()
            and not self._stopping
        )

    async def start(self) -> None:
        if self._loop_task is not None:
            return
        recovered = (
            await self.recover_startup()
            if self.recover_startup is not None
            else []
        )
        self._loop_task = asyncio.create_task(self._run())
        for task_id in recovered:
            await self.queue.put(task_id)

    async def stop(self) -> None:
        loop_task = self._loop_task
        if loop_task is None:
            return
        if not loop_task.done() and not self._stopping:
            self._stopping = True
            loop_task.cancel()
        with suppress(asyncio.CancelledError, Exception):
            await loop_task

    async def enqueue(self, task_id: str) -> None:
        self._ensure_available()
        await self.queue.put(task_id)

    async def wait_until_idle(self) -> None:
        loop_task = self._ensure_available()
        join_task = asyncio.create_task(self.queue.join())
        done, _pending = await asyncio.wait(
            {join_task, loop_task},
            return_when=asyncio.FIRST_COMPLETED,
        )
        if loop_task in done:
            join_task.cancel()
            with suppress(asyncio.CancelledError):
                await join_task
            raise WorkerUnavailableError("task worker is not running")
        await join_task

    async def _run(self) -> None:
        consumers = [
            asyncio.create_task(self._consume())
            for _index in range(self.max_concurrency)
        ]
        try:
            await asyncio.gather(*consumers)
        finally:
            for consumer in consumers:
                consumer.cancel()
            for consumer in consumers:
                with suppress(asyncio.CancelledError, Exception):
                    await consumer

    async def _consume(self) -> None:
        while True:
            task_id = await self.queue.get()
            try:
                if task_id is None:
                    return
                try:
                    await self.execute(task_id)
                except asyncio.CancelledError:
                    if self.converge_cancelled is not None:
                        await self.converge_cancelled(task_id)
                    raise
                except Exception:
                    if self.converge_cancelled is not None:
                        await self.converge_cancelled(task_id)
                    continue
            finally:
                self.queue.task_done()

    def _ensure_available(self) -> asyncio.Task[None]:
        if self._loop_task is None or self._loop_task.done() or self._stopping:
            raise WorkerUnavailableError("task worker is not running")
        return self._loop_task
