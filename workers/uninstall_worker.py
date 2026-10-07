import os
import subprocess
import sys
import tempfile
from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot

from paths import (
    BOOTSTRAP_FILE,
    get_data_dir,
    get_download_dir,
    app_root,
    is_frozen,
)


def _build_bat(delete_downloads, delete_app_folder):
    """
    Возвращает путь к .bat-скрипту.
    """
    data_dir = get_data_dir()
    bootstrap_dir = BOOTSTRAP_FILE.parent
    download_dir = get_download_dir()
    app_dir = app_root()

    lines = ["@echo off", "chcp 65001 >nul", "title PLANA_DP Uninstaller"]

    lines.append("echo Удаление PLANA_DP...")
    lines.append("timeout /t 2 /nobreak >nul")

    # Убить процессы приложения, если ещё живы
    lines.append("taskkill /F /IM PLANA_DP.exe >nul 2>&1")
    lines.append('taskkill /F /IM python.exe /FI "WINDOWTITLE eq PLANA_DP*" >nul 2>&1')

    # Папка данных
    lines.append(f'if exist "{data_dir}" rmdir /S /Q "{data_dir}"')

    # Bootstrap
    if bootstrap_dir.exists():
        lines.append(f'if exist "{BOOTSTRAP_FILE}" del /F /Q "{BOOTSTRAP_FILE}"')
        lines.append(f'rmdir "{bootstrap_dir}" 2>nul')

    # Папка загрузок (если пользователь согласился)
    if delete_downloads and download_dir.exists():
        lines.append(f'rmdir /S /Q "{download_dir}" 2>nul')

    # Папка самого приложения (если запущено как .exe и лежит в своей папке)
    if delete_app_folder and is_frozen() and app_dir.exists():
        lines.append("timeout /t 1 /nobreak >nul")
        lines.append(f'cd /D "%TEMP%"')
        lines.append(f'rmdir /S /Q "{app_dir}" 2>nul')

    lines.append("echo.")
    lines.append("echo PLANA_DP удалён.")
    lines.append("timeout /t 2 /nobreak >nul")

    # Само-удаление .bat
    lines.append(f'del /F /Q "%~f0"')

    bat_path = Path(tempfile.gettempdir()) / "plana_dp_uninstall.bat"
    bat_path.write_text("\r\n".join(lines), encoding="utf-8")
    return bat_path


class UninstallWorker(QObject):
    """
    Пишет .bat и запускает его в отдельном окне.
    Приложение после этого должно само вызвать sys.exit().
    """

    log = Signal(str)
    error = Signal(str)
    finished = Signal(bool)

    def __init__(self, delete_downloads=False, delete_app_folder=True):
        super().__init__()
        self.delete_downloads = bool(delete_downloads)
        self.delete_app_folder = bool(delete_app_folder)

    @Slot()
    def run(self):
        try:
            bat = _build_bat(self.delete_downloads, self.delete_app_folder)
            self.log.emit(f"Uninstaller: {bat}")

            if sys.platform.startswith("win"):
                subprocess.Popen(
                    ["cmd", "/c", str(bat)],
                    creationflags=subprocess.CREATE_NEW_CONSOLE,
                    close_fds=True,
                )
            else:
                subprocess.Popen(["/bin/sh", str(bat)], close_fds=True)

            self.finished.emit(True)

        except Exception as exc:
            self.error.emit(f"Ошибка деинсталлятора: {exc}")
            self.finished.emit(False)
