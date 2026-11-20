"""Own provider response cleanup to completion without losing cancellation."""

import asyncio
from collections.abc import AsyncIterator

import httpx


class OwnedCloseStream(httpx.AsyncByteStream):
    """Keep HTTPX decoding and give EOF/context exit one shared close task."""

    def __init__(self, stream: httpx.AsyncByteStream) -> None:
        self._stream = stream
        self._close_task: asyncio.Task[None] | None = None

    async def __aiter__(self) -> AsyncIterator[bytes]:
        async for chunk in self._stream:
            yield chunk

    async def aclose(self) -> None:
        if self._close_task is None:
            self._close_task = asyncio.create_task(self._stream.aclose())
        cancelled: asyncio.CancelledError | None = None
        while not self._close_task.done():
            try:
                await asyncio.shield(self._close_task)
            except asyncio.CancelledError as error:
                if self._close_task.cancelled():
                    break
                if cancelled is None:
                    cancelled = error
            except BaseException:
                break
        try:
            self._close_task.result()
        finally:
            if cancelled is not None:
                raise cancelled from None
