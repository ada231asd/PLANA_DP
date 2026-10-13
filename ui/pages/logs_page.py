from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from logger import app_logger


NOISY_PREFIXES = (
    "[JS]",
    "[REQUEST FAILED]",
    "[PAGE ERROR]",
    "[HTTP ",
)

FIELD_HEIGHT = 34


class LogsPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        self._log_visible = False

        self._build_ui()

        app_logger.message.connect(self._on_log_line)
        app_logger.cleared.connect(self._on_log_cleared)

        self._refresh_log_view()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        content = QWidget()
        scroll.setWidget(content)
        outer.addWidget(scroll)

        layout = QVBoxLayout(content)
        layout.setContentsMargins(28, 24, 28, 20)
        layout.setSpacing(16)

        header = QHBoxLayout()
        title = QLabel("Логи приложения")
        title.setObjectName("title")
        header.addWidget(title)
        header.addStretch()
        layout.addLayout(header)

        card = QFrame()
        card.setObjectName("card")

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(24, 20, 24, 20)
        card_layout.setSpacing(12)

        toggle_row = QHBoxLayout()
        toggle_row.setSpacing(12)

        hint = QLabel(
            "По умолчанию содержимое лога скрыто, чтобы не мешать. "
            "Нажмите «Показать», чтобы увидеть записи."
        )
        hint.setObjectName("muted")
        hint.setWordWrap(True)
        toggle_row.addWidget(hint, 1)

        self.toggle_log_btn = QPushButton("Показать")
        self.toggle_log_btn.setMinimumHeight(FIELD_HEIGHT)
        self.toggle_log_btn.setMinimumWidth(130)
        self.toggle_log_btn.setCursor(Qt.PointingHandCursor)
        self.toggle_log_btn.clicked.connect(self._toggle_log)
        toggle_row.addWidget(self.toggle_log_btn)

        card_layout.addLayout(toggle_row)

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

        clear_btn = QPushButton("Очистить")
        clear_btn.setMinimumHeight(FIELD_HEIGHT)
        clear_btn.setMinimumWidth(120)
        clear_btn.setCursor(Qt.PointingHandCursor)
        clear_btn.clicked.connect(app_logger.clear)
        controls.addWidget(clear_btn)

        export_btn = QPushButton("Сохранить в файл...")
        export_btn.setMinimumHeight(FIELD_HEIGHT)
        export_btn.setMinimumWidth(190)
        export_btn.setCursor(Qt.PointingHandCursor)
        export_btn.clicked.connect(self._export_log)
        controls.addWidget(export_btn)

        log_container_layout.addLayout(controls)

        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.log_view.setMinimumHeight(300)
        self.log_view.setStyleSheet(
            "font-family: Consolas, 'Courier New', monospace; font-size: 12px;"
        )
        log_container_layout.addWidget(self.log_view, 1)

        card_layout.addWidget(self.log_container, 1)
        self.log_container.setVisible(False)

        layout.addWidget(card, 1)

    # =========================================================
    # TOGGLE
    # =========================================================

    def _toggle_log(self):
        self._log_visible = not self._log_visible
        self.log_container.setVisible(self._log_visible)
        self.toggle_log_btn.setText("Скрыть" if self._log_visible else "Показать")
        if self._log_visible:
            self._refresh_log_view()

    # =========================================================
    # FILTER
    # =========================================================

    def _should_show(self, line):
        if not self.filter_check.isChecked():
            return True
        return not line.startswith(NOISY_PREFIXES)

    def _refresh_log_view(self):
        lines = [ln for ln in app_logger.lines() if self._should_show(ln)]
        self.log_view.setPlainText("\n".join(lines))
        sb = self.log_view.verticalScrollBar()
        sb.setValue(sb.maximum())

    # =========================================================
    # LOG SIGNALS
    # =========================================================

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

    # =========================================================
    # EXPORT
    # =========================================================

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
