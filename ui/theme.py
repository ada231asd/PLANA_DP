STYLE = """
QMainWindow, QWidget#root {
    background: #0e0f13;
    color: #e6e6ee;
    font-family: "Segoe UI";
    font-size: 14px;
}

/* Sidebar */
QFrame#sidebar {
    background: #12131a;
    border-right: 1px solid #1f2230;
}

QLabel#logo {
    font-size: 17px;
    font-weight: 800;
    letter-spacing: 3px;
    color: #c5a4ff;
    background: transparent;
}
QLabel#sublogo {
    color: #6b6f80;
    font-size: 10px;
    letter-spacing: 3px;
    background: transparent;
}
QLabel#section {
    color: #8f94a9;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 2px;
    background: transparent;
}

QPushButton#nav {
    text-align: left;
    padding: 11px 14px;
    border: none;
    border-radius: 8px;
    color: #a4a7b6;
    background: transparent;
    font-weight: 600;
}
QPushButton#nav:hover {
    background: #1a1c26;
    color: #ffffff;
}
QPushButton#nav:checked {
    background: #241b3a;
    color: #c5a4ff;
    border-left: 3px solid #8e63d9;
}

/* Inputs */
QLineEdit, QTextEdit, QListWidget, QComboBox, QSpinBox {
    background: #14161f;
    border: 1px solid #242736;
    border-radius: 8px;
    padding: 4px 10px;
    color: #f0f0f5;
    min-height: 26px;
    selection-background-color: #4a3a7a;
}
QLineEdit:focus, QTextEdit:focus, QComboBox:focus, QSpinBox:focus {
    border: 1px solid #8e63d9;
}

/* ---------- QSpinBox ---------- */
QSpinBox {
    padding-right: 26px;
}

QSpinBox::up-button, QSpinBox::down-button {
    subcontrol-origin: border;
    width: 22px;
    background: transparent;
    border: none;
    margin: 0;
}
QSpinBox::up-button {
    subcontrol-position: top right;
}
QSpinBox::down-button {
    subcontrol-position: bottom right;
}
QSpinBox::up-button:hover, QSpinBox::down-button:hover {
    background: #2a2e3d;
    border-radius: 4px;
}
QSpinBox::up-arrow {
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-bottom: 4px solid #a4a7b6;
    width: 0;
    height: 0;
}
QSpinBox::down-arrow {
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 4px solid #a4a7b6;
    width: 0;
    height: 0;
}

/* ---------- QComboBox ---------- */
QComboBox {
    padding-right: 28px;
}
QComboBox::drop-down {
    subcontrol-origin: border;
    subcontrol-position: top right;
    width: 24px;
    border: none;
    background: transparent;
}
QComboBox::drop-down:hover {
    background: #2a2e3d;
    border-top-right-radius: 7px;
    border-bottom-right-radius: 7px;
}
QComboBox::down-arrow {
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid #a4a7b6;
    width: 0;
    height: 0;
}
QComboBox QAbstractItemView {
    background: #14161f;
    border: 1px solid #242736;
    color: #f0f0f5;
    selection-background-color: #2a2140;
    outline: none;
}

/* Buttons */
QPushButton {
    background: #1c1f2b;
    border: 1px solid #2a2e3d;
    border-radius: 8px;
    padding: 7px 14px;
    color: #e6e6ee;
    min-height: 22px;
}
QPushButton:hover { background: #242838; }
QPushButton:pressed { background: #1a1d28; }

QPushButton#primary {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #7b52c9, stop:1 #a06be0);
    border: none;
    font-weight: 700;
    color: #ffffff;
}
QPushButton#primary:hover {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #8a5fd6, stop:1 #b07aec);
}
QPushButton:disabled {
    color: #555970;
    background: #171922;
    border-color: #1f2230;
}

QFrame#card {
    background: #12141c;
    border: 1px solid #1f2230;
    border-radius: 12px;
}

QLabel#title {
    font-size: 24px;
    font-weight: 800;
    background: transparent;
}
QLabel#muted {
    color: #8b8f9e;
    background: transparent;
}

QCheckBox {
    color: #e6e6ee;
    spacing: 8px;
    background: transparent;
}
QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border-radius: 4px;
    border: 1px solid #2a2e3d;
    background: #14161f;
}
QCheckBox::indicator:hover {
    border-color: #8e63d9;
}
QCheckBox::indicator:checked {
    background: #7b52c9;
    border-color: #8e63d9;
}

QRadioButton {
    color: #e6e6ee;
    spacing: 8px;
    background: transparent;
}
QRadioButton::indicator {
    width: 14px;
    height: 14px;
    border-radius: 7px;
    border: 1px solid #2a2e3d;
    background: #14161f;
}
QRadioButton::indicator:checked {
    background: #7b52c9;
    border-color: #8e63d9;
}

QListWidget {
    outline: none;
}
QListWidget::item {
    padding: 8px;
    border-bottom: 1px solid #1c1f2b;
}
QListWidget::item:selected {
    background: #2a2140;
    color: #ffffff;
}

QProgressBar {
    background: #14161f;
    border: 1px solid #242736;
    border-radius: 6px;
    text-align: center;
    height: 16px;
    font-size: 11px;
    color: #a4a7b6;
}
QProgressBar::chunk {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #7b52c9, stop:1 #a06be0);
    border-radius: 5px;
}

QScrollBar:vertical {
    background: transparent;
    width: 10px;
    margin: 0;
}
QScrollBar::handle:vertical {
    background: #2a2e3d;
    border-radius: 5px;
    min-height: 30px;
}
QScrollBar::handle:vertical:hover { background: #3a3f52; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar:horizontal {
    background: transparent;
    height: 10px;
}
QScrollBar::handle:horizontal {
    background: #2a2e3d;
    border-radius: 5px;
    min-width: 30px;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }

QStatusBar {
    background: #0e0f13;
    color: #8b8f9e;
    border-top: 1px solid #1f2230;
}

QMessageBox { background: #12141c; }
QMessageBox QLabel { color: #e6e6ee; }

QToolTip {
    background: #1c1f2b;
    color: #e6e6ee;
    border: 1px solid #2a2e3d;
    padding: 4px 6px;
    border-radius: 6px;
}
"""
