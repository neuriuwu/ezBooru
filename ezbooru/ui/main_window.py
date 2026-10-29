"""Main search window and integration of APIs, cache, grid, and viewer."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from PySide6.QtCore import QSettings, QUrl
from PySide6.QtGui import (
    QCloseEvent,
    QColor,
    QDesktopServices,
    QImage,
    QKeySequence,
    QShortcut,
)
from PySide6.QtWidgets import (
    QApplication,
    QColorDialog,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ezbooru.api_client import (
    BooruAPIError,
    BooruClient,
    DanbooruClient,
    GelbooruClient,
    MoebooruClient,
    SafebooruClient,
)
from ezbooru.cache import ImageCache
from ezbooru.downloader import DownloadManager
from ezbooru.models import Post
from ezbooru.ui.grid import PostCard, PostGrid
from ezbooru.ui.style import dark_stylesheet
from ezbooru.ui.viewer import PostViewer

_CLIENTS: dict[str, type[BooruClient]] = {
    "Danbooru": DanbooruClient,
    "Gelbooru": GelbooruClient,
    "Safebooru": SafebooruClient,
    "Moebooru (yande.re)": MoebooruClient,
}


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("ezBooru")
        self.resize(1280, 850)
        self.settings = QSettings("ezBooru", "ezBooru")
        self.accent = self.settings.value("accent", "#8b7bff", str)
        self.setStyleSheet(dark_stylesheet(self.accent))
        self.cache = ImageCache()
        self.downloader = DownloadManager()
        self.client: BooruClient | None = None
        self.posts: list[Post] = []
        self.current_index = -1
        self.page = 1
        self._search_task: asyncio.Task[None] | None = None
        self._thumbnail_tasks: set[asyncio.Task[None]] = set()
        self._thumbnail_semaphore = asyncio.Semaphore(8)
        self._download_tasks: set[asyncio.Task[Any]] = set()
        self._viewer: PostViewer | None = None
        self._shutdown_started = False
        self._shutdown_complete = False

        central = QWidget()
        root = QVBoxLayout(central)
        toolbar = QHBoxLayout()
        self.booru = QComboBox()
        self.booru.addItems(_CLIENTS)
        self.query = QLineEdit()
        self.query.setPlaceholderText("Search tags (space-separated)")
        self.search_button = QPushButton("Search")
        self.theme_button = QPushButton("Accent")
        toolbar.addWidget(self.booru)
        toolbar.addWidget(self.query, 1)
        toolbar.addWidget(self.search_button)
        toolbar.addWidget(self.theme_button)
        root.addLayout(toolbar)
        download_toolbar = QHBoxLayout()
        download_toolbar.addWidget(QLabel("Filename template"))
        self.filename_template = QLineEdit("{artist}/{character}_{id}.{ext}")
        self.filename_template.setToolTip(
            "Supported fields: {id}, {artist}, {character}, {rating}, {ext}, {booru}"
        )
        self.download_button = QPushButton("Download loaded posts")
        download_toolbar.addWidget(self.filename_template, 1)
        download_toolbar.addWidget(self.download_button)
        root.addLayout(download_toolbar)
        self.grid = PostGrid()
        root.addWidget(self.grid, 1)
        self.status = QLabel("Ready")
        root.addWidget(self.status)
        self.setCentralWidget(central)

        self.search_button.clicked.connect(self.start_search)
        self.query.returnPressed.connect(self.start_search)
        self.booru.currentTextChanged.connect(self._change_client)
        self.theme_button.clicked.connect(self._choose_accent)
        self.download_button.clicked.connect(self._download_loaded_posts)
        self.grid.post_selected.connect(self.open_post)
        self.grid.need_more.connect(self._load_next_page)
        self._change_client(self.booru.currentText())
        self._install_shortcuts()

    def _change_client(self, name: str) -> None:
        previous = self.client
        old_search = self._search_task
        old_thumbnails = list(self._thumbnail_tasks)
        if old_search is not None and not old_search.done():
            old_search.cancel()
        for task in old_thumbnails:
            task.cancel()
        self._thumbnail_tasks.clear()
        self.client = _CLIENTS[name]()
        if previous is not None:
            asyncio.create_task(
                self._close_previous_client(previous, old_search, old_thumbnails)
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
        thumbnail_tasks: list[asyncio.Task[None]],
    ) -> None:
        pending = [
            task
            for task in [search_task, *thumbnail_tasks]
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
        if not self.posts:
            return
        if 0 <= self.current_index < len(self.grid.cards):
            self.grid.cards[self.current_index].set_selected(False)
        self.current_index = min(max(self.current_index + delta, 0), len(self.posts) - 1)
        self.grid.cards[self.current_index].set_selected(True)
        self.status.setText(f"Selected post #{self.posts[self.current_index].id}")

    def _save_selected(self) -> None:
        if 0 <= self.current_index < len(self.posts):
            self._save_post(self.posts[self.current_index])

    def _choose_accent(self) -> None:
        color = QColorDialog.getColor(QColor(self.accent), self, "Choose accent color")
        if color.isValid():
            self.accent = color.name()
            self.settings.setValue("accent", self.accent)
            self.setStyleSheet(dark_stylesheet(self.accent))

    def start_search(self) -> None:
        if self._search_task is not None and not self._search_task.done():
            self._search_task.cancel()
        self.page = 1
        self.posts.clear()
        self.current_index = -1
        self.grid.set_posts([])
        for task in self._thumbnail_tasks:
            task.cancel()
        self._thumbnail_tasks.clear()
        self._search_task = asyncio.create_task(self._search_page(replace=True))

    async def _search_page(self, replace: bool) -> None:
        if self.client is None:
            return
        self.search_button.setEnabled(False)
        self.status.setText("Searching…")
        try:
            results = await self.client.search(self.query.text().strip(), self.page)
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
        viewer.open_requested.connect(self._open_page)
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

    def _save_post(self, post: Post) -> None:
        default_name = f"{post.id}.{post.file_ext or 'img'}"
        filename, _ = QFileDialog.getSaveFileName(
            self, "Save post", str(Path.home() / "Downloads" / default_name)
        )
        if not filename:
            return
        task = asyncio.create_task(self._save_post_async(post, Path(filename)))
        self._track_download(task)

    def _download_loaded_posts(self) -> None:
        if not self.posts:
            self.status.setText("Search for posts before starting a batch download.")
            return
        directory = QFileDialog.getExistingDirectory(self, "Download posts to")
        if not directory:
            return
        task = asyncio.create_task(
            self._download_batch_async(
                list(self.posts), Path(directory), self.filename_template.text()
            )
        )
        self._track_download(task)

    def _track_download(self, task: asyncio.Task[Any]) -> None:
        self._download_tasks.add(task)
        task.add_done_callback(self._download_tasks.discard)
        task.add_done_callback(self._show_task_error)

    async def _save_post_async(self, post: Post, destination: Path) -> None:
        self.status.setText(f"Downloading post #{post.id}…")
        path = await self.downloader.download_post(post, destination)
        self.status.setText(f"Saved {path}")

    async def _download_batch_async(
        self, posts: list[Post], output_dir: Path, template: str
    ) -> None:
        self.download_button.setEnabled(False)
        self.status.setText(f"Downloading {len(posts)} loaded posts…")
        try:
            paths = await self.downloader.download_many(posts, output_dir, template)
        finally:
            self.download_button.setEnabled(True)
        self.status.setText(f"Downloaded {len(paths)} posts to {output_dir}")

    def _show_task_error(self, task: asyncio.Task[Any]) -> None:
        if task.cancelled():
            return
        error = task.exception()
        if error is not None:
            self.status.setText(str(error))
            QMessageBox.warning(self, "Download failed", str(error))

    async def shutdown(self) -> None:
        if self._search_task is not None:
            self._search_task.cancel()
        for task in self._thumbnail_tasks:
            task.cancel()
        for task in self._download_tasks:
            task.cancel()
        pending = [
            task
            for task in [
                self._search_task,
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
