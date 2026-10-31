"""Safe filename rendering and bounded-parallel post downloads."""

from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Callable, Iterable

import httpx

from ezbooru.models import Post

_INVALID_PATH_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}


def render_filename(post: Post, template: str) -> Path:
    artist = next((tag.name for tag in post.tags if tag.category == "artist"), "unknown_artist")
    character = next(
        (tag.name for tag in post.tags if tag.category == "character"), "unknown_character"
    )
    values = {
        "id": str(post.id),
        "artist": artist,
        "character": character,
        "rating": post.rating,
        "ext": post.file_ext.lstrip(".") or "img",
        "booru": post.booru,
    }

    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in values:
            raise ValueError(f"Unsupported filename template field: {{{key}}}")
        return _safe_segment(values[key])

    rendered = re.sub(r"\{([a-zA-Z_]+)\}", replace, template)
    if "{" in rendered or "}" in rendered:
        raise ValueError("Filename template contains an invalid field.")
    parts = Path(rendered).parts
    if not parts or any(part in {"", ".", ".."} for part in parts):
        raise ValueError("Filename template must resolve to a relative file path.")
    safe_parts = [_safe_segment(part) for part in parts]
    return Path(*safe_parts)


def _safe_segment(value: str) -> str:
    safe = _INVALID_PATH_CHARS.sub("_", value).strip(" .")
    if not safe:
        raise ValueError("Filename template produced an empty path segment.")
    if safe.split(".", 1)[0].upper() in _WINDOWS_RESERVED_NAMES:
        safe += "_"
    return safe


class DownloadManager:
    def __init__(self, parallel_downloads: int = 4) -> None:
        if parallel_downloads < 1:
            raise ValueError("parallel_downloads must be at least one.")
        self._parallel_downloads = parallel_downloads
        self._http = httpx.AsyncClient(
            timeout=httpx.Timeout(60.0, connect=10.0),
            follow_redirects=True,
            headers={"User-Agent": "ezBooru/0.1.0 (desktop client)"},
        )

    async def download_post(self, post: Post, destination: Path) -> Path:
        partial = destination.with_name(destination.name + ".part")
        try:
            async with self._http.stream("GET", post.file_url) as response:
                response.raise_for_status()
                destination.parent.mkdir(parents=True, exist_ok=True)
                with partial.open("wb") as output:
                    async for chunk in response.aiter_bytes(256 * 1024):
                        await asyncio.to_thread(output.write, chunk)
            await asyncio.to_thread(partial.replace, destination)
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(f"Download failed with HTTP {exc.response.status_code}.") from exc
        except httpx.TimeoutException as exc:
            raise RuntimeError("Post download timed out.") from exc
        except httpx.RequestError as exc:
            raise RuntimeError(f"Could not download post: {exc}") from exc
        finally:
            partial.unlink(missing_ok=True)
        return destination

    async def download_many(
        self,
        posts: Iterable[Post],
        output_dir: Path,
        template: str = "{id}.{ext}",
        on_downloaded: Callable[[Path], None] | None = None,
    ) -> list[Path]:
        semaphore = asyncio.Semaphore(self._parallel_downloads)
        post_destinations: list[tuple[Post, Path]] = []
        seen_destinations: set[Path] = set()
        for post in posts:
            destination = output_dir / render_filename(post, template)
            if destination in seen_destinations:
                raise ValueError(
                    f"Filename template maps multiple posts to {destination.name!r}."
                )
            seen_destinations.add(destination)
            post_destinations.append((post, destination))

        async def download_one(post: Post, destination: Path) -> Path:
            async with semaphore:
                path = await self.download_post(post, destination)
                if on_downloaded is not None:
                    on_downloaded(path)
                return path

        tasks = [
            asyncio.create_task(download_one(post, destination))
            for post, destination in post_destinations
        ]
        try:
            return await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            await self._cancel_downloads(tasks)
            raise
        except Exception:
            await self._cancel_downloads(tasks)
            raise

    @staticmethod
    async def _cancel_downloads(tasks: list[asyncio.Task[Path]]) -> None:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    async def close(self) -> None:
        await self._http.aclose()
