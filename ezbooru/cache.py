"""Small in-memory and persistent cache for remote image bytes."""

from __future__ import annotations

import asyncio
from collections import OrderedDict
from pathlib import Path

import httpx
from diskcache import Cache
from platformdirs import user_cache_dir


class ImageCache:
    def __init__(self, memory_items: int = 96) -> None:
        self._memory_items = memory_items
        self._memory: OrderedDict[str, bytes] = OrderedDict()
        self._disk = Cache(
            str(Path(user_cache_dir("ezBooru")) / "images"),
            size_limit=5 * 1024**3,
        )
        self._http = httpx.AsyncClient(
            timeout=httpx.Timeout(35.0, connect=10.0),
            follow_redirects=True,
            headers={"User-Agent": "ezBooru/0.1.0 (desktop client)"},
        )

    async def get(self, url: str) -> bytes:
        cached = self._memory.get(url)
        if cached is not None:
            self._memory.move_to_end(url)
            return cached
        cached = await asyncio.to_thread(self._disk.get, url)
        if isinstance(cached, bytes):
            self._remember(url, cached)
            return cached
        try:
            async with self._http.stream("GET", url) as response:
                response.raise_for_status()
                chunks = bytearray()
                async for chunk in response.aiter_bytes():
                    chunks.extend(chunk)
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(f"Image server returned HTTP {exc.response.status_code}.") from exc
        except httpx.TimeoutException as exc:
            raise RuntimeError("Image download timed out.") from exc
        except httpx.RequestError as exc:
            raise RuntimeError(f"Could not download image: {exc}") from exc
        image_bytes = bytes(chunks)
        await asyncio.to_thread(self._disk.set, url, image_bytes)
        self._remember(url, image_bytes)
        return image_bytes

    def _remember(self, url: str, image_bytes: bytes) -> None:
        self._memory[url] = image_bytes
        self._memory.move_to_end(url)
        while len(self._memory) > self._memory_items:
            self._memory.popitem(last=False)

    async def close(self) -> None:
        await self._http.aclose()
        await asyncio.to_thread(self._disk.close)
