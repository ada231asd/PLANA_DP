import re

from PySide6.QtCore import QObject, Signal, Slot


_CACHE = {}
_HAS_LATIN = re.compile(r"[A-Za-z]")


def _get_translator():
    from deep_translator import GoogleTranslator

    return GoogleTranslator(source="auto", target="ru")


def _translate_one(translator, text):
    """Возвращает (result, ok, error)."""
    if not text or not str(text).strip():
        return text, True, ""

    raw = str(text)
    key = raw.strip().lower()[:200]

    if key in _CACHE:
        return _CACHE[key], True, ""

    try:
        result = translator.translate(raw)
    except Exception as exc:
        return raw, False, f"{type(exc).__name__}: {exc}"

    if not result:
        return raw, False, "пустой ответ переводчика"

    _CACHE[key] = result
    return result, True, ""


class TranslateWorker(QObject):
    result = Signal(dict)
    error = Signal(str)
    log = Signal(str)
    finished = Signal()

    def __init__(self, fields):
        super().__init__()
        self.fields = dict(fields or {})

    @Slot()
    def run(self):
        try:
            translator = _get_translator()
        except Exception as exc:
            self.error.emit(
                "Не удалось инициализировать переводчик.\n"
                "Установите: pip install deep-translator\n\n"
                f"Ошибка: {exc}"
            )
            self.finished.emit()
            return

        out = {}
        errors = []
        success = 0

        for key, value in self.fields.items():
            if not value:
                out[key] = value
                continue

            if isinstance(value, list):
                lst = []
                for v in value:
                    res, ok, err = _translate_one(translator, v)
                    lst.append(res)
                    if ok:
                        success += 1
                    elif err:
                        errors.append(err)
                out[key] = lst
            else:
                res, ok, err = _translate_one(translator, str(value))
                out[key] = res
                if ok:
                    success += 1
                elif err:
                    errors.append(err)

        if success == 0:
            detail = ""
            if errors:
                detail = "\n" + "\n".join(f"• {e}" for e in errors[:3])
            self.error.emit(
                "Перевод не удался ни для одного поля.\n"
                "Проверьте интернет-соединение." + detail
            )
            self.finished.emit()
            return

        self.result.emit(out)
        self.finished.emit()
