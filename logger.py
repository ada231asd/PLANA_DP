import threading
from collections import deque
from datetime import datetime

from PySide6.QtCore import QObject, Signal

from paths import get_data_dir


MAX_LINES = 5000


def _log_file():
    d = get_data_dir() / "logs"
    try:
        d.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    return d / "app.log"


class AppLogger(QObject):
    message = Signal(str)
    cleared = Signal()

    _instance = None

    def __init__(self):
        super().__init__()
        self._buffer = deque(maxlen=MAX_LINES)
        self._lock = threading.Lock()

    @classmethod
    def instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def write(self, text):
        line = str(text).rstrip("\n")

        with self._lock:
            self._buffer.append(line)

        try:
            stamp = datetime.now().strftime("%H:%M:%S")
            with open(_log_file(), "a", encoding="utf-8") as fp:
                fp.write(f"[{stamp}] {line}\n")
        except Exception:
            pass

        try:
            self.message.emit(line)
        except Exception:
            pass

    def lines(self):
        with self._lock:
            return list(self._buffer)

    def clear(self):
        with self._lock:
            self._buffer.clear()
        try:
            self.cleared.emit()
        except Exception:
            pass

    def export(self, path):
        try:
            from pathlib import Path

            Path(path).write_text(
                "\n".join(self.lines()),
                encoding="utf-8",
            )
            return True
        except Exception:
            return False


app_logger = AppLogger.instance()
