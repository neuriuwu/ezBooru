"""Primary navigation and search-library controls."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class Sidebar(QWidget):
    artist_search_requested = Signal(str)
    save_search_requested = Signal()
    saved_search_activated = Signal(object)
    remove_saved_search_requested = Signal(int)
    favorites_requested = Signal()
    blacklist_edited = Signal(str)
    destination_requested = Signal()
    download_loaded_requested = Signal()
    download_everything_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("sidebar")
        self.setFixedWidth(238)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 20, 16, 16)
        layout.setSpacing(10)

        title = QLabel("ezBooru")
        title.setObjectName("brand")
        layout.addWidget(title)
        subtitle = QLabel("BOORU BROWSER")
        subtitle.setObjectName("sidebarCaption")
        layout.addWidget(subtitle)
        self._section(layout, "ARTIST SEARCH")
        self.artist_query = QLineEdit()
        self.artist_query.setPlaceholderText("artist_tag")
        self.artist_query.setToolTip(
            "Search using the booru's artist tag, for example sample_artist."
        )
        self.artist_query.returnPressed.connect(self._search_artist)
        layout.addWidget(self.artist_query)
        artist_button = QPushButton("Search artist")
        artist_button.clicked.connect(self._search_artist)
        layout.addWidget(artist_button)

        self._section(layout, "SAVED SEARCHES")
        self.saved_search_list = QListWidget()
        self.saved_search_list.setMinimumHeight(110)
        self.saved_search_list.itemDoubleClicked.connect(self._open_selected_search)
        layout.addWidget(self.saved_search_list, 1)
        search_buttons = QWidget()
        search_buttons_layout = QVBoxLayout(search_buttons)
        search_buttons_layout.setContentsMargins(0, 0, 0, 0)
        save_search = QPushButton("Save current search")
        save_search.clicked.connect(self.save_search_requested.emit)
        remove_search = QPushButton("Remove selected")
        remove_search.clicked.connect(self._remove_selected_search)
        search_buttons_layout.addWidget(save_search)
        search_buttons_layout.addWidget(remove_search)
        layout.addWidget(search_buttons)

        favorites = QPushButton("♥  Favorites")
        favorites.setObjectName("navigationButton")
        favorites.clicked.connect(self.favorites_requested.emit)
        layout.addWidget(favorites)

        self._section(layout, "BLACKLISTED TAGS")
        self.blacklist = QLineEdit()
        self.blacklist.setPlaceholderText("tag_one, tag_two")
        self.blacklist.setToolTip("Posts with any listed tag are hidden from search results.")
        self.blacklist.editingFinished.connect(
            lambda: self.blacklist_edited.emit(self.blacklist.text())
        )
        layout.addWidget(self.blacklist)

        self._section(layout, "DOWNLOAD MANAGER")
        self.destination_button = QPushButton("Choose download folder…")
        self.destination_button.clicked.connect(self.destination_requested.emit)
        layout.addWidget(self.destination_button)
        loaded_button = QPushButton("Download loaded results")
        loaded_button.clicked.connect(self.download_loaded_requested.emit)
        layout.addWidget(loaded_button)
        everything_button = QPushButton("Download all matching")
        everything_button.setObjectName("primaryButton")
        everything_button.clicked.connect(self.download_everything_requested.emit)
        layout.addWidget(everything_button)
        layout.addStretch(1)

    def set_saved_searches(self, searches: list[dict[str, str]]) -> None:
        self.saved_search_list.clear()
        for search in searches:
            item = f"{search['booru']}  ·  {search['query']}"
            list_item = QListWidgetItem(item)
            list_item.setData(Qt.ItemDataRole.UserRole, search)
            self.saved_search_list.addItem(list_item)

    def set_destination(self, directory: str) -> None:
        self.destination_button.setText(directory or "Choose download folder…")
        self.destination_button.setToolTip(directory)

    @staticmethod
    def _section(layout: QVBoxLayout, title: str) -> None:
        label = QLabel(title)
        label.setObjectName("sidebarCaption")
        layout.addWidget(label)

    def _search_artist(self) -> None:
        artist = self.artist_query.text().strip()
        if artist:
            self.artist_search_requested.emit(artist)

    def _open_selected_search(self, item: QListWidgetItem) -> None:
        search = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(search, dict):
            self.saved_search_activated.emit(search)

    def _remove_selected_search(self) -> None:
        row = self.saved_search_list.currentRow()
        if row >= 0:
            self.remove_saved_search_requested.emit(row)
