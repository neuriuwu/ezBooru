"""Async JSON API clients for common booru engines."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import urljoin, urlsplit

import httpx

from ezbooru.models import Comment, Post, Tag, TagCategory

_DANBOORU_TAG_CATEGORIES: dict[int, TagCategory] = {
    0: "general",
    1: "artist",
    3: "copyright",
    4: "character",
    5: "meta",
}
_RATINGS = {
    "g": "general",
    "s": "sensitive",
    "q": "questionable",
    "e": "explicit",
}


class BooruAPIError(Exception):
    """A network, HTTP, or response-format error from a booru endpoint."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class BooruClient(ABC):
    """Base class for booru APIs that return JSON post objects."""

    name: str
    default_url: str

    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = (base_url or self.default_url).rstrip("/") + "/"
        self._http = httpx.AsyncClient(
            timeout=httpx.Timeout(25.0, connect=10.0),
            follow_redirects=True,
            headers={"User-Agent": "ezBooru/0.1.0 (desktop client)"},
        )

    async def close(self) -> None:
        await self._http.aclose()

    async def _get_json(
        self, path: str, params: Mapping[str, str | int] | None = None
    ) -> Any:
        try:
            response = await self._http.get(urljoin(self.base_url, path), params=params)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            message = (
                f"{self.name} rate limited the request (HTTP 429). Try again shortly."
                if status == 429
                else f"{self.name} returned HTTP {status}."
            )
            raise BooruAPIError(message, status_code=status) from exc
        except httpx.TimeoutException as exc:
            raise BooruAPIError(f"Request to {self.name} timed out.") from exc
        except httpx.RequestError as exc:
            raise BooruAPIError(f"Could not connect to {self.name}: {exc}") from exc
        except ValueError as exc:
            raise BooruAPIError(f"{self.name} returned invalid JSON.") from exc

    async def search(self, tags: str, page: int = 1, limit: int = 40) -> list[Post]:
        if page < 1:
            raise ValueError("page must be at least one.")
        if limit < 1:
            raise ValueError("limit must be at least one.")
        data = await self._get_json(self.posts_path, self.search_params(tags, page, limit))
        if isinstance(data, Mapping):
            data = data.get("posts", data.get("post", data.get("data")))
        if isinstance(data, Mapping) and "id" in data:
            data = [data]
        if not isinstance(data, Sequence) or isinstance(data, (str, bytes)):
            raise BooruAPIError(f"{self.name} returned an unexpected post-list format.")
        return [self.normalize_post(item) for item in data if isinstance(item, Mapping)]

    async def get_comments(self, post_id: int) -> list[Comment]:
        data = await self._get_json("comments.json", {"post_id": post_id})
        if not isinstance(data, list):
            raise BooruAPIError(f"{self.name} returned an unexpected comments format.")
        comments: list[Comment] = []
        for item in data:
            if not isinstance(item, Mapping):
                continue
            comments.append(
                Comment(
                    id=_as_int(item.get("id")),
                    post_id=_as_int(item.get("post_id"), post_id),
                    body=str(item.get("body", "")),
                    author=str(item.get("creator_name", item.get("creator", ""))),
                    created_at=str(item.get("created_at", "")),
                )
            )
        return comments

    @property
    @abstractmethod
    def posts_path(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def search_params(self, tags: str, page: int, limit: int) -> dict[str, str | int]:
        raise NotImplementedError

    @abstractmethod
    def normalize_post(self, item: Mapping[str, Any]) -> Post:
        raise NotImplementedError


class DanbooruClient(BooruClient):
    name = "Danbooru"
    default_url = "https://danbooru.donmai.us/"

    @property
    def posts_path(self) -> str:
        return "posts.json"

    def search_params(self, tags: str, page: int, limit: int) -> dict[str, str | int]:
        return {"tags": tags, "page": page, "limit": min(limit, 200)}

    def normalize_post(self, item: Mapping[str, Any]) -> Post:
        tag_objects = item.get("tags", [])
        tags: list[Tag] = []
        if isinstance(tag_objects, list):
            for value in tag_objects:
                if isinstance(value, Mapping):
                    category = _DANBOORU_TAG_CATEGORIES.get(
                        _as_int(value.get("category")), "general"
                    )
                    name = str(value.get("name", "")).replace("_", " ")
                    if name:
                        tags.append(Tag(name, category))
                elif isinstance(value, str):
                    tags.append(Tag(value.replace("_", " ")))
        return _make_post(item, self.name, self.base_url, tags)


class GelbooruClient(BooruClient):
    name = "Gelbooru"
    default_url = "https://gelbooru.com/"

    @property
    def posts_path(self) -> str:
        return "index.php"

    def search_params(self, tags: str, page: int, limit: int) -> dict[str, str | int]:
        return {
            "page": "dapi",
            "s": "post",
            "q": "index",
            "json": 1,
            "tags": tags,
            "pid": max(page - 1, 0),
            "limit": min(limit, 100),
        }

    def normalize_post(self, item: Mapping[str, Any]) -> Post:
        return _make_post(
            item,
            self.name,
            self.base_url,
            _plain_tags(item.get("tags")),
            f"index.php?page=post&s=view&id={_as_int(item.get('id'))}",
        )


class SafebooruClient(GelbooruClient):
    name = "Safebooru"
    default_url = "https://safebooru.org/"


class MoebooruClient(BooruClient):
    name = "Moebooru"
    default_url = "https://yande.re/"

    @property
    def posts_path(self) -> str:
        return "post.json"

    def search_params(self, tags: str, page: int, limit: int) -> dict[str, str | int]:
        return {"tags": tags, "page": page, "limit": min(limit, 100)}

    def normalize_post(self, item: Mapping[str, Any]) -> Post:
        return _make_post(
            item,
            self.name,
            self.base_url,
            _plain_tags(item.get("tags")),
            f"post/show/{_as_int(item.get('id'))}",
        )


def _plain_tags(value: Any) -> list[Tag]:
    if isinstance(value, str):
        return [Tag(name.replace("_", " ")) for name in value.split() if name]
    if isinstance(value, list):
        return [Tag(str(name).replace("_", " ")) for name in value if name]
    return []


def _make_post(
    item: Mapping[str, Any],
    booru: str,
    base_url: str,
    tags: list[Tag],
    default_page_path: str | None = None,
) -> Post:
    post_id = _as_int(item.get("id"))
    file_url = str(item.get("file_url") or "")
    if not file_url:
        raise BooruAPIError(f"{booru} returned post #{post_id} without a file URL.")
    preview_url = str(
        item.get("preview_file_url")
        or item.get("preview_url")
        or item.get("sample_url")
        or file_url
    )
    file_url = _absolute_url(file_url, base_url)
    preview_url = _absolute_url(preview_url, base_url)
    page_path = default_page_path or f"posts/{post_id}"
    page_url = str(item.get("page_url") or urljoin(base_url, page_path))
    file_ext = item.get("file_ext") or PurePosixPath(urlsplit(file_url).path).suffix.lstrip(
        "."
    )
    return Post(
        id=post_id,
        booru=booru,
        page_url=page_url,
        file_url=file_url,
        preview_url=preview_url,
        tags=tuple(tags),
        rating=_RATINGS.get(str(item.get("rating", "")).lower(), "unknown"),
        file_ext=str(file_ext).lower(),
        width=_optional_int(item.get("image_width", item.get("width"))),
        height=_optional_int(item.get("image_height", item.get("height"))),
        score=_as_int(item.get("score")),
    )


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _optional_int(value: Any) -> int | None:
    return None if value is None else _as_int(value)


def _absolute_url(value: str, base_url: str) -> str:
    if value.startswith("//"):
        return f"https:{value}"
    return urljoin(base_url, value)
