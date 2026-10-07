import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

from PySide6.QtCore import QObject, Signal, Slot


# ============================================================
# КЕШ (в памяти процесса)
# ============================================================

_CACHE = {}
_LATIN = re.compile(r"[A-Za-z]")


def _has_latin(text):
    return bool(_LATIN.search(text or ""))


# ============================================================
# LINGVA TRANSLATE — публичные зеркала Google Translate
# ============================================================

LINGVA_INSTANCES = [
    "lingva.ml",
    "lingva.garudalinux.org",
    "translate.plausibility.cloud",
    "lingva.lunar.icu",
    "lingva.thedaviddelta.com",
]

_LINGVA_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:131.0) Gecko/20100101 Firefox/131.0"
)


def _lingva_request(instance, text, source, target, timeout=10):
    url = (
        f"https://{instance}/api/v1/"
        f"{urllib.parse.quote(source)}/{urllib.parse.quote(target)}/"
        f"{urllib.parse.quote(text)}"
    )
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": _LINGVA_UA,
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return (data.get("translation") or "").strip()


def _translate_lingva(text, source="auto", target="ru", max_attempts=2):
    """Пробует несколько зеркал Lingva. Возвращает перевод или None."""
    if not text or not text.strip():
        return ""

    for attempt in range(max_attempts):
        for instance in LINGVA_INSTANCES:
            try:
                result = _lingva_request(instance, text, source, target)
                if result:
                    return result
            except Exception:
                continue
        # если все зеркала отвалились — короткая пауза и пробуем ещё раз
        if attempt < max_attempts - 1:
            time.sleep(0.5)

    return None


# ============================================================
# MYMEMORY — fallback через deep-translator
# ============================================================


def _translate_mymemory(text, source="en", target="ru"):
    if not text or not text.strip():
        return ""

    try:
        from deep_translator import MyMemoryTranslator

        translator = MyMemoryTranslator(source=source, target=target)
        result = translator.translate(text)
        if result:
            return result.strip()
    except Exception:
        pass

    return None


# ============================================================
# ОБЩИЙ ПЕРЕВОДЧИК (сначала Lingva, потом MyMemory)
# ============================================================


def _translate_one(text, source="auto", target="ru"):
    """
    Возвращает (перевод, движок) или (None, "").
    """
    result = _translate_lingva(text, source=source, target=target)
    if result:
        return result, "lingva"

    # MyMemory требует явный source (en/ru и т.п., не auto)
    mm_source = source if source != "auto" else "en"
    result = _translate_mymemory(text, source=mm_source, target=target)
    if result:
        return result, "mymemory"

    return None, ""


# ============================================================
# БАТЧ-ПЕРЕВОД С ПАРАЛЛЕЛЬНОСТЬЮ
# ============================================================


def _translate_many(texts, source="auto", target="ru", max_workers=4):
    """Параллельно переводит список строк. Возвращает dict {src: dst}."""
    results = {}

    if not texts:
        return results

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_translate_one, t, source, target): t for t in texts}
        for future in as_completed(futures):
            src = futures[future]
            try:
                dst, engine = future.result()
                if dst:
                    results[src] = dst
            except Exception:
                pass

    return results


# ============================================================
# WORKER
# ============================================================


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
        # ----- 1. Собираем уникальные строки к переводу -----
        unique = []
        seen = set()

        def _add(text):
            if not text:
                return
            s = str(text).strip()
            if not s or not _has_latin(s):
                return
            if s in seen:
                return
            seen.add(s)
            unique.append(s)

        for value in self.fields.values():
            if isinstance(value, list):
                for v in value:
                    _add(v)
            else:
                _add(value)

        # ----- 2. Что уже в кеше -----
        to_fetch = []
        for s in unique:
            ck = s.lower()[:200]
            if ck not in _CACHE:
                to_fetch.append(s)

        self.log.emit(
            f"Перевод: строк {len(unique)}, "
            f"в кеше {len(unique) - len(to_fetch)}, "
            f"к переводу {len(to_fetch)}"
        )

        # ----- 3. Переводим всё разом -----
        if to_fetch:
            translated_map = _translate_many(to_fetch)

            for src in to_fetch:
                ck = src.lower()[:200]
                if src in translated_map:
                    _CACHE[ck] = translated_map[src]
                else:
                    # помечаем в кеше как "не удалось", чтобы не долбить
                    # повторно каждую секунду
                    _CACHE[ck] = src

        # ----- 4. Собираем результат -----
        def _T(text):
            if not text or not _has_latin(text):
                return text
            ck = str(text).strip().lower()[:200]
            return _CACHE.get(ck, text)

        result = {}
        for key, value in self.fields.items():
            if isinstance(value, list):
                result[key] = [_T(v) for v in value]
            else:
                result[key] = _T(value)

        # ----- 5. Проверяем, что вообще что-то переведено -----
        if to_fetch:
            changed = 0
            for key, original in self.fields.items():
                translated = result.get(key)
                if isinstance(original, list):
                    if original != translated:
                        changed += 1
                else:
                    if original != translated:
                        changed += 1

            if changed == 0:
                self.error.emit(
                    "Перевод не удался.\n\n"
                    "Все публичные серверы перевода недоступны "
                    "или заблокированы.\n\n"
                    "Проверьте интернет-соединение и повторите позже."
                )
                self.finished.emit()
                return

        self.result.emit(result)
        self.finished.emit()
