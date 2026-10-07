from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
)

from paths import default_data_dir


class SetupWizard(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle("PLANA_DP — первичная настройка")
        self.setMinimumWidth(680)
        self.setModal(True)

        self._data_dir = str(default_data_dir())
        self._download_dir = str(Path(self._data_dir) / "downloads")
        self._download_custom = False

        self._build_ui()
        self._refresh()

    # =========================================================
    # UI
    # =========================================================

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 20)
        root.setSpacing(16)

        title = QLabel("Добро пожаловать в PLANA_DP")
        title.setStyleSheet("font-size:20px;font-weight:800;color:#e6e6ee;")
        root.addWidget(title)

        subtitle = QLabel(
            "Выберите, где приложение будет хранить свои данные "
            "(настройки, историю, кеш) и куда сохранять скачанные главы. "
            "Эти пути можно будет изменить позже в разделе «Настройки»."
        )
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("color:#8b8f9e;")
        root.addWidget(subtitle)

        # --- Данные приложения ---
        data_frame = QFrame()
        data_frame.setStyleSheet(
            "QFrame{background:#171920;border:1px solid #292c37;border-radius:10px;}"
        )
        df = QVBoxLayout(data_frame)
        df.setContentsMargins(18, 16, 18, 16)
        df.setSpacing(10)

        df.addWidget(
            self._section_label("Данные приложения (settings.json, история, кеш)")
        )

        self.data_radio_default = QRadioButton(f"По умолчанию: {default_data_dir()}")
        self.data_radio_custom = QRadioButton("Своя папка")
        self.data_group = QButtonGroup(self)
        self.data_group.addButton(self.data_radio_default, 0)
        self.data_group.addButton(self.data_radio_custom, 1)
        self.data_radio_default.setChecked(True)

        df.addWidget(self.data_radio_default)

        row = QHBoxLayout()
        row.addWidget(self.data_radio_custom)
        self.data_edit = QLineEdit()
        self.data_edit.setEnabled(False)
        row.addWidget(self.data_edit, 1)
        self.data_browse = QPushButton("Обзор...")
        self.data_browse.setEnabled(False)
        self.data_browse.clicked.connect(self._pick_data_dir)
        row.addWidget(self.data_browse)
        df.addLayout(row)

        self.data_group.idClicked.connect(self._on_data_mode)

        root.addWidget(data_frame)

        # --- Папка загрузок ---
        dl_frame = QFrame()
        dl_frame.setStyleSheet(
            "QFrame{background:#171920;border:1px solid #292c37;border-radius:10px;}"
        )
        dlf = QVBoxLayout(dl_frame)
        dlf.setContentsMargins(18, 16, 18, 16)
        dlf.setSpacing(10)

        dlf.addWidget(self._section_label("Папка для скачанных глав"))

        self.dl_radio_default = QRadioButton("Внутри папки данных (рекомендуется)")
        self.dl_radio_custom = QRadioButton("Своя папка")
        self.dl_group = QButtonGroup(self)
        self.dl_group.addButton(self.dl_radio_default, 0)
        self.dl_group.addButton(self.dl_radio_custom, 1)
        self.dl_radio_default.setChecked(True)

        dlf.addWidget(self.dl_radio_default)

        row2 = QHBoxLayout()
        row2.addWidget(self.dl_radio_custom)
        self.dl_edit = QLineEdit()
        self.dl_edit.setEnabled(False)
        row2.addWidget(self.dl_edit, 1)
        self.dl_browse = QPushButton("Обзор...")
        self.dl_browse.setEnabled(False)
        self.dl_browse.clicked.connect(self._pick_download_dir)
        row2.addWidget(self.dl_browse)
        dlf.addLayout(row2)

        self.dl_group.idClicked.connect(self._on_dl_mode)

        root.addWidget(dl_frame)

        root.addStretch()

        # --- Кнопки ---
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        quit_btn = QPushButton("Отмена")
        quit_btn.clicked.connect(self.reject)
        btn_row.addWidget(quit_btn)

        ok_btn = QPushButton("Продолжить")
        ok_btn.setObjectName("primary")
        ok_btn.setStyleSheet(
            "background:#7149b8;color:white;font-weight:700;"
            "border:none;border-radius:8px;padding:9px 22px;"
        )
        ok_btn.clicked.connect(self._on_ok)
        btn_row.addWidget(ok_btn)

        root.addLayout(btn_row)

    @staticmethod
    def _section_label(text):
        lbl = QLabel(text.upper())
        lbl.setStyleSheet(
            "color:#8f94a9;font-size:10px;font-weight:700;"
            "letter-spacing:2px;background:transparent;border:none;"
        )
        return lbl

    # =========================================================
    # HELPERS
    # =========================================================

    def _refresh(self):
        self.data_edit.setText(self._data_dir)
        if self._download_custom:
            self.dl_edit.setText(self._download_dir)
        else:
            self.dl_edit.setText(str(Path(self._data_dir) / "downloads"))

    def _on_data_mode(self, idx):
        custom = idx == 1
        self.data_edit.setEnabled(custom)
        self.data_browse.setEnabled(custom)
        if not custom:
            self._data_dir = str(default_data_dir())
        else:
            self._data_dir = self.data_edit.text() or str(default_data_dir())
        if not self._download_custom:
            self._download_dir = str(Path(self._data_dir) / "downloads")
        self._refresh()

    def _on_dl_mode(self, idx):
        custom = idx == 1
        self._download_custom = custom
        self.dl_edit.setEnabled(custom)
        self.dl_browse.setEnabled(custom)
        if not custom:
            self._download_dir = str(Path(self._data_dir) / "downloads")
        else:
            self._download_dir = self.dl_edit.text() or str(
                Path(self._data_dir) / "downloads"
            )
        self._refresh()

    def _pick_data_dir(self):
        d = QFileDialog.getExistingDirectory(
            self,
            "Выберите папку для данных приложения",
        )
        if d:
            self._data_dir = d
            self._refresh()

    def _pick_download_dir(self):
        d = QFileDialog.getExistingDirectory(
            self,
            "Выберите папку для загрузок",
        )
        if d:
            self._download_dir = d
            self._refresh()

    def _on_ok(self):
        try:
            Path(self._data_dir).mkdir(parents=True, exist_ok=True)
            Path(self._download_dir).mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Ошибка",
                f"Не удалось создать папку:\n{exc}",
            )
            return
        self.accept()

    def result_data(self):
        return {
            "data_dir": self._data_dir,
            "download_dir": self._download_dir,
        }
