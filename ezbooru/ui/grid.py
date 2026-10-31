"""Responsive, scrollable post thumbnail grid."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtGui import QImage, QMouseEvent, QPixmap
from PySide6.QtWidgets import (
    QGridLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ezbooru.models import Post

_RATING_COLORS = {
    "general": "#65c98a",
    "sensitive": "#e6bf62",
    "questionable": "#ed8d55",
    "explicit": "#e56d7e",
}


class PostCard(QWidget):
    clicked = Signal(object)
    favorite_toggled = Signal(object)
    CARD_WIDTH = 194

    def __init__(self, post: Post) -> None:
        super().__init__()
        self.post = post
        self.setFixedSize(self.CARD_WIDTH, 238)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(
            "PostCard { background:#22242b; border:1px solid #33353e; border-radius:9px; }"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        self.image = QLabel("Loading preview…")
        self.image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image.setFixedSize(176, 176)
        self.image.setStyleSheet("background:#191a20; border-radius:5px;")
        self.image.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.details = QLabel(self._details_text())
        self.details.setWordWrap(True)
        self.details.setMaximumHeight(42)
        self.favorite_button = QPushButton("☆")
        self.favorite_button.setFixedSize(30, 28)
        self.favorite_button.setToolTip("Add to favorites")
        self.favorite_button.clicked.connect(lambda: self.favorite_toggled.emit(self.post))
        self.favorite_button.setParent(self)
        self.favorite_button.move(self.width() - 40, 8)
        self.favorite_button.raise_()
        layout.addWidget(self.image)
        layout.addWidget(self.details)

    def set_favorite(self, favorite: bool) -> None:
        self.favorite_button.setText("★" if favorite else "☆")
        self.favorite_button.setToolTip(
            "Remove from favorites" if favorite else "Add to favorites"
        )

    def _details_text(self) -> str:
        color = _RATING_COLORS.get(self.post.rating, "#9ca0ad")
        return (
            f'<span style="color:{color};font-weight:600">{self.post.rating.title()}</span>'
            f" &nbsp; {self.post.media_type} &nbsp; #{self.post.id}"
        )

    def set_image(self, image: QImage) -> None:
        if image.isNull():
            self.image.setText("Invalid image")
            return
        pixmap = QPixmap.fromImage(image)
        self.image.setPixmap(
            pixmap.scaled(
                self.image.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    def set_error(self) -> None:
        self.image.setText("Preview unavailable")

    def set_selected(self, selected: bool) -> None:
        border = "#8b7bff" if selected else "#33353e"
        width = 2 if selected else 1
        self.setStyleSheet(
            "PostCard { "
            f"background:#22242b; border:{width}px solid {border}; border-radius:9px;"
            " }"
        )

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.post)
        super().mousePressEvent(event)


class PostGrid(QScrollArea):
    post_selected = Signal(object)
    favorite_toggled = Signal(object)
    need_more = Signal()

    def __init__(self, favorite_lookup: Callable[[Post], bool] | None = None) -> None:
        super().__init__()
        self._favorite_lookup = favorite_lookup or (lambda post: False)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.content = QWidget()
        self.layout = QGridLayout(self.content)
        self.layout.setContentsMargins(8, 8, 8, 8)
        self.layout.setSpacing(12)
        self.setWidget(self.content)
        self.cards: list[PostCard] = []
        self.posts: list[Post] = []
        self._columns = 0
        self._layout_card_count = 0
        self._last_request_at = -1
        self.verticalScrollBar().valueChanged.connect(self._check_bottom)

    def set_posts(self, posts: list[Post]) -> None:
        self.posts = list(posts)
        self.cards.clear()
        while self.layout.count():
            item = self.layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._layout_card_count = 0
        for post in posts:
            self.cards.append(self._create_card(post))
        self._last_request_at = -1
        self._reflow()

    def add_post(self, post: Post) -> PostCard:
        card = self._create_card(post)
        self.posts.append(post)
        self.cards.append(card)
        self._reflow()
        return card

    def _create_card(self, post: Post) -> PostCard:
        card = PostCard(post)
        card.clicked.connect(self.post_selected.emit)
        card.favorite_toggled.connect(self.favorite_toggled.emit)
        card.set_favorite(self._favorite_lookup(post))
        return card

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._reflow()

    def _reflow(self) -> None:
        columns = max(1, (self.viewport().width() - 24) // (PostCard.CARD_WIDTH + 12))
        if columns == self._columns and len(self.cards) == self._layout_card_count:
            return
        self._columns = columns
        while self.layout.count():
            self.layout.takeAt(0)
        for index, card in enumerate(self.cards):
            self.layout.addWidget(card, index // columns, index % columns)
        self._layout_card_count = len(self.cards)
        self.layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        QTimer.singleShot(
            0, lambda: self._check_bottom(self.verticalScrollBar().value())
        )

    def _check_bottom(self, value: int) -> None:
        bar = self.verticalScrollBar()
        if self.posts and value >= max(0, bar.maximum() - 420):
            if self._last_request_at != len(self.posts):
                self._last_request_at = len(self.posts)
                self.need_more.emit()
