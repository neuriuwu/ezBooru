import tempfile
import unittest
from pathlib import Path

from PySide6.QtCore import QSettings

from ezbooru.library import UserLibrary, filter_blacklisted
from ezbooru.models import Post, Tag


def make_post(
    post_id: int = 12,
    booru: str = "Danbooru",
    tags: tuple[Tag, ...] = (),
) -> Post:
    return Post(
        id=post_id,
        booru=booru,
        page_url=f"https://example.test/posts/{post_id}",
        file_url=f"https://example.test/{post_id}.jpg",
        preview_url=f"https://example.test/{post_id}-preview.jpg",
        tags=tags,
        rating="general",
        file_ext="jpg",
    )


class UserLibraryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        settings_path = Path(self.temporary_directory.name) / "settings.ini"
        self.settings = QSettings(str(settings_path), QSettings.Format.IniFormat)
        self.library = UserLibrary(self.settings)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_favorite_is_persisted_and_deduplicated_by_site_and_id(self) -> None:
        post = make_post(tags=(Tag("artist_tag", "artist"),))
        self.assertTrue(self.library.toggle_favorite(post))
        self.assertFalse(self.library.toggle_favorite(post))
        self.assertEqual(self.library.favorites, [])
        self.library.toggle_favorite(post)
        reloaded = UserLibrary(self.settings)
        self.assertTrue(reloaded.is_favorite(post))
        self.assertEqual(reloaded.favorites[0].tags[0].category, "artist")

    def test_saved_searches_persist_and_remove_by_index(self) -> None:
        self.assertTrue(self.library.save_search("Danbooru", "landscape"))
        self.assertFalse(self.library.save_search("Danbooru", " landscape "))
        self.assertTrue(self.library.save_search("Gelbooru", "portrait"))
        self.library.remove_search(0)
        self.assertEqual(
            self.library.saved_searches,
            [{"booru": "Gelbooru", "query": "portrait"}],
        )

    def test_blacklist_is_normalized_and_filters_posts(self) -> None:
        self.library.blacklisted_tags = ["  blue eyes ", "blue_eyes", "spoiler"]
        posts = [
            make_post(1, tags=(Tag("blue_eyes"),)),
            make_post(2, tags=(Tag("safe_tag"),)),
            make_post(3, tags=(Tag("SPOILER"),)),
        ]
        self.assertEqual(
            [post.id for post in filter_blacklisted(posts, self.library.blacklisted_tags)],
            [2],
        )
        self.assertEqual(self.library.blacklisted_tags, ["blue_eyes", "spoiler"])

    def test_download_directory_persists(self) -> None:
        directory = str(Path(self.temporary_directory.name) / "downloads")
        self.library.download_directory = directory
        self.assertEqual(UserLibrary(self.settings).download_directory, directory)


if __name__ == "__main__":
    unittest.main()
