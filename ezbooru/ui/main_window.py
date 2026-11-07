"""Main search window and integration of APIs, cache, grid, and viewer."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Awaitable, Callable

from PySide6.QtCore import QModelIndex, QSettings, QTimer, QUrl, Qt
from PySide6.QtGui import (
    QCloseEvent,
    QDesktopServices,
    QImage,
    QKeySequence,
    QStandardItem,
    QStandardItemModel,
    QShortcut,
)
from PySide6.QtWidgets import (
    QApplication,
    QCompleter,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QProgressDialog,
    QVBoxLayout,
    QWidget,
)

from ezbooru.api_client import (
    BooruAPIError,
    BooruClient,
    DanbooruClient,
    GelbooruClient,
    KonachanClient,
    MoebooruClient,
    SafebooruClient,
    build_search_query,
)
from ezbooru.cache import ImageCache
from ezbooru.downloader import DownloadManager
from ezbooru.library import UserLibrary, filter_blacklisted, normalize_tags
from ezbooru.models import Post
from ezbooru.ui.grid import PostCard, PostGrid
from ezbooru.ui.sidebar import Sidebar
from ezbooru.ui.style import dark_stylesheet
from ezbooru.ui.viewer import PostViewer

_CLIENTS: dict[str, type[BooruClient]] = {
    "Danbooru": DanbooruClient,
    "Gelbooru": GelbooruClient,
    "Safebooru": SafebooruClient,
    "Moebooru (yande.re)": MoebooruClient,
    "Konachan (Safe)": KonachanClient,
}


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("ezBooru")
        self.resize(1280, 850)
        self.settings = QSettings("ezBooru", "ezBooru")
        self.settings.remove("accent")
        self.library = UserLibrary(self.settings)
        self.setStyleSheet(dark_stylesheet())
        self.cache = ImageCache()
        self.downloader = DownloadManager()
        self.client: BooruClient | None = None
        self.posts: list[Post] = []
        self.current_index = -1
        self.page = 1
        self._search_task: asyncio.Task[None] | None = None
        self._tag_suggestion_task: asyncio.Task[None] | None = None
        self._thumbnail_tasks: set[asyncio.Task[None]] = set()
        self._thumbnail_semaphore = asyncio.Semaphore(8)
        self._download_tasks: set[asyncio.Task[Any]] = set()
        self._viewer: PostViewer | None = None
        self._shutdown_started = False
        self._shutdown_complete = False
        self._showing_favorites = False
        self._download_progress: QProgressDialog | None = None
        self._current_download_task: asyncio.Task[Any] | None = None
        self._download_uses_client = False
        self._download_directory = self.library.download_directory or str(
            Path.home() / "Downloads" / "ezBooru"
        )

        central = QWidget()
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.sidebar = Sidebar()
        root.addWidget(self.sidebar)
        content = QWidget()
        content.setObjectName("content")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(20, 18, 20, 12)
        toolbar = QHBoxLayout()
        self.booru = QComboBox()
        self.booru.addItems(_CLIENTS)
        self.query = QLineEdit()
        self.query.setPlaceholderText("Search tags…")
        self.rating_filter = QComboBox()
        self.rating_filter.addItem("All ratings", "all")
        self.rating_filter.addItem("Safe", "safe")
        self.rating_filter.addItem("Questionable", "questionable")
        self.rating_filter.addItem("Explicit", "explicit")
        self.rating_filter.setToolTip("Append the selected rating tag to the search.")
        self.search_button = QPushButton("Search")
        toolbar.addWidget(self.booru)
        toolbar.addWidget(self.query, 1)
        toolbar.addWidget(self.rating_filter)
        toolbar.addWidget(self.search_button)
        self._tag_suggestion_model = QStandardItemModel(self)
        self._tag_completer = QCompleter(self._tag_suggestion_model, self.query)
        self._tag_completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self._tag_completer.setFilterMode(Qt.MatchFlag.MatchStartsWith)
        self.query.setCompleter(self._tag_completer)
        self._tag_suggestion_timer = QTimer(self)
        self._tag_suggestion_timer.setSingleShot(True)
        self._tag_suggestion_timer.setInterval(250)
        self._tag_suggestion_timer.timeout.connect(self._request_tag_suggestions)
        self._tag_suggestion_prefix = ""
        self._tag_suggestion_context = ""
        self.filename_template = QLineEdit("{artist}/{character}_{id}.{ext}")
        self.filename_template.setToolTip(
            "Supported fields: {id}, {artist}, {character}, {rating}, {ext}, {booru}"
        )
        content_layout.addLayout(toolbar)
        result_tools = QHBoxLayout()
        result_tools.addWidget(QLabel("Orientation"))
        self.orientation_filter = QComboBox()
        self.orientation_filter.addItems(
            ["All orientations", "Landscape", "Portrait", "Square"]
        )
        result_tools.addWidget(self.orientation_filter)
        result_tools.addWidget(QLabel("Filename"))
        result_tools.addWidget(self.filename_template, 1)
        content_layout.addLayout(result_tools)
        self.grid = PostGrid(self.library.is_favorite)
        content_layout.addWidget(self.grid, 1)
        self.status = QLabel("Ready")
        self.status.setObjectName("status")
        content_layout.addWidget(self.status)
        root.addWidget(content, 1)
        self.setCentralWidget(central)

        self.search_button.clicked.connect(self.start_search)
        self.query.returnPressed.connect(self.start_search)
        self.query.textEdited.connect(self._schedule_tag_suggestions)
        self._tag_completer.activated[QModelIndex].connect(
            self._insert_tag_suggestion
        )
        self.booru.currentTextChanged.connect(self._change_client)
        self.orientation_filter.currentTextChanged.connect(self._set_orientation)
        self.grid.post_selected.connect(self.open_post)
        self.grid.favorite_toggled.connect(self._toggle_favorite)
        self.grid.need_more.connect(self._load_next_page)
        self.sidebar.artist_search_requested.connect(self._search_artist)
        self.sidebar.save_search_requested.connect(self._save_search)
        self.sidebar.saved_search_activated.connect(self._open_saved_search)
        self.sidebar.remove_saved_search_requested.connect(self._remove_saved_search)
        self.sidebar.favorites_requested.connect(self._show_favorites)
        self.sidebar.blacklist_edited.connect(self._save_blacklist)
        self.sidebar.destination_requested.connect(self._choose_download_directory)
        self.sidebar.download_loaded_requested.connect(self._download_loaded_posts)
        self.sidebar.download_everything_requested.connect(self._download_everything)
        self.sidebar.set_saved_searches(self.library.saved_searches)
        self.sidebar.set_destination(self._download_directory)
        self.sidebar.blacklist.setText(", ".join(self.library.blacklisted_tags))
        self._change_client(self.booru.currentText())
        self._install_shortcuts()

    def _change_client(self, name: str) -> None:
        previous = self.client
        old_search = self._search_task
        old_suggestions = self._tag_suggestion_task
        self._tag_suggestion_timer.stop()
        old_thumbnails = self._cancel_thumbnail_tasks()
        if old_search is not None and not old_search.done():
            old_search.cancel()
        if old_suggestions is not None and not old_suggestions.done():
            old_suggestions.cancel()
        self.client = _CLIENTS[name]()
        if previous is not None:
            self._showing_favorites = False
            asyncio.create_task(
                self._close_previous_client(
                    previous, old_search, old_suggestions, old_thumbnails
                )
            )
            self.posts.clear()
            self.current_index = -1
            self.page = 1
            self.grid.set_posts([])
            self.status.setText(f"Selected {name}. Search for posts to begin.")

    async def _close_previous_client(
        self,
        client: BooruClient,
        search_task: asyncio.Task[None] | None,
        suggestion_task: asyncio.Task[None] | None,
        thumbnail_tasks: list[asyncio.Task[None]],
    ) -> None:
        pending = [
            task
            for task in [search_task, suggestion_task, *thumbnail_tasks]
            if task is not None
        ]
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        await client.close()

    def _install_shortcuts(self) -> None:
        for sequence, delta in (
            ("J", 1),
            ("Down", 1),
            ("K", -1),
            ("Up", -1),
        ):
            shortcut = QShortcut(QKeySequence(sequence), self)
            shortcut.activated.connect(lambda step=delta: self._select_relative(step))
        save = QShortcut(QKeySequence("S"), self)
        save.activated.connect(self._save_selected)

    def _select_relative(self, delta: int) -> None:
        visible_indices = [
            index
            for index, post in enumerate(self.posts)
            if self.grid.is_post_visible(post)
        ]
        if not visible_indices:
            return
        if 0 <= self.current_index < len(self.grid.cards):
            self.grid.cards[self.current_index].set_selected(False)
        try:
            current_position = visible_indices.index(self.current_index)
        except ValueError:
            current_position = -1 if delta >= 0 else len(visible_indices)
        next_position = min(
            max(current_position + delta, 0), len(visible_indices) - 1
        )
        self.current_index = visible_indices[next_position]
        self.grid.cards[self.current_index].set_selected(True)
        self.status.setText(f"Selected post #{self.posts[self.current_index].id}")

    def _save_selected(self) -> None:
        if 0 <= self.current_index < len(self.posts):
            self._save_post(self.posts[self.current_index])

    def start_search(self) -> None:
        self._tag_suggestion_timer.stop()
        if self._tag_suggestion_task is not None:
            self._tag_suggestion_task.cancel()
        self._tag_suggestion_model.clear()
        self._tag_completer.popup().hide()
        if self._search_task is not None and not self._search_task.done():
            self._search_task.cancel()
        self._save_blacklist(self.sidebar.blacklist.text())
        self._showing_favorites = False
        self.page = 1
        self.posts.clear()
        self.current_index = -1
        self.grid.set_posts([])
        self._cancel_thumbnail_tasks()
        self._search_task = asyncio.create_task(self._search_page(replace=True))

    def _build_query(self) -> str:
        return build_search_query(
            self.query.text(), str(self.rating_filter.currentData())
        )

    def _set_orientation(self, orientation: str) -> None:
        normalized = orientation.casefold().replace(" orientations", "")
        if 0 <= self.current_index < len(self.grid.cards):
            self.grid.cards[self.current_index].set_selected(False)
        self.grid.set_orientation(normalized)
        if 0 <= self.current_index < len(self.posts):
            if not self.grid.is_post_visible(self.posts[self.current_index]):
                self.current_index = -1

    def _schedule_tag_suggestions(self, text: str) -> None:
        self._tag_suggestion_timer.stop()
        if self._tag_suggestion_task is not None:
            self._tag_suggestion_task.cancel()
        self._tag_suggestion_model.clear()
        self._tag_completer.popup().hide()
        if not text or text[-1].isspace():
            return
        tokens = text.split()
        prefix = tokens[-1] if tokens else ""
        if len(prefix) < 2 or ":" in prefix:
            return
        self._tag_suggestion_prefix = prefix
        self._tag_suggestion_context = text[: len(text) - len(prefix)]
        self._tag_suggestion_timer.start()

    def _request_tag_suggestions(self) -> None:
        if self.client is not None:
            self._tag_suggestion_task = asyncio.create_task(
                self._load_tag_suggestions(self.client, self._tag_suggestion_prefix)
            )

    async def _load_tag_suggestions(self, client: BooruClient, prefix: str) -> None:
        try:
            suggestions = await client.suggest_tags(prefix)
        except asyncio.CancelledError:
            raise
        except BooruAPIError as exc:
            if client is self.client:
                self.status.setText(f"Tag suggestions unavailable: {exc}")
        else:
            current_token = self.query.text().split()[-1:] or [""]
            if client is not self.client or current_token[0] != prefix:
                return
            self._tag_suggestion_model.clear()
            for suggestion in suggestions:
                item = QStandardItem(
                    f"{suggestion.name}  ·  {suggestion.post_count:,} posts"
                )
                item.setData(suggestion.name, Qt.ItemDataRole.UserRole)
                self._tag_suggestion_model.appendRow(item)
            if suggestions:
                self._tag_completer.complete()
            else:
                self._tag_completer.popup().hide()

    def _insert_tag_suggestion(self, index: QModelIndex) -> None:
        tag = index.data(Qt.ItemDataRole.UserRole)
        if not isinstance(tag, str):
            return
        query = f"{self._tag_suggestion_context}{tag} "
        self.query.setText(query)
        self.query.setCursorPosition(len(query))

    def _cancel_thumbnail_tasks(self) -> list[asyncio.Task[None]]:
        tasks = list(self._thumbnail_tasks)
        for task in tasks:
            task.cancel()
        self._thumbnail_tasks.clear()
        return tasks

    async def _search_page(self, replace: bool) -> None:
        if self.client is None:
            return
        self.search_button.setEnabled(False)
        self.status.setText("Searching…")
        try:
            results: list[Post] = []
            while True:
                page_results = await self.client.search(
                    self._build_query(), self.page
                )
                results = filter_blacklisted(
                    page_results, self.library.blacklisted_tags
                )
                if results or not page_results:
                    break
                self.page += 1
        except asyncio.CancelledError:
            raise
        except BooruAPIError as exc:
            self.status.setText(str(exc))
        else:
            if replace:
                self.posts = results
                self.grid.set_posts(results)
            else:
                self.posts.extend(results)
                for post in results:
                    self.grid.add_post(post)
            if results:
                self.status.setText(f"{len(self.posts)} posts · page {self.page}")
                start = len(self.posts) - len(results)
                for offset, post in enumerate(results):
                    card = self.grid.cards[start + offset]
                    task = asyncio.create_task(self._load_thumbnail(post, card))
                    self._thumbnail_tasks.add(task)
                    task.add_done_callback(self._thumbnail_tasks.discard)
            else:
                self.status.setText("No more posts found." if not replace else "No posts found.")
        finally:
            self.search_button.setEnabled(True)

    def _load_next_page(self) -> None:
        if self._showing_favorites:
            return
        if self._search_task is not None and not self._search_task.done():
            return
        self.page += 1
        self._search_task = asyncio.create_task(self._search_page(replace=False))

    async def _load_thumbnail(self, post: Post, card: PostCard) -> None:
        if not post.preview_url:
            card.set_error()
            return
        try:
            async with self._thumbnail_semaphore:
                image_bytes = await self.cache.get(post.preview_url)
                image = await asyncio.to_thread(QImage.fromData, image_bytes)
        except RuntimeError:
            card.set_error()
        else:
            card.set_image(image)

    def open_post(self, post: Post) -> None:
        try:
            self.current_index = self.posts.index(post)
        except ValueError:
            self.current_index = -1
        if self.current_index >= 0:
            for index, card in enumerate(self.grid.cards):
                card.set_selected(index == self.current_index)
        viewer = PostViewer(post, self)
        self._viewer = viewer
        viewer.save_requested.connect(self._save_post)
        viewer.favorite_requested.connect(self._toggle_favorite)
        viewer.open_requested.connect(self._open_page)
        viewer.set_favorite(self.library.is_favorite(post))
        viewer.show()
        asyncio.create_task(self._load_full_image(post, viewer))

    async def _load_full_image(self, post: Post, viewer: PostViewer) -> None:
        try:
            image_bytes = await self.cache.get(post.file_url)
        except RuntimeError as exc:
            viewer.status.setText(str(exc))
        else:
            if viewer.isVisible():
                image = await asyncio.to_thread(QImage.fromData, image_bytes)
                viewer.set_image(image)

    def _open_page(self, post: Post) -> None:
        if not QDesktopServices.openUrl(QUrl(post.page_url)):
            self.status.setText("Could not open the post page in a browser.")

    def _search_artist(self, artist: str) -> None:
        self.query.setText(artist.strip().replace(" ", "_"))
        self.start_search()

    def _save_search(self) -> None:
        added = self.library.save_search(
            self.booru.currentText(), self._build_query()
        )
        if added:
            self.sidebar.set_saved_searches(self.library.saved_searches)
            self.status.setText("Search saved.")
        else:
            self.status.setText("Enter a new search query to save it.")

    def _open_saved_search(self, search: dict[str, str]) -> None:
        index = self.booru.findText(search["booru"])
        if index >= 0:
            self.booru.setCurrentIndex(index)
        rating_tags = {
            f"rating:{self.rating_filter.itemData(row)}": self.rating_filter.itemData(
                row
            )
            for row in range(1, self.rating_filter.count())
        }
        tokens = search["query"].split()
        saved_rating = next(
            (
                rating_tags[token.casefold()]
                for token in tokens
                if token.casefold() in rating_tags
            ),
            "all",
        )
        self.rating_filter.setCurrentIndex(self.rating_filter.findData(saved_rating))
        self.query.setText(
            " ".join(token for token in tokens if token.casefold() not in rating_tags)
        )
        self.start_search()

    def _remove_saved_search(self, index: int) -> None:
        self.library.remove_search(index)
        self.sidebar.set_saved_searches(self.library.saved_searches)
        self.status.setText("Saved search removed.")

    def _save_blacklist(self, value: str) -> None:
        self.library.blacklisted_tags = value.replace(",", " ").split()
        self.sidebar.blacklist.setText(", ".join(self.library.blacklisted_tags))
        self.status.setText(
            f"Blacklisted {len(self.library.blacklisted_tags)} tag(s). "
            "The filter applies to future results."
        )

    def _toggle_favorite(self, post: Post) -> None:
        favorite = self.library.toggle_favorite(post)
        for card in self.grid.cards:
            if card.post.booru == post.booru and card.post.id == post.id:
                card.set_favorite(favorite)
        if self._viewer is not None and self._viewer.post == post:
            self._viewer.set_favorite(favorite)
        self.status.setText(
            f"Post #{post.id} {'added to' if favorite else 'removed from'} favorites."
        )
        if self._showing_favorites and not favorite:
            self._show_favorites()

    def _show_favorites(self) -> None:
        if self._search_task is not None and not self._search_task.done():
            self._search_task.cancel()
        self._cancel_thumbnail_tasks()
        self._showing_favorites = True
        self.posts = self.library.favorites
        self.current_index = -1
        self.page = 1
        self.grid.set_posts(self.posts)
        self.status.setText(f"{len(self.posts)} favorite post(s)")
        for post, card in zip(self.posts, self.grid.cards, strict=True):
            task = asyncio.create_task(self._load_thumbnail(post, card))
            self._thumbnail_tasks.add(task)
            task.add_done_callback(self._thumbnail_tasks.discard)

    def _choose_download_directory(self) -> None:
        directory = QFileDialog.getExistingDirectory(
            self, "Choose download folder", self._download_directory
        )
        if directory:
            self._download_directory = directory
            self.library.download_directory = directory
            self.sidebar.set_destination(directory)
            self.status.setText(f"Downloads will be saved in {directory}")

    def _save_post(self, post: Post) -> None:
        if not self._download_directory:
            self.status.setText("Choose a download folder first.")
            return
        self._start_download_operation(
            lambda: self._download_one_async(post),
            f"Downloading post #{post.id}…",
            0,
        )

    def _download_loaded_posts(self) -> None:
        if not self.posts:
            self.status.setText("Search for posts before starting a batch download.")
            return
        self._start_download_operation(
            lambda: self._download_posts_async(list(self.posts)),
            f"Downloading {len(self.posts)} loaded posts…",
            len(self.posts),
        )

    def _download_everything(self) -> None:
        if self._showing_favorites:
            self.status.setText("Return to search results before downloading all matches.")
            return
        if self.client is None or not self._build_query():
            self.status.setText("Enter a search query before downloading all matches.")
            return
        answer = QMessageBox.question(
            self,
            "Download all matching posts",
            "Fetch every page for this search and download all posts that are not "
            "blacklisted? This can use significant network traffic and disk space.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._start_download_operation(
            self._download_everything_async,
            "Fetching matching posts…",
            0,
            uses_client=True,
        )

    def _start_download_operation(
        self,
        operation: Callable[[], Awaitable[Any]],
        label: str,
        total: int,
        uses_client: bool = False,
    ) -> None:
        if self._current_download_task is not None and not self._current_download_task.done():
            self.status.setText("A download operation is already running.")
            return
        progress = QProgressDialog(label, "Cancel", 0, total, self)
        progress.setWindowTitle("Download manager")
        progress.setMinimumDuration(0)
        progress.setAutoClose(False)
        progress.setAutoReset(False)
        self._download_progress = progress
        progress.show()
        task = asyncio.create_task(operation())
        self._current_download_task = task
        self._download_uses_client = uses_client
        if uses_client:
            self.booru.setEnabled(False)
        progress.canceled.connect(task.cancel)
        self._download_tasks.add(task)
        task.add_done_callback(self._download_tasks.discard)
        task.add_done_callback(self._finish_download_operation)

    def _finish_download_operation(self, task: asyncio.Task[Any]) -> None:
        if self._download_progress is not None:
            self._download_progress.close()
            self._download_progress = None
        self._current_download_task = None
        if self._download_uses_client:
            self.booru.setEnabled(True)
        self._download_uses_client = False
        if task.cancelled():
            self.status.setText("Download cancelled.")
            return
        error = task.exception()
        if error is not None:
            self.status.setText(str(error))
            QMessageBox.warning(self, "Download failed", str(error))

    async def _download_one_async(self, post: Post) -> None:
        destination = Path(self._download_directory) / f"{post.id}.{post.file_ext or 'img'}"
        path = await self.downloader.download_post(post, destination)
        self.status.setText(f"Saved {path}")

    async def _download_posts_async(self, posts: list[Post]) -> None:
        output_dir = Path(self._download_directory)
        count = 0

        def downloaded(_path: Path) -> None:
            nonlocal count
            count += 1
            if self._download_progress is not None:
                self._download_progress.setValue(count)
                self._download_progress.setLabelText(
                    f"Downloaded {count} of {len(posts)} posts…"
                )

        paths = await self.downloader.download_many(
            posts,
            output_dir,
            self.filename_template.text(),
            on_downloaded=downloaded,
        )
        self.status.setText(f"Downloaded {len(paths)} posts to {output_dir}")

    async def _download_everything_async(self) -> None:
        if self.client is None:
            return
        output_dir = Path(self._download_directory)
        query = self._build_query()
        blacklist = self.library.blacklisted_tags
        seen: set[tuple[str, int]] = set()
        downloaded = 0
        page = 1
        while True:
            if self._download_progress is not None:
                self._download_progress.setLabelText(
                    f"Searching page {page} · downloaded {downloaded} posts…"
                )
            posts = await self.client.search(query, page)
            if not posts:
                break
            eligible = [
                post
                for post in filter_blacklisted(posts, blacklist)
                if (post.booru.casefold(), post.id) not in seen
            ]
            seen.update((post.booru.casefold(), post.id) for post in eligible)
            if eligible:
                completed = 0

                def update_progress(_path: Path) -> None:
                    nonlocal completed
                    completed += 1
                    if self._download_progress is not None:
                        self._download_progress.setLabelText(
                            f"Searching page {page} · downloaded "
                            f"{downloaded + completed} posts…"
                        )

                await self.downloader.download_many(
                    eligible,
                    output_dir,
                    self.filename_template.text(),
                    on_downloaded=update_progress,
                )
                downloaded += completed
            page += 1
        self.status.setText(f"Downloaded {downloaded} posts to {output_dir}")

    async def shutdown(self) -> None:
        self._tag_suggestion_timer.stop()
        if self._search_task is not None:
            self._search_task.cancel()
        if self._tag_suggestion_task is not None:
            self._tag_suggestion_task.cancel()
        for task in self._thumbnail_tasks:
            task.cancel()
        for task in self._download_tasks:
            task.cancel()
        pending = [
            task
            for task in [
                self._search_task,
                self._tag_suggestion_task,
                *self._thumbnail_tasks,
                *self._download_tasks,
            ]
            if task is not None
        ]
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        if self.client is not None:
            await self.client.close()
        await self.cache.close()
        await self.downloader.close()

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._shutdown_complete:
            event.accept()
            return
        event.ignore()
        if not self._shutdown_started:
            self._shutdown_started = True
            asyncio.create_task(self._finish_close())

    async def _finish_close(self) -> None:
        await self.shutdown()
        self._shutdown_complete = True
        self.close()
        QApplication.quit()
