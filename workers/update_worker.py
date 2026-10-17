import json
import os
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot

from config import APP_VERSION, GITHUB_REPO
from paths import app_root, is_frozen


API_LATEST = "https://api.github.com/repos/{repo}/releases/latest"


def _version_tuple(v):
    v = (v or "").strip().lstrip("vV")
    parts = []
    for p in v.split("."):
        try:
            parts.append(int(p))
        except ValueError:
            parts.append(0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:4])


def _is_newer(latest, current):
    return _version_tuple(latest) > _version_tuple(current)


class UpdateWorker(QObject):
    """
    Проверяет релизы на GitHub.
    result: dict | None
    """

    result = Signal(object)
    error = Signal(str)
    log = Signal(str)
    finished = Signal()

    def __init__(self, repo=GITHUB_REPO, current=APP_VERSION):
        super().__init__()
        self.repo = repo
        self.current = current

    @Slot()
    def run(self):
        try:
            if not self.repo or "/" not in self.repo or self.repo.startswith("your-"):
                self.error.emit(
                    "GitHub-репозиторий не настроен.\n"
                    "Открой config.py и укажи GITHUB_REPO = "
                    "'владелец/репозиторий'."
                )
                self.finished.emit()
                return

            url = API_LATEST.format(repo=self.repo)
            self.log.emit(f"Проверяю обновления: {url}")

            req = urllib.request.Request(
                url,
                headers={
                    "Accept": "application/vnd.github+json",
                    "User-Agent": "PLANA_DP-Updater",
                },
            )

            try:
                with urllib.request.urlopen(req, timeout=20) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                if exc.code == 404:
                    self.log.emit("На GitHub пока нет ни одного релиза.")
                    self.result.emit(
                        {
                            "has_update": False,
                            "current": self.current,
                            "latest": "",
                            "name": "",
                            "notes": "",
                            "html_url": f"https://github.com/{self.repo}",
                            "asset_url": "",
                            "asset_name": "",
                            "published_at": "",
                            "no_releases": True,
                        }
                    )
                    self.finished.emit()
                    return
                raise

            tag = (data.get("tag_name") or "").strip()
            name = (data.get("name") or "").strip()
            body = (data.get("body") or "").strip()
            html_url = data.get("html_url") or ""
            published = data.get("published_at") or ""

            asset_url = ""
            asset_name = ""
            for a in data.get("assets", []) or []:
                name_a = (a.get("name") or "").lower()
                if name_a.endswith(".exe") or name_a.endswith(".zip"):
                    asset_url = a.get("browser_download_url") or ""
                    asset_name = a.get("name") or ""
                    break

            if not tag:
                self.error.emit("GitHub не вернул tag_name релиза.")
                self.finished.emit()
                return

            has_update = _is_newer(tag, self.current)

            self.log.emit(
                f"Текущая: {self.current} | Последняя: {tag} | "
                f"Обновление: {'да' if has_update else 'нет'}"
            )

            self.result.emit(
                {
                    "has_update": has_update,
                    "current": self.current,
                    "latest": tag,
                    "name": name,
                    "notes": body,
                    "html_url": html_url,
                    "asset_url": asset_url,
                    "asset_name": asset_name,
                    "published_at": published,
                    "no_releases": False,
                }
            )

        except Exception as exc:
            self.error.emit(f"Ошибка проверки обновлений: {exc}")

        finally:
            self.finished.emit()


