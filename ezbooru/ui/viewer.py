"""Post detail dialog with zoomable image and categorized tags."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QImage, QPixmap, QWheelEvent
from PySide6.QtWidgets import (
    QDialog,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ezbooru.models import Post

_TAG_COLORS = {
    "artist": "#e99b9b",
    "character": "#9cc9ef",
    "copyright": "#c4a4ef",
    "general": "#d4d5dc",
    "meta": "#8f969f",
}


class ZoomView(QGraphicsView):
    def __init__(self) -> None:
        super().__init__()
        self.setScene(QGraphicsScene(self))
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setBackgroundBrush(Qt.GlobalColor.black)

    def set_image(self, pixmap: QPixmap) -> None:
        scene = self.scene()
        if scene is None:
            return
        scene.clear()
        scene.addPixmap(pixmap)
        scene.setSceneRect(pixmap.rect())
        self.fitInView(scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def wheelEvent(self, event: QWheelEvent) -> None:
        factor = 1.18 if event.angleDelta().y() > 0 else 1 / 1.18
        self.scale(factor, factor)


class PostViewer(QDialog):
    save_requested = Signal(object)
    open_requested = Signal(object)

    def __init__(self, post: Post, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.post = post
        self.setWindowTitle(f"{post.booru} post #{post.id}")
        self.resize(1100, 760)
        root = QVBoxLayout(self)
        content = QHBoxLayout()
        self.image_view = ZoomView()
        self.image_view.setMinimumSize(500, 420)
        self.tags = QListWidget()
        self.tags.setMinimumWidth(240)
        self.tags.setMaximumWidth(320)
        for category, tags in post.tags_by_category.items():
            if not tags:
                continue
            self.tags.addItem(category.title())
            item = self.tags.item(self.tags.count() - 1)
            item.setForeground(Qt.GlobalColor.gray)
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            for tag in tags:
                self.tags.addItem(f"  {tag.name}")
                self.tags.item(self.tags.count() - 1).setForeground(
                    QColor(_TAG_COLORS[category])
                )
        content.addWidget(self.image_view, 1)
        content.addWidget(self.tags)
        root.addLayout(content, 1)
        buttons = QHBoxLayout()
        self.status = QLabel(f"{post.rating.title()} · {post.media_type} · #{post.id}")
        save = QPushButton("Save")
        copy = QPushButton("Copy Link")
        open_page = QPushButton("Open in Browser")
        save.clicked.connect(lambda: self.save_requested.emit(post))
        copy.clicked.connect(self._copy_link)
        open_page.clicked.connect(lambda: self.open_requested.emit(post))
        buttons.addWidget(self.status)
        buttons.addStretch(1)
        buttons.addWidget(save)
        buttons.addWidget(copy)
        buttons.addWidget(open_page)
        root.addLayout(buttons)

    def set_image(self, image: QImage) -> None:
        if image.isNull():
            self.status.setText("The image could not be decoded.")
            return
        self.image_view.set_image(QPixmap.fromImage(image))

    def _copy_link(self) -> None:
        from PySide6.QtWidgets import QApplication

        QApplication.clipboard().setText(self.post.page_url)
