from PySide6.QtCore import QObject, Signal, Slot

from core.mgeko import MgekoClient


class MangaWorker(QObject):
    result = Signal(object)
    cover = Signal(bytes)

    error = Signal(str)
    log = Signal(str)
    finished = Signal()

    def __init__(self, url):
        super().__init__()
        self.url = url

    @Slot()
    def run(self):
        client = MgekoClient(self.log.emit)

        try:
            client.start()

            manga = client.get_manga(self.url)

            self.result.emit(manga)

            # ---------------------------------------------
            # COVER
            # ---------------------------------------------

            if not manga.cover_url:
                self.log.emit("Обложка не найдена на странице тайтла.")
            else:
                self.log.emit(f"Скачиваю обложку: {manga.cover_url}")

                data = self._download_cover(client, manga.cover_url, manga.url)

                if data:
                    self.cover.emit(data)
                    self.log.emit(f"Обложка получена: {len(data)} байт.")
                else:
                    self.log.emit("Не удалось скачать обложку.")

        except Exception as exc:
            self.error.emit(str(exc))

        finally:
            client.close()
            self.finished.emit()

    @staticmethod
    def _download_cover(client, cover_url, referer):
        """
        Скачивает обложку с двумя попытками.
        """
        for attempt in (1, 2):
            try:
                response = client.context.request.get(
                    cover_url,
                    headers={
                        "Referer": referer,
                        "Accept": (
                            "image/avif,image/webp,image/apng,"
                            "image/svg+xml,image/*,*/*;q=0.8"
                        ),
                    },
                    timeout=30_000,
                )

                if response.ok:
                    body = response.body()
                    if body:
                        return body

            except Exception:
                pass

        return None
