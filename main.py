import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMessageBox

from config import APP_NAME, APP_VERSION, LOGO_JPG
from paths import (
    default_data_dir,
    is_in_user_config,
    load_bootstrap,
    migrate_data_dir_to_default,
    save_bootstrap,
)


def _setup_high_dpi():
    """Должно быть вызвано ДО создания QApplication."""
    try:
        QApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
        )
    except Exception:
        pass
    try:
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    except Exception:
        pass


def _restart_app():
    from PySide6.QtCore import QProcess

    QProcess.startDetached(sys.executable, sys.argv)


def _maybe_migrate_data_dir():
    """
    Проверяет, лежит ли data_dir внутри %APPDATA%/PLANA_DP.
    Если нет — предлагает перенести.
    Возвращает True, если нужен перезапуск приложения.
    """
    boot = load_bootstrap()
    if not boot:
        return False

    data_dir = boot.get("data_dir") or ""
    if not data_dir:
        return False

    if is_in_user_config(data_dir):
        boot["last_version"] = APP_VERSION
        save_bootstrap(boot)
        return False

    last_version = boot.get("last_version") or ""
    declined = bool(boot.get("migrate_declined", False))
    if declined and last_version == APP_VERSION:
        return False

    target = default_data_dir()

    box = QMessageBox()
    box.setWindowTitle("Расположение данных")
    box.setIcon(QMessageBox.Question)
    box.setText(
        "Данные приложения хранятся вне стандартной папки:\n\n"
        f"Текущая:  {data_dir}\n"
        f"Стандарт: {target}\n\n"
        "Перенести данные в стандартную папку?\n"
        "Это нужно для корректной работы обновлений и деинсталлятора."
    )
    box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
    box.setDefaultButton(QMessageBox.Yes)
    answer = box.exec()

    if answer != QMessageBox.Yes:
        boot["migrate_declined"] = True
        boot["last_version"] = APP_VERSION
        save_bootstrap(boot)
        return False

    if migrate_data_dir_to_default():
        QMessageBox.information(
            None,
            "Перенос завершён",
            "Данные перенесены. Приложение будет перезапущено.",
        )
        return True

    QMessageBox.warning(
        None,
        "Ошибка переноса",
        "Не удалось перенести данные. Приложение продолжит\nработу с текущей папкой.",
    )
    boot["migrate_declined"] = True
    boot["last_version"] = APP_VERSION
    save_bootstrap(boot)
    return False


def main():
    _setup_high_dpi()

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(APP_NAME)

    try:
        app.setStyle("Fusion")
    except Exception:
        pass

    try:
        if LOGO_JPG.exists():
            app.setWindowIcon(QIcon(str(LOGO_JPG)))
    except Exception:
        pass

    # Глобальный стиль ставим ПОСЛЕ setStyle, чтобы он не перекрылся.
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

    # Проверка расположения данных (после первого запуска или после обновления)
    if _maybe_migrate_data_dir():
        _restart_app()
        sys.exit(0)

    from ui.main_window import MainWindow

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
