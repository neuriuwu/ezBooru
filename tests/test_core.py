import asyncio
from concurrent.futures import ThreadPoolExecutor
import tempfile
import unittest
from pathlib import Path

import httpx

from ezbooru.api_client import (
    DanbooruClient,
    GelbooruClient,
    KonachanClient,
    MoebooruClient,
    SafebooruClient,
    build_search_query,
)
from ezbooru.downloader import DownloadManager, render_filename
from ezbooru.models import Post


class APIClientTests(unittest.TestCase):
    def test_danbooru_post_normalization(self) -> None:
        client = DanbooruClient()
        post = client.normalize_post(
            {
                "id": 42,
                "file_url": "https://cdn.example/image.webp?token=abc",
                "preview_file_url": "https://cdn.example/preview.jpg",
                "rating": "g",
                "tags": [
                    {"name": "sample_artist", "category": 1},
                    {"name": "sample_character", "category": 4},
                ],
            }
        )
        self.assertEqual(post.page_url, "https://danbooru.donmai.us/posts/42")
        self.assertEqual(post.file_ext, "webp")
        self.assertEqual(post.rating, "general")
        self.assertEqual(post.tags[0].category, "artist")
        self.assertEqual(post.tags[1].category, "character")
        asyncio.run(client.close())

    def test_gelbooru_pagination_and_page_url(self) -> None:
        client = GelbooruClient()
        self.assertEqual(client.search_params("cat", 3, 500)["pid"], 2)
        post = client.normalize_post(
            {"id": 9, "file_url": "https://cdn.example/9.png", "tags": "cat blue_eyes"}
        )
        self.assertEqual(
            post.page_url,
            "https://gelbooru.com/index.php?page=post&s=view&id=9",
        )
        self.assertEqual([tag.name for tag in post.tags], ["cat", "blue eyes"])
        asyncio.run(client.close())

    def test_safebooru_host(self) -> None:
        client = SafebooruClient()
        self.assertEqual(client.base_url, "https://safebooru.org/")
        asyncio.run(client.close())

    def test_moebooru_host_and_page_url(self) -> None:
        client = MoebooruClient()
        post = client.normalize_post(
            {"id": 17, "file_url": "https://cdn.example/17.gif", "tags": "girl"}
        )
        self.assertEqual(client.base_url, "https://yande.re/")
        self.assertEqual(post.page_url, "https://yande.re/post/show/17")
        self.assertEqual(post.media_type, "animated")
        asyncio.run(client.close())

    def test_konachan_host_and_page_url(self) -> None:
        client = KonachanClient()
        post = client.normalize_post(
            {"id": 21, "file_url": "https://cdn.example/21.png", "tags": "safe_tag"}
        )
        self.assertEqual(client.base_url, "https://konachan.net/")
        self.assertEqual(post.booru, "Konachan (Safe)")
        self.assertEqual(
            post.page_url, "https://konachan.net/post/show/21"
        )
        self.assertEqual(client.posts_path, "post.json")
        asyncio.run(client.close())

    def test_protocol_relative_media_urls_are_normalized(self) -> None:
        client = DanbooruClient()
        post = client.normalize_post(
            {
                "id": 18,
                "file_url": "//cdn.example/18.png",
                "preview_file_url": "//cdn.example/18-preview.jpg",
            }
        )
        self.assertEqual(post.file_url, "https://cdn.example/18.png")
        self.assertEqual(post.preview_url, "https://cdn.example/18-preview.jpg")
        asyncio.run(client.close())

    def test_missing_media_url_is_reported(self) -> None:
        from ezbooru.api_client import BooruAPIError

        with self.assertRaisesRegex(BooruAPIError, "without a file URL"):
            DanbooruClient().normalize_post({"id": 19})


class DownloadTemplateTests(unittest.TestCase):
    def test_nested_template_uses_normalized_tags(self) -> None:
        post = Post(
            id=3,
            booru="Danbooru",
            page_url="https://example.test/posts/3",
            file_url="https://example.test/3.jpg",
            preview_url="https://example.test/3.jpg",
            file_ext="jpg",
        )
        path = render_filename(post, "{artist}/{character}_{id}.{ext}")
        self.assertEqual(
            path,
            Path("unknown_artist") / "unknown_character_3.jpg",
        )

    def test_unknown_fields_and_path_traversal_are_rejected(self) -> None:
        post = Post(
            id=4,
            booru="Danbooru",
            page_url="https://example.test/posts/4",
            file_url="https://example.test/4.jpg",
            preview_url="https://example.test/4.jpg",
            file_ext="jpg",
        )
        with self.assertRaises(ValueError):
            render_filename(post, "{unknown}.{ext}")
        with self.assertRaises(ValueError):
            render_filename(post, "../{id}.{ext}")


class SearchQueryTests(unittest.TestCase):
    def test_rating_filter_replaces_existing_rating_tags(self) -> None:
        self.assertEqual(build_search_query("cat rating:explicit blue_eyes"), "cat blue_eyes")
        self.assertEqual(build_search_query("cat", "safe"), "cat rating:safe")
        self.assertEqual(
            build_search_query("cat rating:safe", "questionable"),
            "cat rating:questionable",
        )
        self.assertEqual(build_search_query("rating:explicit", "all"), "")

    def test_unknown_rating_filter_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            build_search_query("cat", "unknown")


