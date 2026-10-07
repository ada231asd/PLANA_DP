from pathlib import Path

from PySide6.QtCore import Qt, QThread, QSize, Signal
from PySide6.QtGui import QPixmap, QMovie
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from config import GIF_DOWNLOAD, TRANSLATE_ENABLED
from logger import app_logger
from storage import (
    get_cached_manga,
    save_cached_manga,
    invalidate_manga_cache,
    manga_from_cache_dict,
    load_settings,
)

from workers.search_worker import SearchWorker
from workers.manga_worker import MangaWorker
from workers.download_worker import DownloadWorker
from workers.translate_worker import TranslateWorker


class SearchPage(QWidget):
    manga_loaded = Signal(object, bytes)

    loading_started = Signal(str)
    loading_finished = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self.current_manga = None
        self._history_emitted = False
        self._loading_active = False

        # перевод
        self._translated = False
        self._original_snapshot = {}
        self._translate_thread = None
        self._translate_worker = None

        self.search_thread = None
        self.search_worker = None
        self.manga_thread = None
        self.manga_worker = None
        self.download_thread = None
        self.download_worker = None

        self._build_ui()

    # =========================================================
    # OVERLAY HELPERS
    # =========================================================

    def _show_loading(self, text):
        if self._loading_active:
            return
        self._loading_active = True
        self.loading_started.emit(text)

    def _hide_loading(self):
        if not self._loading_active:
            return
        self._loading_active = False
        self.loading_finished.emit()

    # =========================================================
    # UI
    # =========================================================

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 20)
        layout.setSpacing(16)

        header = QHBoxLayout()
        title = QLabel("Поиск манги")
        title.setObjectName("title")
        header.addWidget(title)
        header.addStretch()
        layout.addLayout(header)

        # ---------- Search row ----------
        search_row = QHBoxLayout()
        search_row.setSpacing(8)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Введите название манги...")
        self.search_edit.setClearButtonEnabled(False)
        self.search_edit.returnPressed.connect(self.search)
        search_row.addWidget(self.search_edit, 1)

        self.clear_search_btn = QPushButton("✕")
        self.clear_search_btn.setToolTip("Очистить поиск и текущий тайтл")
        self.clear_search_btn.setFixedWidth(40)
        self.clear_search_btn.setMinimumHeight(34)
        self.clear_search_btn.setCursor(Qt.PointingHandCursor)
        self.clear_search_btn.clicked.connect(self.clear_search)
        search_row.addWidget(self.clear_search_btn)

        self.search_button = QPushButton("Найти")
        self.search_button.setObjectName("primary")
        self.search_button.setMinimumHeight(34)
        self.search_button.clicked.connect(self.search)
        search_row.addWidget(self.search_button)

        # Кнопка перевода — только если включена в config
        self.translate_button = QPushButton("🌐  Перевести")
        self.translate_button.setMinimumHeight(34)
        self.translate_button.setCursor(Qt.PointingHandCursor)
        self.translate_button.clicked.connect(self.toggle_translate)
        self.translate_button.setEnabled(False)

        if TRANSLATE_ENABLED:
            search_row.addWidget(self.translate_button)

        layout.addLayout(search_row)

        # ---------- Info card ----------
        info_card = QFrame()
        info_card.setObjectName("card")

        info_layout = QHBoxLayout(info_card)
        info_layout.setContentsMargins(18, 18, 18, 18)
        info_layout.setSpacing(18)

        self.cover = QLabel("Обложка")
        self.cover.setAlignment(Qt.AlignCenter)
        self.cover.setFixedSize(180, 255)
        self.cover.setStyleSheet(
            "background:#191b26;border-radius:10px;color:#555970;"
            "font-size:12px;letter-spacing:1px;"
        )
        info_layout.addWidget(self.cover)

        details = QVBoxLayout()
        details.setSpacing(8)

        self.manga_title = QLabel("Начните поиск")
        self.manga_title.setObjectName("title")
        self.manga_title.setWordWrap(True)
        details.addWidget(self.manga_title)

        self.meta = QLabel("")
        self.meta.setObjectName("muted")
        self.meta.setWordWrap(True)
        details.addWidget(self.meta)

        self.description = QTextEdit()
        self.description.setReadOnly(True)
        self.description.setMinimumHeight(120)
        details.addWidget(self.description, 1)

        info_layout.addLayout(details, 1)
        layout.addWidget(info_card, 2)

        # ---------- Bottom ----------
        bottom = QHBoxLayout()
        bottom.setSpacing(16)

        # Chapters
        chapter_card = QFrame()
        chapter_card.setObjectName("card")

        ch_layout = QVBoxLayout(chapter_card)
        ch_layout.setContentsMargins(14, 14, 14, 14)
        ch_layout.setSpacing(10)

        ch_header = QHBoxLayout()
        ch_title = QLabel("ГЛАВЫ")
        ch_title.setObjectName("section")
        ch_header.addWidget(ch_title)
        ch_header.addStretch()

        self.select_all_button = QPushButton("Выбрать все")
        self.select_all_button.setMinimumHeight(34)
        self.select_all_button.setCursor(Qt.PointingHandCursor)
        self.select_all_button.clicked.connect(self.select_all)
        ch_header.addWidget(self.select_all_button)

        self.clear_button = QPushButton("Снять все")
        self.clear_button.setMinimumHeight(34)
        self.clear_button.setCursor(Qt.PointingHandCursor)
        self.clear_button.clicked.connect(self.clear_all)
        ch_header.addWidget(self.clear_button)

        ch_layout.addLayout(ch_header)

        self.chapters = QListWidget()
        self.chapters.setSelectionMode(QAbstractItemView.NoSelection)
        ch_layout.addWidget(self.chapters)

        bottom.addWidget(chapter_card, 3)

        # Download
        dl_card = QFrame()
        dl_card.setObjectName("card")

        dl_layout = QVBoxLayout(dl_card)
        dl_layout.setContentsMargins(14, 14, 14, 14)
        dl_layout.setSpacing(10)

        dl_title = QLabel("ЗАГРУЗКА")
        dl_title.setObjectName("section")
        dl_layout.addWidget(dl_title)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        dl_layout.addWidget(self.progress)

        self.progress_text = QLabel("Ожидание")
        self.progress_text.setObjectName("muted")
        self.progress_text.setWordWrap(True)
        dl_layout.addWidget(self.progress_text)

        dl_layout.addStretch()

        self.download_gif = QLabel()
        self.download_gif.setAlignment(Qt.AlignCenter)
        self.download_gif.setVisible(False)
        self.download_gif.setFixedHeight(140)

        if Path(GIF_DOWNLOAD).exists():
            self._gif_movie = QMovie(str(GIF_DOWNLOAD))
            self._gif_movie.setScaledSize(QSize(130, 130))
            self.download_gif.setMovie(self._gif_movie)
        else:
            self._gif_movie = None
            app_logger.write(f"[WARN] GIF не найден: {GIF_DOWNLOAD}")

        dl_layout.addWidget(self.download_gif)

        self.download_button = QPushButton("Скачать выбранные")
        self.download_button.setObjectName("primary")
        self.download_button.setMinimumHeight(36)
        self.download_button.setCursor(Qt.PointingHandCursor)
        self.download_button.clicked.connect(self.download_selected)
        self.download_button.setEnabled(False)
        dl_layout.addWidget(self.download_button)

        bottom.addWidget(dl_card, 2)

        layout.addLayout(bottom, 2)

    # =========================================================
    # SEARCH / CLEAR
    # =========================================================

    def search(self):
        query = self.search_edit.text().strip()
        if not query:
            return
        self.open_query(query)

    def clear_search(self):
        if self.search_thread is not None and self.search_thread.isRunning():
            return
        if self.manga_thread is not None and self.manga_thread.isRunning():
            return

        self.current_manga = None
        self._history_emitted = False
        self._reset_translate_state()

        self.search_edit.clear()
        self.manga_title.setText("Начните поиск")
        self.meta.setText("")
        self.description.clear()
        self.chapters.clear()
        self.cover.clear()
        self.cover.setText("Обложка")
        self.download_button.setEnabled(False)
        self.translate_button.setEnabled(False)
        self.progress.setValue(0)
        self.progress_text.setText("Ожидание")

        app_logger.write("Поиск очищен.")

    def open_query(self, query):
        if self.search_thread is not None and self.search_thread.isRunning():
            app_logger.write("Предыдущий поиск ещё выполняется...")
            return

        self.current_manga = None
        self._history_emitted = False
        self._reset_translate_state()
        self._reset_display()

        self.search_button.setEnabled(False)
        self.translate_button.setEnabled(False)
        app_logger.write(f"Поиск: {query}")

        self._show_loading("Поиск тайтла")

        self.search_thread = QThread()
        self.search_worker = SearchWorker(query, enrich=False)
        self.search_worker.moveToThread(self.search_thread)

        self.search_thread.started.connect(self.search_worker.run)

        self.search_worker.results.connect(self.show_search_results)
        self.search_worker.log.connect(app_logger.write)
        self.search_worker.error.connect(self._on_search_error)

        self.search_worker.finished.connect(self.search_thread.quit)
        self.search_worker.finished.connect(self.search_worker.deleteLater)
        self.search_thread.finished.connect(self.search_thread.deleteLater)
        self.search_thread.finished.connect(self._search_thread_done)

        self.search_thread.start()

    def _search_thread_done(self):
        self.search_thread = None
        self.search_worker = None
        self.search_button.setEnabled(True)

        if not self.current_manga:
            self._hide_loading()

    def show_search_results(self, results):
        if not results:
            app_logger.write("Ничего не найдено.")
            self.manga_title.setText("Ничего не найдено")
            self._hide_loading()
            return

        first = results[0]
        url = first.get("url") or ""
        app_logger.write(
            f"Найдено результатов: {len(results)}. Первый: "
            f"{first.get('title') or 'без названия'}"
        )

        if url:
            self.open_url(url)
        else:
            self._hide_loading()

    def _on_search_error(self, message):
        app_logger.write(f"[ERROR] {message}")
        self._hide_loading()
        QMessageBox.critical(self, "Ошибка поиска", message)

    # =========================================================
    # OPEN URL
    # =========================================================

    def open_url(self, url, force_refresh=False):
        if not url:
            return

        if self.manga_thread is not None and self.manga_thread.isRunning():
            app_logger.write("Предыдущая загрузка тайтла ещё идёт...")
            return

        self._show_loading("Загрузка тайтла")

        settings = load_settings()

        # КЕШ
        if settings.get("use_cache", True) and not force_refresh:
            cached = get_cached_manga(url)
            if cached:
                self.current_manga = manga_from_cache_dict(cached)
                self._history_emitted = False
                self._reset_translate_state()

                app_logger.write(
                    f"Тайтл из кеша: {self.current_manga.title} "
                    f"(обновлён: {cached.get('cached_at', '?')})"
                )

                self.show_manga(self.current_manga)

                cover_path = cached.get("_cover_path") or ""
                if cover_path and Path(cover_path).exists():
                    try:
                        data = Path(cover_path).read_bytes()
                        pixmap = QPixmap()
                        if pixmap.loadFromData(data):
                            self.cover.setPixmap(
                                pixmap.scaled(
                                    self.cover.size(),
                                    Qt.KeepAspectRatio,
                                    Qt.SmoothTransformation,
                                )
                            )
                        if not self._history_emitted:
                            self._history_emitted = True
                            self.manga_loaded.emit(self.current_manga, data)
                    except Exception as exc:
                        app_logger.write(
                            f"[WARN] не удалось прочитать кеш обложки: {exc}"
                        )
                        if not self._history_emitted:
                            self._history_emitted = True
                            self.manga_loaded.emit(self.current_manga, b"")
                else:
                    if not self._history_emitted:
                        self._history_emitted = True
                        self.manga_loaded.emit(self.current_manga, b"")

                self._hide_loading()
                return

        # СЕТЬ
        self.current_manga = None
        self._history_emitted = False
        self._reset_translate_state()
        self._reset_display()
        self.manga_title.setText("Загрузка...")

        app_logger.write(f"Открываю тайтл (сеть): {url}")

        self.manga_thread = QThread()
        self.manga_worker = MangaWorker(url)
        self.manga_worker.moveToThread(self.manga_thread)

        self.manga_thread.started.connect(self.manga_worker.run)

        self.manga_worker.result.connect(self.show_manga)
        self.manga_worker.cover.connect(self._on_cover_received)
        self.manga_worker.log.connect(app_logger.write)
        self.manga_worker.error.connect(self._on_manga_error)

        self.manga_worker.finished.connect(self.manga_thread.quit)
        self.manga_worker.finished.connect(self.manga_worker.deleteLater)
        self.manga_thread.finished.connect(self.manga_thread.deleteLater)
        self.manga_thread.finished.connect(self._manga_thread_done)

        self.manga_thread.start()

    def _manga_thread_done(self):
        self.manga_thread = None
        self.manga_worker = None

        if self.current_manga is not None:
            try:
                save_cached_manga(self.current_manga, None)
            except Exception:
                pass

            if not self._history_emitted:
                self._history_emitted = True
                self.manga_loaded.emit(self.current_manga, b"")

        self._hide_loading()

    def _on_cover_received(self, data, from_cache=False):
        pixmap = QPixmap()
        if pixmap.loadFromData(data):
            self.cover.setPixmap(
                pixmap.scaled(
                    self.cover.size(),
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation,
                )
            )

        if from_cache:
            return

        if self.current_manga is not None:
            try:
                save_cached_manga(self.current_manga, data or None)
            except Exception:
                pass

            if not self._history_emitted:
                self._history_emitted = True
                self.manga_loaded.emit(self.current_manga, data)

    def _on_manga_error(self, message):
        app_logger.write(f"[ERROR] {message}")
        self._hide_loading()
        QMessageBox.critical(self, "Ошибка", message)

    # =========================================================
    # SHOW MANGA
    # =========================================================

    def show_manga(self, manga):
        self.current_manga = manga
        self.manga_title.setText(manga.title)

        parts = []
        if manga.author:
            parts.append(f"Автор: {manga.author}")
        if manga.status:
            parts.append(f"Статус: {manga.status}")
        if manga.views:
            parts.append(f"Просмотры: {manga.views}")
        if manga.bookmarks:
            parts.append(f"Закладки: {manga.bookmarks}")
        if manga.genres:
            parts.append("Жанры: " + ", ".join(manga.genres))
        if manga.alternative_title:
            parts.append("Альтернативное: " + manga.alternative_title)

        self.meta.setText("\n".join(parts))
        self.description.setPlainText(manga.description or "Описание отсутствует.")

        self.chapters.clear()
        for chapter in manga.chapters:
            item = QListWidgetItem(f"Глава {chapter.number}")
            item.setData(Qt.UserRole, chapter)
            item.setCheckState(Qt.Unchecked)
            if chapter.updated:
                item.setToolTip(chapter.updated)
            self.chapters.addItem(item)

        self.download_button.setEnabled(bool(manga.chapters))
        if TRANSLATE_ENABLED:
            self.translate_button.setEnabled(True)
        app_logger.write(f"Загружено глав: {len(manga.chapters)}")

    # =========================================================
    # TRANSLATE
    # =========================================================

    def toggle_translate(self):
        if not TRANSLATE_ENABLED:
            return
        if not self.current_manga:
            return

        if self._translated:
            self._restore_original()
            return

        if self._translate_thread is not None and self._translate_thread.isRunning():
            return

        manga = self.current_manga

        fields = {
            "title": manga.title or "",
            "alternative_title": manga.alternative_title or "",
            "author": manga.author or "",
            "status": manga.status or "",
            "genres": list(manga.genres or []),
            "description": manga.description or "",
        }

        self._original_snapshot = {
            "title": self.manga_title.text(),
            "meta": self.meta.text(),
            "description": self.description.toPlainText(),
        }

        self.translate_button.setEnabled(False)
        self.translate_button.setText("🌐  Перевод...")
        self._show_loading("Перевод")

        self._translate_thread = QThread()
        self._translate_worker = TranslateWorker(fields)
        self._translate_worker.moveToThread(self._translate_thread)

        self._translate_thread.started.connect(self._translate_worker.run)

        self._translate_worker.result.connect(self._on_translate_done)
        self._translate_worker.error.connect(self._on_translate_error)
        self._translate_worker.log.connect(app_logger.write)

        self._translate_worker.finished.connect(self._translate_thread.quit)
        self._translate_worker.finished.connect(self._translate_worker.deleteLater)
        self._translate_thread.finished.connect(self._translate_thread.deleteLater)
        self._translate_thread.finished.connect(self._translate_thread_done)

        self._translate_thread.start()

    def _translate_thread_done(self):
        self._translate_thread = None
        self._translate_worker = None
        self._hide_loading()
        self.translate_button.setEnabled(bool(self.current_manga))
        if not self._translated:
            self.translate_button.setText("🌐  Перевести")

    def _on_translate_done(self, translated):
        try:
            title = translated.get("title") or self.current_manga.title

            parts = []
            if translated.get("author"):
                parts.append(f"Автор: {translated['author']}")
            if translated.get("status"):
                parts.append(f"Статус: {translated['status']}")
            if self.current_manga.views:
                parts.append(f"Просмотры: {self.current_manga.views}")
            if self.current_manga.bookmarks:
                parts.append(f"Закладки: {self.current_manga.bookmarks}")
            if translated.get("genres"):
                parts.append("Жанры: " + ", ".join(translated["genres"]))
            if translated.get("alternative_title"):
                parts.append("Альтернативное: " + translated["alternative_title"])

            self.manga_title.setText(title)
            self.meta.setText("\n".join(parts))
            self.description.setPlainText(
                translated.get("description")
                or self.current_manga.description
                or "Описание отсутствует."
            )

            self._translated = True
            self.translate_button.setText("🌐  Оригинал")
            app_logger.write("Перевод готов.")
        except Exception as exc:
            app_logger.write(f"[WARN] применение перевода: {exc}")

    def _on_translate_error(self, message):
        app_logger.write(f"[ERROR] перевод: {message}")
        self._translated = False
        self.translate_button.setText("🌐  Перевести")
        QMessageBox.warning(self, "Перевод", message)

    def _restore_original(self):
        if not self._original_snapshot:
            return
        self.manga_title.setText(self._original_snapshot.get("title", ""))
        self.meta.setText(self._original_snapshot.get("meta", ""))
        self.description.setPlainText(self._original_snapshot.get("description", ""))
        self._translated = False
        self.translate_button.setText("🌐  Перевести")

    def _reset_translate_state(self):
        self._translated = False
        self._original_snapshot = {}
        self.translate_button.setText("🌐  Перевести")
        self.translate_button.setEnabled(False)

    # =========================================================
    # RESET / SELECT / CLEAR
    # =========================================================

    def _reset_display(self):
        self.cover.clear()
        self.cover.setText("Обложка")
        self.manga_title.setText("Загрузка...")
        self.meta.setText("")
        self.description.clear()
        self.chapters.clear()
        self.download_button.setEnabled(False)

    def select_all(self):
        for i in range(self.chapters.count()):
            self.chapters.item(i).setCheckState(Qt.Checked)

    def clear_all(self):
        for i in range(self.chapters.count()):
            self.chapters.item(i).setCheckState(Qt.Unchecked)

    # =========================================================
    # DOWNLOAD
    # =========================================================

    def download_selected(self):
        if not self.current_manga:
            return

        selected = []
        for i in range(self.chapters.count()):
            item = self.chapters.item(i)
            if item.checkState() == Qt.Checked:
                selected.append(item.data(Qt.UserRole))

        if not selected:
            QMessageBox.information(self, "Главы", "Выберите хотя бы одну главу.")
            return

        if self.download_thread is not None and self.download_thread.isRunning():
            app_logger.write("Загрузка уже идёт.")
            return

        self.download_button.setEnabled(False)
        self.search_button.setEnabled(False)
        self.progress.setValue(0)
        app_logger.write(f"Начинаю загрузку: {len(selected)} глав.")

        self._set_download_gif(True)

        self.download_thread = QThread()
        self.download_worker = DownloadWorker(self.current_manga.title, selected)
        self.download_worker.moveToThread(self.download_thread)

        self.download_thread.started.connect(self.download_worker.run)

        self.download_worker.progress.connect(self.download_progress)
        self.download_worker.chapter_started.connect(
            lambda name: app_logger.write(f"--- {name} ---")
        )
        self.download_worker.log.connect(app_logger.write)
        self.download_worker.error.connect(self._on_download_error)

        self.download_worker.finished.connect(self.download_thread.quit)
        self.download_worker.finished.connect(self.download_worker.deleteLater)
        self.download_thread.finished.connect(self.download_thread.deleteLater)
        self.download_thread.finished.connect(self.download_finished)

        self.download_thread.start()

    def download_progress(self, completed_chapters, total_chapters, text):
        if total_chapters:
            value = int((completed_chapters / total_chapters) * 100)
            self.progress.setValue(max(0, min(100, value)))
        self.progress_text.setText(text)

    def download_finished(self):
        self.progress.setValue(100)
        self.progress_text.setText("Загрузка завершена")
        app_logger.write("Готово.")
        self.download_button.setEnabled(True)
        self.search_button.setEnabled(True)
        self.download_thread = None
        self.download_worker = None
        self._set_download_gif(False)

    def _set_download_gif(self, active):
        if self._gif_movie is None:
            return
        if active:
            self.download_gif.setVisible(True)
            self._gif_movie.start()
        else:
            self._gif_movie.stop()
            self.download_gif.setVisible(False)

    def _on_download_error(self, message):
        app_logger.write(f"[ERROR] {message}")

        if self.current_manga is not None:
            try:
                invalidate_manga_cache(self.current_manga.url)
                app_logger.write(f"Кеш тайтла сброшен: {self.current_manga.url}")
            except Exception:
                pass

        QMessageBox.critical(self, "Ошибка", message)

    # =========================================================
    # SHUTDOWN
    # =========================================================

    def shutdown(self):
        if self.download_worker is not None:
            try:
                self.download_worker.stop()
            except Exception:
                pass

        for thread in (
            self.download_thread,
            self.manga_thread,
            self.search_thread,
            self._translate_thread,
        ):
            if thread is not None:
                try:
                    if thread.isRunning():
                        thread.quit()
                        thread.wait(5000)
                except Exception:
                    pass
