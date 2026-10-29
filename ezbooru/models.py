"""Normalized data models used by the API and user-interface layers."""

from dataclasses import dataclass, field
from typing import Literal

TagCategory = Literal["artist", "character", "copyright", "general", "meta"]


@dataclass(frozen=True, slots=True)
class Tag:
    name: str
    category: TagCategory = "general"


@dataclass(frozen=True, slots=True)
class Comment:
    id: int
    post_id: int
    body: str
    author: str = ""
    created_at: str = ""


@dataclass(frozen=True, slots=True)
class Post:
    id: int
    booru: str
    page_url: str
    file_url: str
    preview_url: str
    tags: tuple[Tag, ...] = ()
    rating: str = "unknown"
    file_ext: str = ""
    width: int | None = None
    height: int | None = None
    score: int = 0
    comments: tuple[Comment, ...] = field(default_factory=tuple)

    @property
    def media_type(self) -> str:
        extension = self.file_ext.lower().lstrip(".")
        if extension in {"webm", "mp4", "mov"}:
            return "video"
        if extension == "gif":
            return "animated"
        return "image"

    @property
    def tags_by_category(self) -> dict[str, tuple[Tag, ...]]:
        categories = ("artist", "character", "copyright", "general", "meta")
        return {
            category: tuple(tag for tag in self.tags if tag.category == category)
            for category in categories
        }
