from pathlib import Path

from PySide6.QtCore import Qt, QSize, QEvent, Signal
from PySide6.QtGui import QIcon, QPixmap, QAction, QMovie
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from config import GIF_EMPTY
from logger import app_logger
from storage import (
    load_history,
    clear_history,
    remove_from_history,
    delete_manga_folder,
    load_settings,
)


class HistoryPage(QWidget):
    open_manga = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._gif_movie = None
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        content = QWidget()
        scroll.setWidget(content)
        outer.addWidget(scroll)

        layout = QVBoxLayout(content)
        layout.setContentsMargins(28, 24, 28, 20)
        layout.setSpacing(16)

        # ---------- header ----------
        header = QHBoxLayout()
        title = QLabel("История")
        title.setObjectName("title")
        header.addWidget(title)
        header.addStretch()

        self.sel_label = QLabel("")
        self.sel_label.setObjectName("muted")
        header.addWidget(self.sel_label)
        header.addSpacing(12)

        refresh_btn = QPushButton("Обновить")
        refresh_btn.clicked.connect(self.refresh)
        header.addWidget(refresh_btn)

        clear_btn = QPushButton("Очистить всё")
        clear_btn.clicked.connect(self.clear_all)
        header.addWidget(clear_btn)

        layout.addLayout(header)

        # ---------- карточка со списком ----------
        card = QFrame()
        card.setObjectName("card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 16, 16, 16)
        card_layout.setSpacing(8)

        self.list = QListWidget()
        self.list.setViewMode(QListWidget.ListMode)
        self.list.setIconSize(QSize(64, 90))
        self.list.setSpacing(4)
        self.list.setMovement(QListWidget.Static)
        self.list.setWordWrap(True)
        self.list.setTextElideMode(Qt.ElideRight)
        self.list.setUniformItemSizes(True)
        self.list.setSelectionMode(QAbstractItemView.MultiSelection)

        self.list.itemDoubleClicked.connect(self._on_item_open)
        self.list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._context_menu)
        self.list.itemSelectionChanged.connect(self._update_sel_label)
        self.list.installEventFilter(self)

        card_layout.addWidget(self.list)
        layout.addWidget(card, 1)

        # ---------- пустое состояние ----------
        self.empty_box = QWidget()
        empty_layout = QVBoxLayout(self.empty_box)
        empty_layout.setContentsMargins(0, 40, 0, 40)
        empty_layout.setAlignment(Qt.AlignCenter)
        empty_layout.setSpacing(14)

        self.empty_gif = QLabel()
        self.empty_gif.setAlignment(Qt.AlignCenter)

        if Path(GIF_EMPTY).exists():
            self._gif_movie = QMovie(str(GIF_EMPTY))
            self._gif_movie.setScaledSize(QSize(220, 220))
            self.empty_gif.setMovie(self._gif_movie)
            self._gif_movie.start()
        else:
            self.empty_gif.setVisible(False)

        empty_layout.addWidget(self.empty_gif)

        empty_text = QLabel("История пуста")
        empty_text.setObjectName("muted")
        empty_text.setAlignment(Qt.AlignCenter)
        empty_text.setStyleSheet("font-size:15px;")
        empty_layout.addWidget(empty_text)

        hint = QLabel("Открой любой тайтл — он появится здесь.")
        hint.setObjectName("muted")
        hint.setAlignment(Qt.AlignCenter)
        empty_layout.addWidget(hint)

        layout.addWidget(self.empty_box, 1)
        layout.addStretch()

    # =========================================================
    # KEYBOARD
    # =========================================================

    def eventFilter(self, obj, event):
        if obj is self.list and event.type() == QEvent.KeyPress:
            key = event.key()
            mods = event.modifiers()

            if key == Qt.Key_A and (mods & Qt.ControlModifier):
                self.list.selectAll()
                return True

            if key == Qt.Key_Delete:
                self._remove_selected()
                return True

        return super().eventFilter(obj, event)

    # =========================================================
    # REFRESH
    # =========================================================

    def refresh(self):
        self.list.clear()
        items = load_history()
        has_items = bool(items)

        self.list.setVisible(has_items)
        self.empty_box.setVisible(not has_items)

        for entry in items:
            label = entry.get("title") or "Без названия"

            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, entry.get("url") or "")
            item.setData(Qt.UserRole + 1, entry)

            cover_path = entry.get("cover_path") or ""
            if cover_path and Path(cover_path).exists():
                pixmap = QPixmap(cover_path)
                if not pixmap.isNull():
                    item.setIcon(QIcon(pixmap))

            tip_parts = [label]
            if entry.get("author"):
                tip_parts.append(f"Автор: {entry['author']}")
            if entry.get("status"):
                tip_parts.append(f"Статус: {entry['status']}")
            if entry.get("chapters_count"):
                tip_parts.append(f"Глав: {entry['chapters_count']}")
            item.setToolTip("\n".join(tip_parts))

            self.list.addItem(item)

        self._update_sel_label()

    def _update_sel_label(self):
        count = len(self.list.selectedItems())
        self.sel_label.setText(f"Выбрано: {count}" if count else "")

    # =========================================================
    # OPEN
    # =========================================================

    def _on_item_open(self, item):
        url = item.data(Qt.UserRole)
        if not url:
            return
        self.open_manga.emit(url, item.text())

    # =========================================================
    # CONTEXT MENU
    # =========================================================

    def _context_menu(self, pos):
        item = self.list.itemAt(pos)

        if item is not None:
            if not item.isSelected():
                item.setSelected(True)

        menu = QMenu(self)

        if item is not None:
            url = item.data(Qt.UserRole)
            title = item.text()

            open_action = QAction("Открыть", self)
            open_action.triggered.connect(lambda: self.open_manga.emit(url, title))
            menu.addAction(open_action)

            menu.addSeparator()

        select_all_action = QAction("Выбрать все", self)
        select_all_action.triggered.connect(self.list.selectAll)
        menu.addAction(select_all_action)

        clear_sel_action = QAction("Снять выделение", self)
        clear_sel_action.triggered.connect(self.list.clearSelection)
        menu.addAction(clear_sel_action)

        menu.addSeparator()

        count = len(self.list.selectedItems())
        if count == 0 and item is not None:
            count = 1

        settings = load_settings()
        delete_with_chapters = bool(settings.get("delete_chapters_with_history"))

        if delete_with_chapters:
            remove_label = f"Удалить из истории и главы ({count})"
        else:
            remove_label = f"Удалить из истории ({count})"

        remove_action = QAction(remove_label, self)
        remove_action.triggered.connect(self._remove_selected)
        menu.addAction(remove_action)

        menu.exec(self.list.mapToGlobal(pos))

    # =========================================================
    # REMOVE
    # =========================================================

    def _remove_selected(self):
        selected = self.list.selectedItems()
        if not selected:
            return

        settings = load_settings()
        delete_chapters = bool(settings.get("delete_chapters_with_history"))

        titles_to_delete = []
        urls = []

        for item in selected:
            entry = item.data(Qt.UserRole + 1) or {}
            urls.append(entry.get("url") or "")
            titles_to_delete.append(entry.get("title") or "")

        if delete_chapters:
            answer = QMessageBox.question(
                self,
                "Удаление",
                f"Удалить {len(urls)} тайтл(ов) из истории и удалить скачанные главы?",
            )
        else:
            answer = QMessageBox.question(
                self,
                "Удаление",
                f"Удалить {len(urls)} тайтл(ов) из истории?",
            )

        if answer != QMessageBox.Yes:
            return

        for url in urls:
            if url:
                remove_from_history(url)

        if delete_chapters:
            download_dir = settings.get("download_dir", "downloads")
            for title in titles_to_delete:
                if title and delete_manga_folder(title, download_dir):
                    app_logger.write(f"Удалена папка глав: {title}")

        self.refresh()

    def clear_all(self):
        items = load_history()
        if not items:
            return

        settings = load_settings()
        delete_chapters = bool(settings.get("delete_chapters_with_history"))

        if delete_chapters:
            answer = QMessageBox.question(
                self,
                "Очистить историю",
                "Удалить ВСЕ записи и все скачанные главы?",
            )
        else:
            answer = QMessageBox.question(
                self,
                "Очистить историю",
                "Удалить все записи из истории?",
            )

        if answer != QMessageBox.Yes:
            return

        if delete_chapters:
            download_dir = settings.get("download_dir", "downloads")
            for entry in items:
                title = entry.get("title") or ""
                if title and delete_manga_folder(title, download_dir):
                    app_logger.write(f"Удалена папка глав: {title}")

        clear_history()
        self.refresh()