class ApplyUpdateWorker(QObject):
    """
    Автообновление: скачивает релиз, готовит .bat, запускает его,
    приложение закрывается — .bat заменяет файлы на диске и
    перезапускает PLANA_DP с того же места.

    Поддерживает два типа сборки (определяется автоматически):
      - onefile  — рядом с .exe нет папки _internal
      - folder   — рядом с .exe есть _internal

    Signals:
      progress(int, int) — (скачано байт, всего байт)
      log(str)           — сообщение в лог
      error(str)         — ошибка
      ready()            — файлы готовы, .bat запущен, можно закрывать приложение
      finished()         — воркер завершил работу
    """

    progress = Signal(int, int)
    log = Signal(str)
    error = Signal(str)
    ready = Signal()
    finished = Signal()

    def __init__(self, asset_url, asset_name=""):
        super().__init__()
        self.asset_url = asset_url
        self.asset_name = asset_name
        self._stop = False

    @Slot()
    def stop(self):
        self._stop = True

    @Slot()
    def run(self):
        try:
            if not is_frozen():
                self.error.emit(
                    "Приложение запущено из исходников (python main.py).\n"
                    "Автообновление работает только для .exe-сборки."
                )
                return

            if not sys.platform.startswith("win"):
                self.error.emit("Автообновление поддерживается только на Windows.")
                return

            if not self.asset_url:
                self.error.emit("URL файла обновления пуст.")
                return

            app_dir = app_root()
            exe_path = Path(sys.executable).resolve()
            exe_name = exe_path.name
            pid = os.getpid()
            is_folder_build = (app_dir / "_internal").is_dir()

            self.log.emit(
                f"Режим обновления: {'folder' if is_folder_build else 'onefile'}"
            )
            self.log.emit(f"Папка приложения: {app_dir}")

            tmp_dir = Path(tempfile.mkdtemp(prefix="plana_update_"))
            self.log.emit(f"Временная папка: {tmp_dir}")

            # ---------- 1. Скачать ----------
            filename = (
                self.asset_name
                or self.asset_url.rstrip("/").split("/")[-1]
                or "PLANA_DP_update"
            )
            archive = tmp_dir / filename

            if not self._download(archive):
                # отменено пользователем
                self._cleanup(tmp_dir)
                return

            # ---------- 2. Подготовить источник ----------
            source, source_is_folder = self._prepare_source(archive, tmp_dir, exe_name)
            self.log.emit(
                f"Источник: {source} ({'папка' if source_is_folder else 'файл'})"
            )

            if is_folder_build and not source_is_folder:
                self.error.emit(
                    "Установлена folder-сборка, а в обновлении только .exe.\n"
                    "Прикрепите к релизу .zip с содержимым папки dist/PLANA_DP/."
                )
                self._cleanup(tmp_dir)
                return

            if not is_folder_build and source_is_folder:
                # onefile-сборка, а в zip — папка: извлекаем только .exe
                candidate = source / exe_name
                if not candidate.exists():
                    exes = list(source.rglob("*.exe"))
                    if not exes:
                        self.error.emit("В архиве не найден .exe.")
                        self._cleanup(tmp_dir)
                        return
                    candidate = exes[0]
                source = candidate
                source_is_folder = False
                self.log.emit(f"Извлекаю только .exe: {source}")

            # ---------- 3. Сгенерировать .bat ----------
            bat = self._build_bat(
                tmp_dir, source, source_is_folder, app_dir, exe_path, pid
            )
            self.log.emit(f"Скрипт обновления: {bat}")

            # ---------- 4. Запустить .bat ----------
            subprocess.Popen(
                ["cmd", "/c", str(bat)],
                creationflags=subprocess.CREATE_NEW_CONSOLE,
                close_fds=True,
            )

            self.log.emit("Скрипт запущен, приложение может закрываться.")
            self.ready.emit()

        except Exception as exc:
            self.error.emit(f"Ошибка автообновления: {exc}")

        finally:
            self.finished.emit()

    # =========================================================
    # DOWNLOAD
    # =========================================================

    def _download(self, target):
        self.log.emit(f"Скачиваю: {self.asset_url}")
        req = urllib.request.Request(
            self.asset_url,
            headers={"User-Agent": "PLANA_DP-Updater"},
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            total = int(resp.headers.get("Content-Length") or 0)
            done = 0
            with open(target, "wb") as fp:
                while True:
                    if self._stop:
                        self.log.emit("Загрузка отменена пользователем.")
                        try:
                            if target.exists():
                                target.unlink()
                        except Exception:
                            pass
                        return False
                    chunk = resp.read(64 * 1024)
                    if not chunk:
                        break
                    fp.write(chunk)
                    done += len(chunk)
                    self.progress.emit(done, total)
        return True

    # =========================================================
    # SOURCE PREPARATION
    # =========================================================

    def _prepare_source(self, archive, tmp_dir, exe_name):
        """
        Возвращает (source_path, source_is_folder).
        Если архив содержит _internal — это folder-сборка.
        Иначе — ищем .exe (onefile).
        """
        suffix = archive.suffix.lower()

        if suffix == ".zip":
            extract = tmp_dir / "new"
            extract.mkdir()
            self.log.emit("Распаковываю архив...")
            with zipfile.ZipFile(archive) as z:
                z.extractall(extract)

            internal_dirs = list(extract.rglob("_internal"))
            if internal_dirs:
                folder_root = internal_dirs[0].parent
                self.log.emit(f"Folder-сборка найдена: {folder_root}")
                return folder_root, True

            exes = list(extract.rglob("*.exe"))
            if not exes:
                raise RuntimeError("В архиве не найден ни _internal, ни .exe-файл.")
            # если несколько exe — берём тот, что совпадает по имени, иначе первый
            chosen = next(
                (p for p in exes if p.name == exe_name),
                exes[0],
            )
            return chosen, False

        if suffix == ".exe":
            return archive, False

        raise RuntimeError(f"Неподдерживаемый формат файла обновления: {suffix}")

    # =========================================================
    # BAT GENERATION
    # =========================================================

    def _build_bat(self, tmp_dir, source, source_is_folder, app_dir, exe_path, pid):
        lines = [
            "@echo off",
            "chcp 65001 >nul",
            "title PLANA_DP Updater",
            "echo.",
            "echo Обновление PLANA_DP...",
            "echo.",
            "",
            "REM даём приложению шанс закрыться штатно",
            "timeout /t 2 /nobreak >nul",
            "",
            "REM ждём завершения процесса по PID (до 30 секунд)",
            "set /a waited=0",
            ":waitloop",
            f'tasklist /FI "PID eq {pid}" 2>nul | find /I "{exe_path.name}" >nul',
            "if errorlevel 1 goto after_wait",
            "timeout /t 1 /nobreak >nul",
            "set /a waited+=1",
            "if %waited% LSS 30 goto waitloop",
            "echo Приложение не закрылось за 30 секунд — завершаю принудительно.",
            f"taskkill /F /PID {pid} >nul 2>&1",
            "timeout /t 2 /nobreak >nul",
            "",
            ":after_wait",
        ]

        if source_is_folder:
            # folder build: полная перезапись содержимого
            lines += [
                f'robocopy "{source}" "{app_dir}" /E /IS /IT /NFL /NDL /NJH /NJS /NC /NS >nul',
                "if errorlevel 8 goto fail",
            ]
        else:
            # onefile: заменяем только .exe
            lines += [
                f'copy /Y "{source}" "{exe_path}" >nul',
                "if errorlevel 1 goto fail",
            ]

        lines += [
            "",
            "REM запускаем новую версию с того же места",
            f'start "" "{exe_path}"',
            "",
            "REM самоудаление",
            'del /F /Q "%~f0" >nul 2>&1',
            "exit /b 0",
            "",
            ":fail",
            "echo.",
            "echo ОШИБКА: не удалось заменить файлы.",
            "echo Возможные причины:",
            "echo   - нет прав на запись в папку приложения",
            "echo   - антивирус блокирует замену",
            "echo   - файл всё ещё занят другим процессом",
            "echo.",
            "echo Старая версия осталась на месте.",
            "pause",
            "exit /b 1",
        ]

        bat = tmp_dir / "plana_update.bat"
        bat.write_text("\r\n".join(lines), encoding="utf-8")
        return bat

    # =========================================================
    # CLEANUP
    # =========================================================

    @staticmethod
    def _cleanup(tmp_dir):
        try:
            import shutil

            shutil.rmtree(tmp_dir, ignore_errors=True)
        except Exception:
            pass
