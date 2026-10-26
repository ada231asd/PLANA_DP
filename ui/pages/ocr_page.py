from pathlib import Path

from PySide6.QtCore import Qt, QThread, Slot
from PySide6.QtGui import QDesktopServices
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from logger import app_logger
from workers.ocr_worker import OcrWorker


FIELD_HEIGHT = 34


class OcrPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        self._thread = None
        self._worker = None

        self._build_ui()

    # =========================================================
    # UI
    # =========================================================

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 20)
        layout.setSpacing(16)

        # ---- заголовок ----
        header = QHBoxLayout()
        title = QLabel("Распознавание текста")
        title.setObjectName("title")
        header.addWidget(title)
        header.addStretch()
        layout.addLayout(header)

        # ================= ПАРАМЕТРЫ =================
        params_card = QFrame()
        params_card.setObjectName("card")

        pc = QVBoxLayout(params_card)
        pc.setContentsMargins(24, 20, 24, 20)
        pc.setSpacing(12)

        hint = QLabel(
            "Выберите папку с изображениями главы — приложение распознаёт "
            "английский текст на каждом и сохраняет результат в один .txt "
            "в той же папке."
        )
        hint.setObjectName("muted")
        hint.setWordWrap(True)
        pc.addWidget(hint)

        # --- папка ---
        row = QHBoxLayout()
        row.setSpacing(8)

        self.folder_edit = QLineEdit()
        self.folder_edit.setPlaceholderText("Путь к папке с изображениями главы...")
        self.folder_edit.setMinimumHeight(FIELD_HEIGHT)
        row.addWidget(self.folder_edit, 1)

        pick_btn = QPushButton("Обзор...")
        pick_btn.setMinimumHeight(FIELD_HEIGHT)
        pick_btn.setMinimumWidth(110)
        pick_btn.setCursor(Qt.PointingHandCursor)
        pick_btn.clicked.connect(self._pick_folder)
        row.addWidget(pick_btn)

        open_btn = QPushButton("Открыть")
        open_btn.setMinimumHeight(FIELD_HEIGHT)
        open_btn.setMinimumWidth(110)
        open_btn.setCursor(Qt.PointingHandCursor)
        open_btn.clicked.connect(self._open_folder)
        row.addWidget(open_btn)

        pc.addLayout(row)

        # --- файл результата ---
        row2 = QHBoxLayout()
        row2.setSpacing(8)

        lbl_out = QLabel("Файл результата:")
        row2.addWidget(lbl_out)

        self.output_edit = QLineEdit("chapter_text.txt")
        self.output_edit.setMinimumHeight(FIELD_HEIGHT)
        self.output_edit.setMaximumWidth(300)
        row2.addWidget(self.output_edit)

        row2.addSpacing(20)

        lbl_lang = QLabel("Язык:")
        row2.addWidget(lbl_lang)

        self.lang_combo = QComboBox()
        self.lang_combo.setMinimumHeight(FIELD_HEIGHT)
        self.lang_combo.addItems(["en", "ja", "ru", "auto"])
        self.lang_combo.setMaximumWidth(140)
        row2.addWidget(self.lang_combo)

        row2.addStretch()
        pc.addLayout(row2)

        layout.addWidget(params_card)

        # ================= ЗАПУСК =================
        action_card = QFrame()
        action_card.setObjectName("card")

        ac = QVBoxLayout(action_card)
        ac.setContentsMargins(24, 20, 24, 20)
        ac.setSpacing(12)

        # --- статус ---
        self.status = QLabel("Готов к запуску")
        self.status.setObjectName("muted")
        self.status.setWordWrap(True)
        ac.addWidget(self.status)

        # --- прогресс ---
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        ac.addWidget(self.progress)

        # --- кнопки ---
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        self.start_btn = QPushButton("Распознать")
        self.start_btn.setObjectName("primary")
        self.start_btn.setMinimumHeight(FIELD_HEIGHT)
        self.start_btn.setMinimumWidth(180)
        self.start_btn.setCursor(Qt.PointingHandCursor)
        self.start_btn.clicked.connect(self.start_ocr)
        btn_row.addWidget(self.start_btn)

        self.stop_btn = QPushButton("Отмена")
        self.stop_btn.setMinimumHeight(FIELD_HEIGHT)
        self.stop_btn.setMinimumWidth(140)
        self.stop_btn.setCursor(Qt.PointingHandCursor)
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._cancel)
        btn_row.addWidget(self.stop_btn)

        ac.addLayout(btn_row)

        # --- превью / лог ---
        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setMinimumHeight(220)
        self.preview.setStyleSheet(
            "font-family: Consolas, 'Courier New', monospace; font-size: 12px;"
        )
        ac.addWidget(self.preview, 1)

        layout.addWidget(action_card, 1)

    # =========================================================
    # HELPERS
    # =========================================================

    def _pick_folder(self):
        current = self.folder_edit.text().strip()
        start_dir = current if current and Path(current).is_dir() else ""
        d = QFileDialog.getExistingDirectory(
            self, "Выберите папку с изображениями", start_dir
        )
        if d:
            self.folder_edit.setText(d)

    def _open_folder(self):
        path = self.folder_edit.text().strip()
        if path and Path(path).exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))
        else:
            QMessageBox.information(self, "OCR", "Сначала укажите существующую папку.")

    # =========================================================
    # START / STOP
    # =========================================================

    def start_ocr(self):
        if self._thread is not None and self._thread.isRunning():
            return

        folder = self.folder_edit.text().strip()
        if not folder or not Path(folder).is_dir():
            QMessageBox.warning(
                self, "OCR", "Укажите существующую папку с изображениями."
            )
            return

        output = self.output_edit.text().strip() or "chapter_text.txt"
        if not output.lower().endswith(".txt"):
            output += ".txt"

        lang = self.lang_combo.currentText()

        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.progress.setValue(0)
        self.status.setText("Запуск OCR...")
        self.preview.clear()

        self._thread = QThread()
        self._worker = OcrWorker(folder, output_name=output, lang=lang)
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.run)

        self._worker.progress.connect(self._on_progress)
        self._worker.log.connect(app_logger.write)
        self._worker.log.connect(self._on_log)
        self._worker.result.connect(self._on_result)
        self._worker.error.connect(self._on_error)

        self._worker.finished.connect(self._thread.quit)
        self._worker.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.finished.connect(self._on_finished)

        self._thread.start()

    def _cancel(self):
        if self._worker is not None:
            self._worker.stop()
            self.status.setText("Отмена...")

    # =========================================================
    # SLOTS
    # =========================================================

    @Slot(int, int, str)
    def _on_progress(self, done, total, name):
        if total > 0:
            self.progress.setValue(int(done / total * 100))
        self.status.setText(f"[{done}/{total}] {name}")

    @Slot(str)
    def _on_log(self, line):
        self.preview.appendPlainText(line)

    @Slot(str)
    def _on_result(self, path):
        self.status.setText(f"Готово: {path}")
        self.progress.setValue(100)
        try:
            text = Path(path).read_text(encoding="utf-8")
            self.preview.setPlainText(text)
        except Exception as exc:
            app_logger.write(f"[WARN] не удалось открыть результат: {exc}")
            QMessageBox.warning(
                self, "OCR", f"Файл записан, но открыть не удалось:\n{exc}"
            )

    @Slot(str)
    def _on_error(self, msg):
        self.status.setText(f"Ошибка: {msg}")
        app_logger.write(f"[ERROR] OCR: {msg}")
        QMessageBox.warning(self, "OCR", msg)

    def _on_finished(self):
        self._thread = None
        self._worker = None
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)

        if self.progress.value() < 100:
            if "Готово" not in self.status.text():
                self.status.setText("Остановлено")

    # =========================================================
    # SHUTDOWN
    # =========================================================

    def shutdown(self):
        if self._worker is not None:
            try:
                self._worker.stop()
            except Exception:
                pass
        if self._thread is not None:
            try:
                if self._thread.isRunning():
                    self._thread.quit()
                    self._thread.wait(3000)
            except Exception:
                pass
