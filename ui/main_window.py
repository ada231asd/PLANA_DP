from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from config import APP_NAME, APP_VERSION, LOGO_JPG
from logger import app_logger

from ui.overlay import LoadingOverlay
from ui.pages.search_page import SearchPage
from ui.pages.history_page import HistoryPage
from ui.pages.settings_page import SettingsPage


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle(f"{APP_NAME} {APP_VERSION}")
        self.resize(1280, 840)
        self.setMinimumSize(1100, 720)

        if LOGO_JPG.exists():
            self.setWindowIcon(QIcon(str(LOGO_JPG)))

        self._build_ui()

        self.overlay = LoadingOverlay(self.centralWidget())
        self.overlay.setGeometry(self.centralWidget().rect())

        self.search_page.loading_started.connect(self.overlay.show_overlay)
        self.search_page.loading_finished.connect(self.overlay.hide_overlay)
        self.history_page.open_manga.connect(self._open_manga_from_history)

        app_logger.message.connect(self._on_log_line)
        app_logger.write("Приложение запущено.")

    # =========================================================
    # UI
    # =========================================================

    def _build_ui(self):
        central = QWidget()
        central.setObjectName("root")
        self.setCentralWidget(central)

        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ---- SIDEBAR ----
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(230)

        side = QVBoxLayout(sidebar)
        side.setContentsMargins(20, 26, 20, 20)
        side.setSpacing(6)

        # Логотип
        logo_row = QHBoxLayout()
        logo_row.setSpacing(12)
        logo_row.setContentsMargins(0, 0, 0, 0)

        logo_img = QLabel()
        logo_img.setFixedSize(40, 40)
        logo_img.setStyleSheet("background:transparent;")
        if LOGO_JPG.exists():
            pix = QPixmap(str(LOGO_JPG))
            if not pix.isNull():
                logo_img.setPixmap(
                    pix.scaled(
                        40,
                        40,
                        Qt.KeepAspectRatio,
                        Qt.SmoothTransformation,
                    )
                )
        logo_row.addWidget(logo_img)

        text_col = QVBoxLayout()
        text_col.setSpacing(0)
        text_col.setContentsMargins(0, 0, 0, 0)

        logo_text = QLabel("PLANA_DP")
        logo_text.setObjectName("logo")
        text_col.addWidget(logo_text)

        sub = QLabel("MANGA DOWNLOADER")
        sub.setObjectName("sublogo")
        text_col.addWidget(sub)

        logo_row.addLayout(text_col)
        logo_row.addStretch()

        side.addLayout(logo_row)

        side.addSpacing(30)

        nav_label = QLabel("НАВИГАЦИЯ")
        nav_label.setObjectName("section")
        side.addWidget(nav_label)
        side.addSpacing(6)

        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)

        self.btn_search = self._nav_button("🔍   Поиск")
        self.btn_history = self._nav_button("📚   История")
        self.btn_settings = self._nav_button("⚙   Настройки")

        self.nav_group.addButton(self.btn_search, 0)
        self.nav_group.addButton(self.btn_history, 1)
        self.nav_group.addButton(self.btn_settings, 2)

        side.addWidget(self.btn_search)
        side.addWidget(self.btn_history)
        side.addWidget(self.btn_settings)

        side.addStretch()

        version = QLabel(f"v{APP_VERSION}")
        version.setObjectName("muted")
        side.addWidget(version)

        root.addWidget(sidebar)

        # ---- PAGES ----
        self.stack = QStackedWidget()
        root.addWidget(self.stack, 1)

        self.search_page = SearchPage()
        self.history_page = HistoryPage()
        self.settings_page = SettingsPage()

        self.stack.addWidget(self.search_page)
        self.stack.addWidget(self.history_page)
        self.stack.addWidget(self.settings_page)

        self.nav_group.idClicked.connect(self._on_nav_clicked)
        self.btn_search.setChecked(True)

        self.search_page.manga_loaded.connect(self._on_manga_loaded)
        self.settings_page.settings_saved.connect(self._on_settings_saved)

        self.statusBar().showMessage("Готов к работе")

    def _nav_button(self, text):
        btn = QPushButton(text)
        btn.setObjectName("nav")
        btn.setCheckable(True)
        btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        btn.setCursor(Qt.PointingHandCursor)
        return btn

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "overlay"):
            self.overlay.setGeometry(self.centralWidget().rect())

    # =========================================================
    # SLOTS
    # =========================================================

    def _on_nav_clicked(self, index):
        self.stack.setCurrentIndex(index)
        if index == 1:
            self.history_page.refresh()

    def _on_manga_loaded(self, manga, cover_bytes):
        from storage import add_to_history

        try:
            add_to_history(manga, cover_bytes)
        except Exception as exc:
            app_logger.write(f"[WARN] история: {exc}")
        self.history_page.refresh()

    def _open_manga_from_history(self, url, title):
        self.stack.setCurrentIndex(0)
        self.btn_search.setChecked(True)
        app_logger.write(f"Открываю из истории: {title or url}")
        self.search_page.open_url(url)

    def _on_settings_saved(self):
        self.statusBar().showMessage("Настройки сохранены")

    def _on_log_line(self, line):
        short = line if len(line) <= 120 else line[:117] + "..."
        self.statusBar().showMessage(short)

    # =========================================================
    # CLOSE
    # =========================================================

    def closeEvent(self, event):
        try:
            self.search_page.shutdown()
        except Exception:
            pass
        event.accept()
