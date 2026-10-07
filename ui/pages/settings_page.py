from pathlib import Path

from PySide6.QtCore import Qt, QUrl, QThread, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QProgressDialog,
    QPushButton,
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
from paths import get_data_dir

from workers.update_worker import UpdateWorker, DownloadWorker
from workers.uninstall_worker import UninstallWorker


NOISY_PREFIXES = (
    "[JS]",
    "[REQUEST FAILED]",
    "[PAGE ERROR]",
    "[HTTP ",
)

FIELD_HEIGHT = 34


class SettingsPage(QWidget):
    settings_saved = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self._log_visible = False

        self._update_thread = None
        self._update_worker = None
        self._dl_thread = None
        self._dl_worker = None
        self._uninstall_thread = None
        self._uninstall_worker = None

        self._build_ui()
        self.load()

        app_logger.message.connect(self._on_log_line)
        app_logger.cleared.connect(self._on_log_cleared)

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

    # =========================================================
    # UI
    # =========================================================

    def _build_ui(self):
        layout = QVBoxLayout(self)
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
        grid.setColumnStretch(0, 0)  # лейблы — по содержимому
        grid.setColumnStretch(1, 1)  # поля — растягиваются
        grid.setContentsMargins(0, 0, 0, 0)

        row = 0

        # ---- Папка загрузок ----
        grid.addWidget(self._lbl("Папка загрузок"), row, 0)

        dir_row = QHBoxLayout()
        dir_row.setContentsMargins(0, 0, 0, 0)
        dir_row.setSpacing(8)

        self.download_dir = QLineEdit()
        self.download_dir.setMinimumHeight(FIELD_HEIGHT)
        dir_row.addWidget(self.download_dir, 1)

        browse = self._btn("Обзор...", min_w=110)
        browse.clicked.connect(self._pick_dir)
        dir_row.addWidget(browse)

        open_dir = self._btn("Открыть", min_w=110)
        open_dir.clicked.connect(self._open_dir)
        dir_row.addWidget(open_dir)

        dir_widget = QWidget()
        dir_widget.setLayout(dir_row)
        grid.addWidget(dir_widget, row, 1)
        row += 1

        # ---- Браузер ----
        grid.addWidget(self._lbl("Браузер"), row, 0)
        self.browser = QComboBox()
        self.browser.addItems(["firefox", "chromium"])
        self.browser.setMinimumHeight(FIELD_HEIGHT)
        self.browser.setMinimumWidth(220)
        self.browser.setMaximumWidth(300)
        self.browser.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        grid.addWidget(self.browser, row, 1, Qt.AlignLeft)
        row += 1

        # ---- Чекбоксы (на всю ширину) ----
        self.headless = QCheckBox("Запускать браузер в фоне (headless)")
        self.headless.setMinimumHeight(FIELD_HEIGHT)
        grid.addWidget(self.headless, row, 0, 1, 2)
        row += 1

        self.use_cache = QCheckBox(
            "Использовать кеш тайтлов (не перезагружать с сайта)"
        )
        self.use_cache.setMinimumHeight(FIELD_HEIGHT)
        grid.addWidget(self.use_cache, row, 0, 1, 2)
        row += 1

        self.delete_chapters = QCheckBox("Удалять скачанные главы вместе с историей")
        self.delete_chapters.setMinimumHeight(FIELD_HEIGHT)
        grid.addWidget(self.delete_chapters, row, 0, 1, 2)
        row += 1

        # ---- Числовые поля ----
        grid.addWidget(self._lbl("Повторов загрузки картинки"), row, 0)
        self.retries = QSpinBox()
        self.retries.setRange(1, 10)
        self.retries.setMinimumHeight(FIELD_HEIGHT)
        self.retries.setFixedWidth(140)
        grid.addWidget(self.retries, row, 1, Qt.AlignLeft)
        row += 1

        grid.addWidget(self._lbl("Таймаут навигации"), row, 0)
        self.nav_timeout = QSpinBox()
        self.nav_timeout.setRange(5000, 180000)
        self.nav_timeout.setSingleStep(1000)
        self.nav_timeout.setSuffix(" мс")
        self.nav_timeout.setMinimumHeight(FIELD_HEIGHT)
        self.nav_timeout.setFixedWidth(160)
        grid.addWidget(self.nav_timeout, row, 1, Qt.AlignLeft)
        row += 1

        grid.addWidget(self._lbl("Таймаут загрузки картинки"), row, 0)
        self.dl_timeout = QSpinBox()
        self.dl_timeout.setRange(5000, 300000)
        self.dl_timeout.setSingleStep(1000)
        self.dl_timeout.setSuffix(" мс")
        self.dl_timeout.setMinimumHeight(FIELD_HEIGHT)
        self.dl_timeout.setFixedWidth(160)
        grid.addWidget(self.dl_timeout, row, 1, Qt.AlignLeft)
        row += 1

        grid.addWidget(self._lbl("Лимит истории"), row, 0)
        self.history_limit = QSpinBox()
        self.history_limit.setRange(10, 2000)
        self.history_limit.setSingleStep(10)
        self.history_limit.setMinimumHeight(FIELD_HEIGHT)
        self.history_limit.setFixedWidth(140)
        grid.addWidget(self.history_limit, row, 1, Qt.AlignLeft)
        row += 1

        card_layout.addLayout(grid)
        card_layout.addSpacing(20)

        # ---- Кнопки ----
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
        row2.addWidget(self.un_dl_check)

        self.un_app_check = QCheckBox("Удалить папку приложения (если .exe)")
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

        # ================= ЛОГИ =================
        log_card = QFrame()
        log_card.setObjectName("card")

        log_layout = QVBoxLayout(log_card)
        log_layout.setContentsMargins(24, 20, 24, 20)
        log_layout.setSpacing(12)

        log_header = QHBoxLayout()
        log_header_title = QLabel("ЛОГИ ПРИЛОЖЕНИЯ")
        log_header_title.setObjectName("section")
        log_header.addWidget(log_header_title)
        log_header.addStretch()

        self.toggle_log_btn = self._btn("Показать", min_w=130)
        self.toggle_log_btn.clicked.connect(self._toggle_log)
        log_header.addWidget(self.toggle_log_btn)

        log_layout.addLayout(log_header)

        self.log_container = QWidget()
        log_container_layout = QVBoxLayout(self.log_container)
        log_container_layout.setContentsMargins(0, 0, 0, 0)
        log_container_layout.setSpacing(8)

        controls = QHBoxLayout()
        self.filter_check = QCheckBox("Скрыть технический шум (JS/сеть)")
        self.filter_check.setChecked(True)
        self.filter_check.stateChanged.connect(self._refresh_log_view)
        controls.addWidget(self.filter_check)
        controls.addStretch()

        clear_btn = self._btn("Очистить", min_w=120)
        clear_btn.clicked.connect(app_logger.clear)
        controls.addWidget(clear_btn)

        export_btn = self._btn("Сохранить в файл...", min_w=190)
        export_btn.clicked.connect(self._export_log)
        controls.addWidget(export_btn)

        log_container_layout.addLayout(controls)

        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.log_view.setStyleSheet(
            "font-family: Consolas, 'Courier New', monospace;font-size: 12px;"
        )
        log_container_layout.addWidget(self.log_view, 1)

        log_layout.addWidget(self.log_container, 1)
        self.log_container.setVisible(False)

        layout.addWidget(log_card, 1)

        self._refresh_log_view()

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
        s["image_retries"] = int(self.retries.value())
        s["navigation_timeout"] = int(self.nav_timeout.value())
        s["download_timeout"] = int(self.dl_timeout.value())
        s["history_limit"] = int(self.history_limit.value())

        save_settings(s)
        self.settings_saved.emit()
        QMessageBox.information(self, "Настройки", "Сохранено.")

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
    # UPDATES
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

    def _download_update(self, info):
        asset_url = info.get("asset_url") or ""
        asset_name = info.get("asset_name") or ""

        progress = QProgressDialog(
            "Загрузка обновления...",
            "Отмена",
            0,
            100,
            self,
        )
        progress.setWindowTitle("Обновление")
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)
        progress.setValue(0)

        self._dl_thread = QThread()
        self._dl_worker = DownloadWorker(asset_url, asset_name)
        self._dl_worker.moveToThread(self._dl_thread)

        def on_progress(done, total):
            if total > 0:
                progress.setValue(int(done / total * 100))
            else:
                progress.setValue(0)

        def on_result(path):
            progress.close()
            QMessageBox.information(
                self,
                "Обновление",
                f"Файл сохранён в:\n{path}\n\n"
                f"Закройте PLANA_DP, замените файлы и запустите заново.",
            )
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(path).parent)))

        def on_error(msg):
            progress.close()
            QMessageBox.warning(self, "Обновление", msg)

        self._dl_thread.started.connect(self._dl_worker.run)
        self._dl_worker.progress.connect(on_progress)
        self._dl_worker.result.connect(on_result)
        self._dl_worker.error.connect(on_error)
        self._dl_worker.log.connect(app_logger.write)

        self._dl_worker.finished.connect(self._dl_thread.quit)
        self._dl_worker.finished.connect(self._dl_worker.deleteLater)
        self._dl_thread.finished.connect(self._dl_thread.deleteLater)
        self._dl_thread.finished.connect(self._dl_thread_done)

        progress.canceled.connect(self._dl_thread.quit)

        self._dl_thread.start()

    def _dl_thread_done(self):
        self._dl_thread = None
        self._dl_worker = None

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
        self._uninstall_worker.error.connect(
            lambda msg: QMessageBox.warning(self, "Деинсталлятор", msg)
        )
        self._uninstall_worker.finished.connect(self._on_uninstall_ready)

        self._uninstall_worker.finished.connect(self._uninstall_thread.quit)
        self._uninstall_worker.finished.connect(self._uninstall_worker.deleteLater)
        self._uninstall_thread.finished.connect(self._uninstall_thread.deleteLater)

        self._uninstall_thread.start()

    def _on_uninstall_ready(self, ok):
        self._uninstall_thread = None
        self._uninstall_worker = None

        if not ok:
            return

        from PySide6.QtWidgets import QApplication

        app = QApplication.instance()
        if app is not None:
            app.quit()

    # =========================================================
    # LOGS
    # =========================================================

    def _toggle_log(self):
        self._log_visible = not self._log_visible
        self.log_container.setVisible(self._log_visible)
        self.toggle_log_btn.setText("Скрыть" if self._log_visible else "Показать")
        if self._log_visible:
            self._refresh_log_view()

    def _should_show(self, line):
        if not self.filter_check.isChecked():
            return True
        return not line.startswith(NOISY_PREFIXES)

    def _refresh_log_view(self):
        lines = [ln for ln in app_logger.lines() if self._should_show(ln)]
        self.log_view.setPlainText("\n".join(lines))
        sb = self.log_view.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _on_log_line(self, line):
        if not self._log_visible:
            return
        if not self._should_show(line):
            return
        self.log_view.appendPlainText(line)
        sb = self.log_view.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _on_log_cleared(self):
        self.log_view.clear()

    def _export_log(self):
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Сохранить лог",
            "app.log",
            "Log files (*.log *.txt);;All files (*)",
        )
        if not path:
            return
        if app_logger.export(path):
            QMessageBox.information(self, "Логи", "Файл сохранён.")
        else:
            QMessageBox.warning(self, "Логи", "Не удалось сохранить файл.")
