import re
from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot


IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}

# Минимальная уверенность OCR (0..1). Ниже 0.20 RapidOCR выдаёт мусор.
MIN_CONFIDENCE = 0.25

# Пиксельное расстояние между рамками, при котором они считаются одним баблом.
BUBBLE_GAP_PX = 60

# Допуск по Y для сборки строк внутри бабла.
LINE_TOLERANCE_PX = 25

# Латинских букв минимум, чтобы считать текст английским.
ENGLISH_RE = re.compile(r"[A-Za-z]{2,}")

# Слабые (построчные) маркеры мусора
WATERMARK_PATTERNS = [
    r"\bELF\s*TOON\b",
    r"\bELFTOON\b",
    r"\.com\b",
    r"\.gg\b",
    r"https?://",
    r"\bDISCORD\b",
    r"\bREAD\s+(?:THIS\s+)?CHAPTER\b",
    r"\bREADING\s+THIS\b",
    r"\bON\s+OUR\s+WEBSITE\b",
    r"\bJOIN\s+OUR\b",
    r"\bTHANK\s+YOU\s+FOR\s+READING\b",
    r"\bPLEASE\s+READ\b",
    r"\bSUPPORT\s+US\b",
    r"\bSCAN\s+(?:GROUP|LATION)\b",
    r"\bDON'?T\s+HESITATE\b",
]
WATERMARK_RE = re.compile("|".join(WATERMARK_PATTERNS), re.IGNORECASE)

# Сильные маркеры — если такие есть в бабле, выкидываем весь бабл.
STRONG_WATERMARK_RE = re.compile(
    r"\bELF\s*TOON\b|\.com\b|\.gg\b|https?://|\bDISCORD\b",
    re.IGNORECASE,
)

# Опциональный сплиттер слипшихся слов.
try:
    import wordninja  # pip install wordninja

    _HAS_WORDNINJA = True
except Exception:
    _HAS_WORDNINJA = False


# ============================================================
# HELPERS
# ============================================================


def natural_sort_key(name):
    """001.jpg < 002.jpg < ... < 010.jpg"""
    return [int(c) if c.isdigit() else c.lower() for c in re.split(r"(\d+)", name)]


def is_english_line(line):
    return bool(ENGLISH_RE.search(line or ""))


def is_watermark(line):
    return bool(WATERMARK_RE.search(line or ""))


def is_strong_watermark(text):
    return bool(STRONG_WATERMARK_RE.search(text or ""))


def _maybe_split_merged(text):
    """
    Разбивает одиночное «слово» без пробелов, если оно длинное (>10 симв.).
    Работает только при установленном wordninja; иначе возвращает как есть.
    """
    if not _HAS_WORDNINJA or not text:
        return text
    if " " in text or "\n" in text:
        return text
    if not re.fullmatch(r"[A-Za-z0-9]+", text):
        return text
    if len(text) < 10:
        return text
    try:
        parts = wordninja.split(text.lower())
    except Exception:
        return text
    if len(parts) <= 1:
        return text
    if text.isupper():
        return " ".join(p.upper() for p in parts)
    if text.islower():
        return " ".join(parts)
    return " ".join(p.capitalize() for p in parts)


# ============================================================
# WORKER
# ============================================================


