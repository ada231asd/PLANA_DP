from PySide6.QtCore import QObject, Signal, Slot

from core.mgeko import MgekoClient


class SearchWorker(QObject):
    results = Signal(object)
    error = Signal(str)
    log = Signal(str)
    finished = Signal()

    def __init__(self, query, enrich=True, preview_limit=12):
        super().__init__()
        self.query = query
        self.enrich = enrich
        self.preview_limit = preview_limit

    @Slot()
    def run(self):
        client = MgekoClient(self.log.emit)

        try:
            client.start()

            if self.enrich:
                results = client.search_with_previews(
                    self.query,
                    limit=self.preview_limit,
                )
            else:
                results = client.search(self.query)

            self.results.emit(results)

        except Exception as exc:
            self.error.emit(str(exc))

        finally:
            client.close()
            self.finished.emit()
