import sys

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from paths import load_bootstrap, save_bootstrap
from config import APP_NAME, LOGO_JPG


def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(APP_NAME)

    # Логотип в панель задач
    try:
        if LOGO_JPG.exists():
            app.setWindowIcon(QIcon(str(LOGO_JPG)))
    except Exception:
        pass

    # Глобальный стиль
    try:
        from ui.theme import STYLE

        app.setStyleSheet(STYLE)
    except Exception:
        pass

    # Первый запуск → мастер настройки
    if load_bootstrap() is None:
        from ui.setup_wizard import SetupWizard

        wizard = SetupWizard()
        if wizard.exec() != SetupWizard.Accepted:
            sys.exit(0)
        save_bootstrap(wizard.result_data())

    # Теперь можно грузить хранилище/UI
    from ui.main_window import MainWindow

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