class OrientationTests(unittest.TestCase):
    def test_orientation_uses_image_dimensions_and_handles_missing_sizes(self) -> None:
        post = Post(
            id=5,
            booru="Danbooru",
            page_url="https://example.test/posts/5",
            file_url="https://example.test/5.jpg",
            preview_url="https://example.test/5.jpg",
            width=1600,
            height=900,
        )
        self.assertEqual(post.orientation, "landscape")
        self.assertEqual(
            Post(
                id=8,
                booru="Danbooru",
                page_url="https://example.test/posts/8",
                file_url="https://example.test/8.jpg",
                preview_url="https://example.test/8.jpg",
                width=1000,
                height=1000,
            ).orientation,
            "square",
        )
        self.assertEqual(
            Post(
                id=6,
                booru="Danbooru",
                page_url="https://example.test/posts/6",
                file_url="https://example.test/6.jpg",
                preview_url="https://example.test/6.jpg",
                width=800,
                height=1200,
            ).orientation,
            "portrait",
        )
        self.assertIsNone(
            Post(
                id=7,
                booru="Danbooru",
                page_url="https://example.test/posts/7",
                file_url="https://example.test/7.jpg",
                preview_url="https://example.test/7.jpg",
                width=0,
                height=0,
            ).orientation
        )


class TagSuggestionTests(unittest.IsolatedAsyncioTestCase):
    async def test_konachan_search_uses_moebooru_post_endpoint(self) -> None:
        requests: list[httpx.Request] = []

        async def respond(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(
                200,
                json=[
                    {
                        "id": 31,
                        "file_url": "https://cdn.example/31.jpg",
                        "tags": "sample_tag",
                        "rating": "s",
                    }
                ],
            )

        client = KonachanClient()
        await client.close()
        client._http = httpx.AsyncClient(transport=httpx.MockTransport(respond))
        try:
            posts = await client.search("sample_tag", page=2)
            self.assertEqual(requests[0].url.host, "konachan.net")
            self.assertEqual(requests[0].url.path, "/post.json")
            self.assertEqual(requests[0].url.params["page"], "2")
            self.assertEqual(posts[0].page_url, "https://konachan.net/post/show/31")
        finally:
            await client.close()

    async def test_engine_tag_endpoints_normalize_suggestions(self) -> None:
        cases = (
            (DanbooruClient(), "/tags.json", "search[name_matches]", "blue*"),
            (GelbooruClient(), "/index.php", "name_pattern", "blue*"),
            (SafebooruClient(), "/index.php", "name_pattern", "blue*"),
            (MoebooruClient(), "/tag.json", "name", "blue"),
            (KonachanClient(), "/tag.json", "name", "blue"),
        )
        for client, expected_path, parameter, expected_value in cases:
            requests: list[httpx.Request] = []

            async def respond(request: httpx.Request) -> httpx.Response:
                requests.append(request)
                if isinstance(client, (GelbooruClient, SafebooruClient)):
                    body = {"tag": [{"name": "blue_eyes", "count": "123"}]}
                else:
                    body = [{"name": "blue_eyes", "post_count": 123}]
                return httpx.Response(200, json=body)

            await client.close()
            client._http = httpx.AsyncClient(
                transport=httpx.MockTransport(respond)
            )
            try:
                suggestions = await client.suggest_tags("blue")
                self.assertEqual(requests[0].url.path, expected_path)
                self.assertEqual(requests[0].url.params[parameter], expected_value)
                self.assertEqual(suggestions[0].name, "blue_eyes")
                self.assertEqual(suggestions[0].post_count, 123)
            finally:
                await client.close()


class DownloadManagerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.executor = ThreadPoolExecutor(max_workers=2)
        asyncio.get_running_loop().set_default_executor(self.executor)

    async def test_batch_is_bounded_and_writes_complete_files(self) -> None:
        active = 0
        peak_active = 0

        async def respond(request: httpx.Request) -> httpx.Response:
            nonlocal active, peak_active
            active += 1
            peak_active = max(peak_active, active)
            await asyncio.sleep(0.01)
            active -= 1
            return httpx.Response(200, content=b"image-data")

        manager = DownloadManager(parallel_downloads=2)
        await manager.close()
        manager._http = httpx.AsyncClient(transport=httpx.MockTransport(respond))
        posts = [
            Post(
                id=post_id,
                booru="Danbooru",
                page_url=f"https://example.test/posts/{post_id}",
                file_url=f"https://cdn.example/{post_id}.jpg",
                preview_url=f"https://cdn.example/{post_id}.jpg",
                file_ext="jpg",
            )
            for post_id in range(5)
        ]
        try:
            with tempfile.TemporaryDirectory() as temporary_directory:
                paths = await manager.download_many(
                    posts, Path(temporary_directory), "{id}.{ext}"
                )
                self.assertEqual(len(paths), 5)
                self.assertTrue(all(path.read_bytes() == b"image-data" for path in paths))
                self.assertLessEqual(peak_active, 2)
                partial_files = [
                    path
                    for path in Path(temporary_directory).rglob("*")
                    if path.name.endswith(".part")
                ]
                self.assertFalse(partial_files)
        finally:
            await manager.close()


if __name__ == "__main__":
    unittest.main()
