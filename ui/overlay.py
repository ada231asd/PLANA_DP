from pathlib import Path

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QMovie
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from config import GIF_LOADING


class LoadingOverlay(QWidget):
    """
    Полупрозрачный оверлей на весь центральный виджет:
    затемняет приложение и крутит GIF по центру.
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet("background: rgba(8, 9, 13, 205);")
        self.setAutoFillBackground(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(18)

        self.gif_label = QLabel()
        self.gif_label.setAlignment(Qt.AlignCenter)

        self._movie = None
        if Path(GIF_LOADING).exists():
            self._movie = QMovie(str(GIF_LOADING))
            self._movie.setScaledSize(QSize(220, 220))
            self.gif_label.setMovie(self._movie)
        else:
            self.gif_label.setText("Загрузка...")
            self.gif_label.setStyleSheet(
                "color:#c5a4ff; font-size:14px; letter-spacing:3px;"
            )

        layout.addWidget(self.gif_label)

        self.text_label = QLabel("Загрузка...")
        self.text_label.setAlignment(Qt.AlignCenter)
        self.text_label.setStyleSheet(
            "color: #c5a4ff;"
            "font-size: 13px;"
            "font-weight: 700;"
            "letter-spacing: 3px;"
            "background: transparent;"
        )
        layout.addWidget(self.text_label)

        self.hide()

    def show_overlay(self, text="Загрузка..."):
        self.text_label.setText(text.upper())
        if self._movie is not None:
            self._movie.start()
        self.raise_()
        self.show()

    def hide_overlay(self):
        if self._movie is not None:
            self._movie.stop()
        self.hide()