class OcrWorker(QObject):
    """
    Проходит по всем изображениям в папке, распознаёт английский текст,
    группирует его в «баблы» и пишет в один .txt в той же папке.

    Signals:
      progress(int, int, str) — (сделано, всего, имя_файла)
      log(str)                — сообщение в лог
      result(str)             — путь к записанному .txt
      error(str)              — ошибка
      finished()              — воркер завершил работу
    """

    progress = Signal(int, int, str)
    log = Signal(str)
    result = Signal(str)
    error = Signal(str)
    finished = Signal()

    def __init__(self, folder, output_name="chapter_text.txt", lang="en"):
        super().__init__()
        self.folder = Path(folder)
        self.output_name = output_name or "chapter_text.txt"
        self.lang = lang or "en"
        self._stop = False
        self._engine = None

    @Slot()
    def stop(self):
        self._stop = True

    # =========================================================
    # ENGINE
    # =========================================================

    def _load_engine(self):
        if self._engine is not None:
            return self._engine

        self.log.emit("Загружаю OCR-движок...")

        try:
            from rapidocr_onnxruntime import RapidOCR

            self._engine = ("rapidocr", RapidOCR())
            self.log.emit("Движок: RapidOCR (onnxruntime)")
            return self._engine
        except ImportError:
            self.log.emit("RapidOCR не установлен — пробую EasyOCR.")
        except Exception as exc:
            self.log.emit(f"RapidOCR не запустился: {exc}")

        try:
            import easyocr

            langs = ["en"] if self.lang == "en" else [self.lang, "en"]
            self._engine = ("easyocr", easyocr.Reader(langs, gpu=False))
            self.log.emit(f"Движок: EasyOCR ({langs})")
            return self._engine
        except ImportError:
            self.log.emit("EasyOCR не установлен — пробую Tesseract.")
        except Exception as exc:
            self.log.emit(f"EasyOCR не запустился: {exc}")

        try:
            import pytesseract

            pytesseract.get_tesseract_version()
            self._engine = ("pytesseract", pytesseract)
            self.log.emit("Движок: Tesseract")
            return self._engine
        except Exception as exc:
            self.log.emit(f"Tesseract недоступен: {exc}")

        return None

    # =========================================================
    # BUBBLE EXTRACTION
    # =========================================================

    def _extract_bubbles(self, image_path):
        """Возвращает список строк-баблов (уже склеенных через пробел)."""
        name, engine = self._engine

        if name == "rapidocr":
            result, _ = engine(str(image_path))
            if not result:
                return []
            return self._bubbles_from_boxes(result)

        if name == "easyocr":
            results = engine.readtext(str(image_path))
            return self._bubbles_from_boxes(results)

        if name == "pytesseract":
            from PIL import Image

            text = engine.image_to_string(Image.open(image_path), lang="eng")
            # Tesseract не даёт координат — каждая строка = отдельный бабл
            return [ln.strip() for ln in text.splitlines() if ln.strip()]

        return []

    @staticmethod
    def _bubbles_from_boxes(raw_items):
        """
        raw_items: [(box, text, confidence), ...]
        Возвращает список склеенных баблов.
        """
        parsed = []
        for box, text, conf in raw_items:
            try:
                conf = float(conf)
            except Exception:
                conf = 1.0
            if conf < MIN_CONFIDENCE:
                continue

            text = _maybe_split_merged((text or "").strip())
            if not text:
                continue

            try:
                xs = [float(p[0]) for p in box]
                ys = [float(p[1]) for p in box]
            except Exception:
                continue

            x1, x2 = min(xs), max(xs)
            y1, y2 = min(ys), max(ys)
            parsed.append(
                {
                    "x1": x1,
                    "x2": x2,
                    "y1": y1,
                    "y2": y2,
                    "cx": (x1 + x2) / 2.0,
                    "cy": (y1 + y2) / 2.0,
                    "text": text,
                }
            )

        if not parsed:
            return []

        # -------- кластеризация в баблы (union-find) --------
        n = len(parsed)
        parent = list(range(n))

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a, b):
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb

        for i in range(n):
            a = parsed[i]
            for j in range(i + 1, n):
                b = parsed[j]
                h_gap = max(0.0, a["x1"] - b["x2"], b["x1"] - a["x2"])
                v_gap = max(0.0, a["y1"] - b["y2"], b["y1"] - a["y2"])
                if (h_gap * h_gap + v_gap * v_gap) ** 0.5 < BUBBLE_GAP_PX:
                    union(i, j)

        groups = {}
        for i in range(n):
            r = find(i)
            groups.setdefault(r, []).append(parsed[i])

        # -------- сборка строк внутри бабла --------
        result = []
        for group in groups.values():
            group.sort(key=lambda it: (it["cy"], it["cx"]))

            line_groups = []
            current = [group[0]]
            current_y = group[0]["cy"]
            for item in group[1:]:
                if abs(item["cy"] - current_y) < LINE_TOLERANCE_PX:
                    current.append(item)
                    current_y = sum(it["cy"] for it in current) / len(current)
                else:
                    line_groups.append(current)
                    current = [item]
                    current_y = item["cy"]
            line_groups.append(current)

            line_texts = []
            for lg in line_groups:
                lg.sort(key=lambda it: it["cx"])
                line_texts.append(" ".join(it["text"] for it in lg))

            # сильный маркер — выкидываем весь бабл
            if is_strong_watermark(" ".join(line_texts)):
                continue

            # построчная чистка
            line_texts = [ln for ln in line_texts if not is_watermark(ln)]
            if not line_texts:
                continue

            bubble_text = " ".join(line_texts).strip()
            if not bubble_text or not is_english_line(bubble_text):
                continue

            top_y = min(it["y1"] for it in group)
            left_x = min(it["x1"] for it in group)
            result.append((top_y, left_x, bubble_text))

        # -------- порядок баблов: сверху-вниз, слева-направо --------
        result.sort(key=lambda t: (t[0], t[1]))
        return [t[2] for t in result]

    # =========================================================
    # MAIN
    # =========================================================

    def run(self):
        try:
            if not self.folder.is_dir():
                self.error.emit(f"Папка не найдена:\n{self.folder}")
                return

            images = sorted(
                [
                    p
                    for p in self.folder.iterdir()
                    if p.is_file() and p.suffix.lower() in IMAGE_EXTS
                ],
                key=lambda p: natural_sort_key(p.name),
            )

            if not images:
                self.error.emit(
                    f"В папке нет изображений ({', '.join(sorted(IMAGE_EXTS))}):\n"
                    f"{self.folder}"
                )
                return

            self.log.emit(f"Найдено изображений: {len(images)}")
            if not _HAS_WORDNINJA:
                self.log.emit(
                    "wordninja не установлен — слипшиеся слова не разделяются. "
                    "Установите: pip install wordninja"
                )

            if self._load_engine() is None:
                self.error.emit(
                    "Не найден ни один OCR-движок.\n\n"
                    "Установите один из:\n"
                    "  pip install rapidocr-onnxruntime\n"
                    "  pip install easyocr\n"
                    "  pip install pytesseract  (+ бинарник Tesseract)"
                )
                return

            total = len(images)
            blocks = []
            processed = 0

            for index, image in enumerate(images, start=1):
                if self._stop:
                    self.log.emit("Остановлено пользователем.")
                    return

                self.progress.emit(index - 1, total, image.name)

                try:
                    bubbles = self._extract_bubbles(image)
                except Exception as exc:
                    self.log.emit(f"[{index}/{total}] {image.name} — ошибка: {exc}")
                    bubbles = []

                if bubbles:
                    body = "\n\n".join(bubbles)
                else:
                    body = "(английский текст не найден)"

                blocks.append(f"=== {image.name} ===\n{body}")
                processed += 1

                self.log.emit(
                    f"[{index}/{total}] {image.name} — баблов: {len(bubbles)}"
                )
                self.progress.emit(index, total, image.name)

            if self._stop:
                self.log.emit("Остановлено до записи файла.")
                return

            full_text = "\n\n".join(blocks) + "\n"
            output_path = self.folder / self.output_name
            output_path.write_text(full_text, encoding="utf-8")

            self.log.emit(f"Готово. Обработано страниц: {processed}")
            self.log.emit(f"Файл записан: {output_path}")
            self.result.emit(str(output_path))

        except Exception as exc:
            self.error.emit(f"Ошибка OCR: {exc}")

        finally:
            self.finished.emit()
