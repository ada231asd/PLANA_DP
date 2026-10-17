from pathlib import Path

from PySide6.QtCore import Qt, QUrl, QThread, Signal, Slot
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from config import APP_VERSION, GITHUB_REPO, GITHUB_CHECK_ENABLED
from logger import app_logger
from storage import (
    load_settings,
    save_settings,
    get_default_settings,
    wipe_app_data,
    clear_history,
)
from paths import (
    get_data_dir,
    default_data_dir,
    is_in_user_config,
    migrate_data_dir_to_default,
)

from workers.update_worker import UpdateWorker, ApplyUpdateWorker
from workers.uninstall_worker import UninstallWorker


FIELD_HEIGHT = 34
ROW_MIN_HEIGHT = 40


class SettingsPage(QWidget):
    settings_saved = Signal()
    logs_visibility_changed = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)

        self._update_thread = None
        self._update_worker = None
        self._dl_thread = None
        self._dl_worker = None
        self._update_progress = None
        self._uninstall_thread = None
        self._uninstall_worker = None

        self._build_ui()
        self.load()

    # =========================================================
    # HELPERS
    # =========================================================

    def _lbl(self, text):
        l = QLabel(text)
        l.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        l.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        l.setContentsMargins(0, 0, 8, 0)
        return l

    def _btn(self, text, min_w=100):
        b = QPushButton(text)
        b.setMinimumHeight(FIELD_HEIGHT)
        b.setMinimumWidth(min_w)
        b.setCursor(Qt.PointingHandCursor)
        return b

    def _field_h(self, widget):
        widget.setMinimumHeight(FIELD_HEIGHT)
        return widget

    # =========================================================
    # UI
    # =========================================================

    def _build_ui(self):
        # корневой layout: только scroll на всю страницу
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        content = QWidget()
        scroll.setWidget(content)

        outer.addWidget(scroll)

        # ---- содержимое страницы ----
        layout = QVBoxLayout(content)
        layout.setContentsMargins(28, 24, 28, 20)
        layout.setSpacing(16)

        title = QLabel("Настройки")
        title.setObjectName("title")
        layout.addWidget(title)

        # ================= ОСНОВНЫЕ =================
        card = QFrame()
        card.setObjectName("card")

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(28, 24, 28, 24)
        card_layout.setSpacing(0)

        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(12)
        grid.setColumnStretch(0, 0)
        grid.setColumnStretch(1, 1)
        grid.setContentsMargins(0, 0, 0, 0)

        row = 0

        def set_row_min(r):
            grid.setRowMinimumHeight(r, ROW_MIN_HEIGHT)

        # ---- Папка загрузок ----
        grid.addWidget(self._lbl("Папка загрузок"), row, 0)

        dir_row = QHBoxLayout()
        dir_row.setContentsMargins(0, 0, 0, 0)
        dir_row.setSpacing(8)

        self.download_dir = self._field_h(QLineEdit())
        dir_row.addWidget(self.download_dir, 1)

        browse = self._btn("Обзор...", min_w=110)
        browse.clicked.connect(self._pick_dir)
        dir_row.addWidget(browse)

        open_dir = self._btn("Открыть", min_w=110)
        open_dir.clicked.connect(self._open_dir)
        dir_row.addWidget(open_dir)

        dir_widget = QWidget()
        dir_widget.setLayout(dir_row)
        dir_widget.setMinimumHeight(FIELD_HEIGHT)
        grid.addWidget(dir_widget, row, 1)
        set_row_min(row)
        row += 1

        # ---- Браузер ----
        grid.addWidget(self._lbl("Браузер"), row, 0)
        self.browser = self._field_h(QComboBox())
        self.browser.addItems(["firefox", "chromium"])
        self.browser.setMinimumWidth(200)
        self.browser.setMaximumWidth(320)
        self.browser.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        grid.addWidget(self.browser, row, 1, Qt.AlignLeft)
        set_row_min(row)
        row += 1

        # ---- Чекбоксы ----
        self.headless = QCheckBox("Запускать браузер в фоне (headless)")
        self.headless.setMinimumHeight(ROW_MIN_HEIGHT)
        grid.addWidget(self.headless, row, 0, 1, 2)
        set_row_min(row)
        row += 1

        self.use_cache = QCheckBox(
            "Использовать кеш тайтлов (не перезагружать с сайта)"
        )
        self.use_cache.setMinimumHeight(ROW_MIN_HEIGHT)
        grid.addWidget(self.use_cache, row, 0, 1, 2)
        set_row_min(row)
        row += 1

        self.delete_chapters = QCheckBox("Удалять скачанные главы вместе с историей")
        self.delete_chapters.setMinimumHeight(ROW_MIN_HEIGHT)
        grid.addWidget(self.delete_chapters, row, 0, 1, 2)
        set_row_min(row)
        row += 1

        self.show_logs = QCheckBox("Показывать раздел логов в сайдбаре")
        self.show_logs.setMinimumHeight(ROW_MIN_HEIGHT)
        self.show_logs.stateChanged.connect(self._on_show_logs_changed)
        grid.addWidget(self.show_logs, row, 0, 1, 2)
        set_row_min(row)
        row += 1

        # ---- Числовые поля ----
        grid.addWidget(self._lbl("Повторов загрузки картинки"), row, 0)
        self.retries = self._field_h(QSpinBox())
        self.retries.setRange(1, 10)
        self.retries.setMinimumWidth(120)
        self.retries.setMaximumWidth(180)
        self.retries.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        grid.addWidget(self.retries, row, 1, Qt.AlignLeft)
        set_row_min(row)
        row += 1

        grid.addWidget(self._lbl("Таймаут навигации"), row, 0)
        self.nav_timeout = self._field_h(QSpinBox())
        self.nav_timeout.setRange(5000, 180000)
        self.nav_timeout.setSingleStep(1000)
        self.nav_timeout.setSuffix(" мс")
        self.nav_timeout.setMinimumWidth(140)
        self.nav_timeout.setMaximumWidth(200)
        self.nav_timeout.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        grid.addWidget(self.nav_timeout, row, 1, Qt.AlignLeft)
        set_row_min(row)
        row += 1

        grid.addWidget(self._lbl("Таймаут загрузки картинки"), row, 0)
        self.dl_timeout = self._field_h(QSpinBox())
        self.dl_timeout.setRange(5000, 300000)
        self.dl_timeout.setSingleStep(1000)
        self.dl_timeout.setSuffix(" мс")
        self.dl_timeout.setMinimumWidth(140)
        self.dl_timeout.setMaximumWidth(200)
        self.dl_timeout.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        grid.addWidget(self.dl_timeout, row, 1, Qt.AlignLeft)
        set_row_min(row)
        row += 1

        grid.addWidget(self._lbl("Лимит истории"), row, 0)
        self.history_limit = self._field_h(QSpinBox())
        self.history_limit.setRange(10, 2000)
        self.history_limit.setSingleStep(10)
        self.history_limit.setMinimumWidth(120)
        self.history_limit.setMaximumWidth(180)
        self.history_limit.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        grid.addWidget(self.history_limit, row, 1, Qt.AlignLeft)
        set_row_min(row)
        row += 1

        card_layout.addLayout(grid)
        card_layout.addSpacing(20)

        save_row = QHBoxLayout()
        save_row.addStretch()

        reset = self._btn("Сбросить настройки", min_w=200)
        reset.clicked.connect(self._reset_settings)
        save_row.addWidget(reset)

        save = self._btn("Сохранить", min_w=160)
        save.setObjectName("primary")
        save.clicked.connect(self.save)
        save_row.addWidget(save)

        card_layout.addLayout(save_row)

        layout.addWidget(card)

        # ================= РАСПОЛОЖЕНИЕ ДАННЫХ =================
        loc_card = QFrame()
        loc_card.setObjectName("card")

        ll = QVBoxLayout(loc_card)
        ll.setContentsMargins(24, 20, 24, 20)
        ll.setSpacing(12)

        loc_title = QLabel("РАСПОЛОЖЕНИЕ ДАННЫХ")
        loc_title.setObjectName("section")
        ll.addWidget(loc_title)

        self.loc_label = QLabel("")
        self.loc_label.setObjectName("muted")
        self.loc_label.setWordWrap(True)
        self.loc_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        ll.addWidget(self.loc_label)

        loc_row = QHBoxLayout()
        self.loc_move_btn = self._btn("Переместить в %APPDATA%/PLANA_DP", min_w=340)
        self.loc_move_btn.clicked.connect(self._move_data_dir)
        loc_row.addWidget(self.loc_move_btn)
        loc_row.addStretch()
        ll.addLayout(loc_row)

        layout.addWidget(loc_card)

        # ================= ОБНОВЛЕНИЯ =================
        upd_card = QFrame()
        upd_card.setObjectName("card")

        upd_layout = QVBoxLayout(upd_card)
        upd_layout.setContentsMargins(24, 20, 24, 20)
        upd_layout.setSpacing(12)

        upd_title = QLabel("ОБНОВЛЕНИЯ")
        upd_title.setObjectName("section")
        upd_layout.addWidget(upd_title)

        upd_hint = QLabel(f"Текущая версия: {APP_VERSION}\nРепозиторий: {GITHUB_REPO}")
        upd_hint.setObjectName("muted")
        upd_hint.setWordWrap(True)
        upd_layout.addWidget(upd_hint)

        upd_row = QHBoxLayout()
        upd_row.addStretch()

        self.check_updates_btn = self._btn("Проверить обновления", min_w=240)
        self.check_updates_btn.setObjectName("primary")
        self.check_updates_btn.clicked.connect(self._check_updates)
        self.check_updates_btn.setEnabled(bool(GITHUB_CHECK_ENABLED))
        upd_row.addWidget(self.check_updates_btn)

        upd_layout.addLayout(upd_row)

        layout.addWidget(upd_card)

        # ================= УПРАВЛЕНИЕ ДАННЫМИ =================
        danger_card = QFrame()
        danger_card.setObjectName("card")

        dl = QVBoxLayout(danger_card)
        dl.setContentsMargins(24, 20, 24, 20)
        dl.setSpacing(12)

        danger_title = QLabel("УПРАВЛЕНИЕ ДАННЫМИ")
        danger_title.setObjectName("section")
        dl.addWidget(danger_title)

        danger_hint = QLabel(
            "Очистка кеша и истории — удаляет только временные файлы.\n"
            "Деинсталлятор полностью удаляет приложение и данные."
        )
        danger_hint.setObjectName("muted")
        danger_hint.setWordWrap(True)
        dl.addWidget(danger_hint)

        row1 = QHBoxLayout()
        wipe_cache = self._btn("Очистить кеш и историю", min_w=260)
        wipe_cache.clicked.connect(self._wipe_cache)
        row1.addWidget(wipe_cache)
        row1.addStretch()
        dl.addLayout(row1)

        row2 = QHBoxLayout()

        self.un_dl_check = QCheckBox("Удалить папку загрузок")
        self.un_dl_check.setMinimumHeight(ROW_MIN_HEIGHT)
        row2.addWidget(self.un_dl_check)

        self.un_app_check = QCheckBox("Удалить папку приложения (если .exe)")
        self.un_app_check.setMinimumHeight(ROW_MIN_HEIGHT)
        self.un_app_check.setChecked(True)
        row2.addWidget(self.un_app_check)

        row2.addStretch()

        uninstall_btn = QPushButton("Удалить PLANA_DP")
        uninstall_btn.setMinimumHeight(FIELD_HEIGHT)
        uninstall_btn.setMinimumWidth(220)
        uninstall_btn.setCursor(Qt.PointingHandCursor)
        uninstall_btn.setStyleSheet(
            "background:#3a1a1a;border:1px solid #7a2e2e;color:#ffcccc;font-weight:700;"
        )
        uninstall_btn.clicked.connect(self._run_uninstaller)
        row2.addWidget(uninstall_btn)

        dl.addLayout(row2)

        layout.addWidget(danger_card)

        layout.addStretch()

        self._refresh_location()

    # =========================================================
    # SETTINGS
    # =========================================================

    def load(self):
        s = load_settings()
        self.download_dir.setText(s["download_dir"])
        self.browser.setCurrentText(s["browser"])
        self.headless.setChecked(bool(s["headless"]))
        self.use_cache.setChecked(bool(s.get("use_cache", True)))
        self.delete_chapters.setChecked(
            bool(s.get("delete_chapters_with_history", False))
        )
        self.show_logs.setChecked(bool(s.get("show_logs_section", False)))
        self.retries.setValue(int(s["image_retries"]))
        self.nav_timeout.setValue(int(s["navigation_timeout"]))
        self.dl_timeout.setValue(int(s["download_timeout"]))
        self.history_limit.setValue(int(s["history_limit"]))

    def save(self):
        s = load_settings()
        s["download_dir"] = self.download_dir.text().strip() or s["download_dir"]
        s["browser"] = self.browser.currentText()
        s["headless"] = self.headless.isChecked()
        s["use_cache"] = self.use_cache.isChecked()
        s["delete_chapters_with_history"] = self.delete_chapters.isChecked()
        s["show_logs_section"] = self.show_logs.isChecked()
        s["image_retries"] = int(self.retries.value())
        s["navigation_timeout"] = int(self.nav_timeout.value())
        s["download_timeout"] = int(self.dl_timeout.value())
        s["history_limit"] = int(self.history_limit.value())

        save_settings(s)
        self.settings_saved.emit()
        app_logger.write("Настройки сохранены.")
        QMessageBox.information(self, "Настройки", "Сохранено.")

    def _on_show_logs_changed(self, _state):
        self.logs_visibility_changed.emit(self.show_logs.isChecked())

    def _reset_settings(self):
        answer = QMessageBox.question(
            self,
            "Сброс настроек",
            "Сбросить настройки до значений по умолчанию?\n"
            "История и кеш не затрагиваются.",
        )
        if answer != QMessageBox.Yes:
            return
        save_settings(get_default_settings())
        self.load()
        self.settings_saved.emit()
        self.logs_visibility_changed.emit(self.show_logs.isChecked())
        app_logger.write("Настройки сброшены к умолчанию.")

    # =========================================================
    # LOCATION
    # =========================================================

    def _refresh_location(self):
        try:
            current = get_data_dir()
            target = default_data_dir()
        except Exception:
            self.loc_label.setText("Не удалось определить путь данных.")
            self.loc_move_btn.setVisible(False)
            return

        in_std = is_in_user_config(current)

        if in_std:
            self.loc_label.setText(
                f"Данные в стандартной папке:\n{current}\n\nПеремещение не требуется."
            )
            self.loc_move_btn.setVisible(False)
        else:
            self.loc_label.setText(
                f"Текущая папка данных:\n{current}\n\n"
                f"Стандартная папка:\n{target}\n\n"
                "Рекомендуется переместить данные в стандартную папку —\n"
                "это нужно для корректной работы обновлений и деинсталлятора."
            )
            self.loc_move_btn.setVisible(True)

    def _move_data_dir(self):
        answer = QMessageBox.question(
            self,
            "Перемещение данных",
            "Переместить данные приложения в стандартную папку?\n\n"
            "Приложение будет перезапущено.",
        )
        if answer != QMessageBox.Yes:
            return

        if not migrate_data_dir_to_default():
            QMessageBox.warning(
                self,
                "Ошибка",
                "Не удалось переместить данные.\nПроверьте права доступа к папкам.",
            )
            return

        QMessageBox.information(
            self,
            "Готово",
            "Данные перемещены. Приложение будет перезапущено.",
        )

        import sys
        from PySide6.QtCore import QProcess

        QProcess.startDetached(sys.executable, sys.argv)
        app = QApplication.instance()
        if app is not None:
            app.quit()

    # =========================================================
    # HELPERS
    # =========================================================

    def _pick_dir(self):
        d = QFileDialog.getExistingDirectory(self, "Выберите папку")
        if d:
            self.download_dir.setText(d)

    def _open_dir(self):
        path = self.download_dir.text().strip()
        if path:
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    # =========================================================
    # UPDATES — CHECK
    # =========================================================

    def _check_updates(self):
        if self._update_thread is not None and self._update_thread.isRunning():
            return

        self.check_updates_btn.setEnabled(False)
        self.check_updates_btn.setText("Проверяю...")

        self._update_thread = QThread()
        self._update_worker = UpdateWorker()
        self._update_worker.moveToThread(self._update_thread)

        self._update_thread.started.connect(self._update_worker.run)

        self._update_worker.result.connect(self._on_update_result)
        self._update_worker.error.connect(self._on_update_error)
        self._update_worker.log.connect(app_logger.write)

        self._update_worker.finished.connect(self._update_thread.quit)
        self._update_worker.finished.connect(self._update_worker.deleteLater)
        self._update_thread.finished.connect(self._update_thread.deleteLater)
        self._update_thread.finished.connect(self._update_thread_done)

        self._update_thread.start()

    def _update_thread_done(self):
        self._update_thread = None
        self._update_worker = None
        self.check_updates_btn.setEnabled(bool(GITHUB_CHECK_ENABLED))
        self.check_updates_btn.setText("Проверить обновления")

    def _on_update_error(self, message):
        app_logger.write(f"[ERROR] обновление: {message}")
        QMessageBox.warning(self, "Обновления", message)

    def _on_update_result(self, info):
        if not info:
            QMessageBox.information(self, "Обновления", "Не удалось получить данные.")
            return

        if info.get("no_releases"):
            QMessageBox.information(
                self,
                "Обновления",
                f"Установлена версия {info.get('current')}.\n\n"
                f"На GitHub пока нет ни одного релиза — "
                f"проверять нечего.",
            )
            return

        if not info.get("has_update"):
            QMessageBox.information(
                self,
                "Обновления",
                f"Установлена последняя версия.\n"
                f"Текущая: {info.get('current')}\n"
                f"На GitHub: {info.get('latest')}",
            )
            return

        latest = info.get("latest", "?")
        name = info.get("name") or ""
        notes = info.get("notes") or ""

        short_notes = notes.strip()
        if len(short_notes) > 500:
            short_notes = short_notes[:500] + "..."

        body = (
            f"<b>Доступна новая версия: {latest}</b><br>"
            f"<span style='color:#8b8f9e;'>Текущая: {info.get('current')}</span>"
        )
        if name:
            body += f"<br><br>{name}"
        if short_notes:
            body += f"<br><br><pre style='white-space:pre-wrap'>{short_notes}</pre>"

        box = QMessageBox(self)
        box.setWindowTitle("Доступно обновление")
        box.setTextFormat(Qt.RichText)
        box.setText(body)

        download_btn = box.addButton("Обновить", QMessageBox.AcceptRole)
        open_btn = box.addButton("Открыть на GitHub", QMessageBox.ActionRole)
        box.addButton("Отмена", QMessageBox.RejectRole)

        box.exec()

        clicked = box.clickedButton()

        if clicked is open_btn:
            url = info.get("html_url") or ""
            if url:
                QDesktopServices.openUrl(QUrl(url))
            return

        if clicked is download_btn:
            if info.get("asset_url"):
                self._download_update(info)
            else:
                url = info.get("html_url") or ""
                if url:
                    QDesktopServices.openUrl(QUrl(url))
                    QMessageBox.information(
                        self,
                        "Обновление",
                        "Файл релиза не прикреплён. "
                        "Открыл страницу релиза — скачайте вручную.",
                    )

    # =========================================================
    # UPDATES — APPLY
    # =========================================================

    def _download_update(self, info):
        if self._dl_thread is not None and self._dl_thread.isRunning():
            QMessageBox.information(self, "Обновление", "Загрузка уже идёт.")
            return

        asset_url = info.get("asset_url") or ""
        asset_name = info.get("asset_name") or ""

        self._update_progress = QProgressDialog(
            "Загрузка обновления...",
            "Отмена",
            0,
            100,
            self,
        )
        self._update_progress.setWindowTitle("Обновление")
        self._update_progress.setWindowModality(Qt.WindowModal)
        self._update_progress.setMinimumDuration(0)
        self._update_progress.setValue(0)

        self._dl_thread = QThread()
        self._dl_worker = ApplyUpdateWorker(asset_url, asset_name)
        self._dl_worker.moveToThread(self._dl_thread)

        self._dl_thread.started.connect(self._dl_worker.run)

        # bound-методы с @Slot → QueuedConnection → выполняются в главном потоке
        self._dl_worker.progress.connect(self._on_update_progress)
        self._dl_worker.error.connect(self._on_update_download_error)
        self._dl_worker.log.connect(app_logger.write)
        self._dl_worker.ready.connect(self._on_update_ready)

        self._dl_worker.finished.connect(self._dl_thread.quit)
        self._dl_worker.finished.connect(self._dl_worker.deleteLater)
        self._dl_thread.finished.connect(self._dl_thread.deleteLater)
        self._dl_thread.finished.connect(self._dl_thread_done)

        # «Отмена» прерывает загрузку между чанками
        self._update_progress.canceled.connect(self._dl_worker.stop)

        self._dl_thread.start()

    @Slot(int, int)
    def _on_update_progress(self, done, total):
        if self._update_progress is None:
            return
        if total > 0:
            self._update_progress.setValue(int(done / total * 100))
        else:
            self._update_progress.setValue(0)

    @Slot()
    def _on_update_ready(self):
        """Файлы скачаны, .bat запущен — показываем сообщение и закрываемся."""
        if self._update_progress is not None:
            self._update_progress.close()
            self._update_progress = None

        QMessageBox.information(
            self,
            "Обновление",
            "Новая версия скачана.\n\n"
            "Приложение сейчас закроется, файлы заменятся автоматически, "
            "и PLANA_DP запустится заново.\n\n"
            "Не запускайте приложение вручную, пока обновление не завершится.",
        )
        QApplication.quit()

    @Slot(str)
    def _on_update_download_error(self, msg):
        if self._update_progress is not None:
            self._update_progress.close()
            self._update_progress = None

        app_logger.write(f"[ERROR] автообновление: {msg}")
        QMessageBox.warning(self, "Обновление", msg)

    def _dl_thread_done(self):
        self._dl_thread = None
        self._dl_worker = None
        # если пользователь нажал «Отмена» — слоты result/error не вызовутся,
        # поэтому закрываем диалог здесь
        if self._update_progress is not None:
            self._update_progress.close()
            self._update_progress = None

    # =========================================================
    # WIPE / UNINSTALL
    # =========================================================

    def _wipe_cache(self):
        answer = QMessageBox.question(
            self,
            "Очистка",
            "Удалить историю и кеш тайтлов?",
        )
        if answer != QMessageBox.Yes:
            return

        import shutil as _sh

        clear_history()
        cache = get_data_dir() / "cache"
        if cache.exists():
            _sh.rmtree(cache, ignore_errors=True)

        app_logger.write("История и кеш очищены.")
        QMessageBox.information(self, "Готово", "История и кеш очищены.")

    def _run_uninstaller(self):
        delete_downloads = self.un_dl_check.isChecked()
        delete_app = self.un_app_check.isChecked()

        msg = (
            "Удалить PLANA_DP?\n\n"
            f"• Папка данных: {get_data_dir()}\n"
            f"• Bootstrap: %APPDATA%/PLANA_DP/\n"
            f"• Папка загрузок: "
            f"{'ДА' if delete_downloads else 'нет (останется)'}\n"
            f"• Папка приложения: "
            f"{'ДА' if delete_app else 'нет (останется)'}\n\n"
            "После подтверждения приложение закроется, "
            "а удаление продолжится в отдельном окне."
        )

        answer = QMessageBox.warning(
            self,
            "Деинсталляция",
            msg,
            QMessageBox.Yes | QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return

        self._uninstall_thread = QThread()
        self._uninstall_worker = UninstallWorker(
            delete_downloads=delete_downloads,
            delete_app_folder=delete_app,
        )
        self._uninstall_worker.moveToThread(self._uninstall_thread)

        self._uninstall_thread.started.connect(self._uninstall_worker.run)

        self._uninstall_worker.log.connect(app_logger.write)
        self._uninstall_worker.error.connect(self._on_uninstall_error)
        self._uninstall_worker.finished.connect(self._on_uninstall_ready)

        self._uninstall_worker.finished.connect(self._uninstall_thread.quit)
        self._uninstall_worker.finished.connect(self._uninstall_worker.deleteLater)
        self._uninstall_thread.finished.connect(self._uninstall_thread.deleteLater)

        self._uninstall_thread.start()

    @Slot(str)
    def _on_uninstall_error(self, msg):
        app_logger.write(f"[ERROR] деинсталлятор: {msg}")
        QMessageBox.warning(self, "Деинсталлятор", msg)

    def _on_uninstall_ready(self, ok):
        self._uninstall_thread = None
        self._uninstall_worker = None

        if not ok:
            return

        app = QApplication.instance()
        if app is not None:
            app.quit()
