import json
import urllib.error
import urllib.request
from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot

from config import APP_VERSION, GITHUB_REPO


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


class DownloadWorker(QObject):
    """
    Скачивает файл обновления в папку Downloads пользователя.
    progress: (downloaded_bytes, total_bytes)
    result: str (путь к скачанному файлу)
    """

    progress = Signal(int, int)
    result = Signal(str)
    error = Signal(str)
    log = Signal(str)
    finished = Signal()

    def __init__(self, url, filename=""):
        super().__init__()
        self.url = url
        self.filename = filename

    @Slot()
    def run(self):
        try:
            if not self.url:
                self.error.emit("URL файла обновления пуст.")
                self.finished.emit()
                return

            downloads = Path.home() / "Downloads"
            downloads.mkdir(parents=True, exist_ok=True)

            fname = (
                self.filename
                or self.url.rstrip("/").split("/")[-1]
                or "PLANA_DP_update"
            )
            target = downloads / fname

            self.log.emit(f"Скачиваю обновление: {self.url}")

            req = urllib.request.Request(
                self.url,
                headers={"User-Agent": "PLANA_DP-Updater"},
            )
            with urllib.request.urlopen(req, timeout=120) as resp:
                total = int(resp.headers.get("Content-Length") or 0)
                downloaded = 0
                chunk_size = 64 * 1024

                with open(target, "wb") as fp:
                    while True:
                        chunk = resp.read(chunk_size)
                        if not chunk:
                            break
                        fp.write(chunk)
                        downloaded += len(chunk)
                        try:
                            self.progress.emit(downloaded, total)
                        except Exception:
                            pass

            self.log.emit(f"Сохранено: {target}")
            self.result.emit(str(target))

        except Exception as exc:
            self.error.emit(f"Ошибка загрузки: {exc}")

        finally:
            self.finished.emit()
