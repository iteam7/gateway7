"""Bounded, single-worker execution of the private management connection.

The connection and its ownership lock stay on one worker. Cancelling an HTTP
caller never abandons a database operation or closes a connection still in use.
"""

import asyncio
import functools
from contextvars import copy_context
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any, TypeVar

from gateway7.errors import GatewayError

Result = TypeVar("Result")


class DBExecutor:
    def __init__(self, *, capacity: int = 64) -> None:
        if type(capacity) is not int or not 1 <= capacity <= 1024:
            raise ValueError("Invalid management executor capacity")
        self.capacity = capacity
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="gateway7-control")
        self._pending: set[asyncio.Future[Any]] = set()
        self._closed = False

    @property
    def pending(self) -> int:
        return len(self._pending)

    async def call(self, operation: Callable[..., Result], *args: Any, **kwargs: Any) -> Result:
        if self._closed:
            raise GatewayError("unavailable")
        if len(self._pending) >= self.capacity:
            raise GatewayError("overloaded")
        context = copy_context()
        submitted = self._executor.submit(
            context.run, functools.partial(operation, *args, **kwargs)
        )
        future = asyncio.wrap_future(submitted)
        self._pending.add(future)
        future.add_done_callback(self._pending.discard)
        cancellation = None
        try:
            await asyncio.wait_for(asyncio.shield(future), timeout=1.0)
        except TimeoutError:
            # Only queued work can be removed. A running transaction must finish;
            # backend statement/lock timeouts bound that operation independently.
            if submitted.cancel():
                raise GatewayError("overloaded") from None
        except asyncio.CancelledError as error:
            if submitted.cancel():
                raise
            cancellation = error
        except Exception:
            return future.result()
        while not future.done():
            try:
                await asyncio.shield(future)
            except asyncio.CancelledError as error:
                cancellation = cancellation or error
            except Exception:
                if not future.done():
                    raise
                break
        try:
            return future.result()
        finally:
            if cancellation is not None:
                raise cancellation

    async def drain(self) -> None:
        cancellation = None
        while self._pending:
            try:
                await asyncio.shield(asyncio.gather(*self._pending, return_exceptions=True))
            except asyncio.CancelledError as error:
                cancellation = cancellation or error
        if cancellation is not None:
            raise cancellation

    async def close(self) -> None:
        try:
            await self.drain()
        finally:
            self._closed = True
            # drain completed every operation before joining the now-idle worker.
            await asyncio.to_thread(self._executor.shutdown, wait=True)
