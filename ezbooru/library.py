"""Persistent user library for favorites, saved searches, and excluded tags."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from PySide6.QtCore import QSettings

from ezbooru.models import Post, Tag, TagCategory


class UserLibrary:
    def __init__(self, settings: QSettings) -> None:
        self._settings = settings

    @property
    def favorites(self) -> list[Post]:
        values = self._read_json("favorites", [])
        if not isinstance(values, list):
            return []
        posts: list[Post] = []
        for value in values:
            if isinstance(value, Mapping):
                try:
                    posts.append(_post_from_dict(value))
                except (KeyError, TypeError, ValueError):
                    continue
        return posts

    def is_favorite(self, post: Post) -> bool:
        return any(_post_key(saved) == _post_key(post) for saved in self.favorites)

    def toggle_favorite(self, post: Post) -> bool:
        favorites = self.favorites
        key = _post_key(post)
        existing_index = next(
            (index for index, saved in enumerate(favorites) if _post_key(saved) == key),
            None,
        )
        if existing_index is not None:
            favorites.pop(existing_index)
            self._write_json("favorites", [_post_to_dict(item) for item in favorites])
            return False
        favorites.append(post)
        self._write_json("favorites", [_post_to_dict(item) for item in favorites])
        return True

    @property
    def saved_searches(self) -> list[dict[str, str]]:
        values = self._read_json("saved_searches", [])
        if not isinstance(values, list):
            return []
        return [
            {"booru": str(value["booru"]), "query": str(value["query"])}
            for value in values
            if isinstance(value, Mapping) and "booru" in value and "query" in value
        ]

    def save_search(self, booru: str, query: str) -> bool:
        normalized_query = query.strip()
        if not normalized_query:
            return False
        searches = self.saved_searches
        entry = {"booru": booru, "query": normalized_query}
        if entry in searches:
            return False
        searches.append(entry)
        self._write_json("saved_searches", searches)
        return True

    def remove_search(self, index: int) -> None:
        searches = self.saved_searches
        if 0 <= index < len(searches):
            searches.pop(index)
            self._write_json("saved_searches", searches)

    @property
    def blacklisted_tags(self) -> list[str]:
        value = str(self._settings.value("blacklisted_tags", ""))
        return normalize_tags(value.replace(",", " ").split())

    @blacklisted_tags.setter
    def blacklisted_tags(self, tags: list[str]) -> None:
        self._settings.setValue("blacklisted_tags", " ".join(normalize_tags(tags)))

    @property
    def download_directory(self) -> str:
        return str(self._settings.value("download_directory", ""))

    @download_directory.setter
    def download_directory(self, directory: str) -> None:
        self._settings.setValue("download_directory", directory)

    def _read_json(self, key: str, default: Any) -> Any:
        raw = self._settings.value(key, "")
        if not raw:
            return default
        try:
            return json.loads(str(raw))
        except json.JSONDecodeError:
            return default

    def _write_json(self, key: str, value: Any) -> None:
        self._settings.setValue(key, json.dumps(value, ensure_ascii=False))


def normalize_tags(tags: list[str]) -> list[str]:
    unique: dict[str, str] = {}
    for tag in tags:
        normalized = tag.strip().replace(" ", "_")
        if normalized:
            unique.setdefault(normalized.casefold(), normalized)
    return list(unique.values())


def filter_blacklisted(posts: list[Post], blacklist: list[str]) -> list[Post]:
    excluded = {tag.casefold().replace(" ", "_") for tag in blacklist}
    if not excluded:
        return posts
    return [
        post
        for post in posts
        if not any(tag.name.casefold().replace(" ", "_") in excluded for tag in post.tags)
    ]


def _post_key(post: Post) -> tuple[str, int]:
    return post.booru.casefold(), post.id


def _post_to_dict(post: Post) -> dict[str, Any]:
    return {
        "id": post.id,
        "booru": post.booru,
        "page_url": post.page_url,
        "file_url": post.file_url,
        "preview_url": post.preview_url,
        "tags": [{"name": tag.name, "category": tag.category} for tag in post.tags],
        "rating": post.rating,
        "file_ext": post.file_ext,
        "width": post.width,
        "height": post.height,
        "score": post.score,
    }


def _post_from_dict(value: Mapping[str, Any]) -> Post:
    raw_tags = value.get("tags", [])
    tags = tuple(
        Tag(str(item["name"]), _tag_category(item.get("category")))
        for item in raw_tags
        if isinstance(item, Mapping) and "name" in item
    )
    return Post(
        id=int(value["id"]),
        booru=str(value["booru"]),
        page_url=str(value["page_url"]),
        file_url=str(value["file_url"]),
        preview_url=str(value.get("preview_url", value["file_url"])),
        tags=tags,
        rating=str(value.get("rating", "unknown")),
        file_ext=str(value.get("file_ext", "")),
        width=_optional_int(value.get("width")),
        height=_optional_int(value.get("height")),
        score=int(value.get("score", 0)),
    )


def _tag_category(value: Any) -> TagCategory:
    categories: set[TagCategory] = {
        "artist",
        "character",
        "copyright",
        "general",
        "meta",
    }
    category = str(value)
    return category if category in categories else "general"


def _optional_int(value: Any) -> int | None:
    return None if value is None else int(value)
