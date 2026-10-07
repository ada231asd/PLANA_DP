from pathlib import Path
import re

from PySide6.QtCore import QObject, Signal, Slot

from storage import load_settings
from core.mgeko import MgekoClient


def safe_name(value):
    value = re.sub(r'[<>:"/\\|?*]', "_", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value[:150] or "Untitled"


class DownloadWorker(QObject):
    progress = Signal(int, int, str)
    chapter_started = Signal(str)
    log = Signal(str)
    error = Signal(str)
    finished = Signal()

    def __init__(self, manga_title, chapters):
        super().__init__()
        self.manga_title = manga_title
        self.chapters = chapters
        self._stop = False

    def stop(self):
        self._stop = True

    @Slot()
    def run(self):
        client = MgekoClient(self.log.emit)
        try:
            client.start()

            settings = load_settings()
            download_dir = Path(settings.get("download_dir", "downloads"))

            total_chapters = len(self.chapters)

            for chapter_index, chapter in enumerate(self.chapters, start=1):
                if self._stop:
                    break

                self.chapter_started.emit(f"Глава {chapter.number}")
                self.log.emit(f"Получаю страницы главы {chapter.number}...")

                image_urls = client.get_chapter_images(chapter.url)
                if not image_urls:
                    self.error.emit(f"В главе {chapter.number} не найдены изображения.")
                    continue

                chapter_dir = (
                    download_dir
                    / safe_name(self.manga_title)
                    / ("Chapter " + safe_name(chapter.number))
                )
                chapter_dir.mkdir(parents=True, exist_ok=True)

                count = len(image_urls)

                for image_index, image_url in enumerate(image_urls, start=1):
                    if self._stop:
                        break

                    suffix = Path(image_url.split("?", 1)[0]).suffix.lower() or ".jpg"
                    destination = chapter_dir / f"{image_index:03d}{suffix}"

                    self.progress.emit(
                        chapter_index - 1,
                        total_chapters,
                        f"Глава {chapter.number}: {image_index}/{count}",
                    )

                    client.download_image(image_url, destination, chapter.url)

                self.progress.emit(
                    chapter_index,
                    total_chapters,
                    f"Глава {chapter.number}: готово",
                )

        except Exception as exc:
            self.error.emit(str(exc))
        finally:
            client.close()
            self.finished.emit()
