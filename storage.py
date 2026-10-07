import json
import re
import shutil
from datetime import datetime
from pathlib import Path
from threading import Lock

from paths import get_data_dir, get_download_dir


_lock = Lock()


def _settings_file():
    return get_data_dir() / "settings.json"


def _history_file():
    return get_data_dir() / "history.json"


def _covers_dir():
    return get_data_dir() / "cache" / "covers"


def _manga_cache_dir():
    return get_data_dir() / "cache" / "manga"


def get_default_settings():
    return {
        "download_dir": str(get_download_dir()),
        "headless": True,
        "browser": "firefox",
        "image_retries": 3,
        "navigation_timeout": 45000,
        "download_timeout": 60000,
        "history_limit": 200,
        "use_cache": True,
        "delete_chapters_with_history": False,
    }


def _read_json(path, default):
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def _write_json(path, data):
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception:
        pass


# ============================================================
# SETTINGS
# ============================================================


def load_settings():
    data = _read_json(_settings_file(), {})
    merged = get_default_settings()
    if isinstance(data, dict):
        for key, value in data.items():
            if key in merged:
                merged[key] = value
    return merged


def save_settings(settings):
    with _lock:
        defaults = get_default_settings()
        data = {k: settings.get(k, v) for k, v in defaults.items()}
        _write_json(_settings_file(), data)


# ============================================================
# HISTORY
# ============================================================


def load_history():
    data = _read_json(_history_file(), [])
    return data if isinstance(data, list) else []


def save_history(items):
    with _lock:
        _write_json(_history_file(), items)


def _save_cover_bytes(title, data):
    try:
        d = _covers_dir()
        d.mkdir(parents=True, exist_ok=True)
        safe = re.sub(r"[^a-zA-Z0-9_.-]+", "_", title or "cover")[:80]
        path = d / f"{safe}.img"
        path.write_bytes(data)
        return str(path)
    except Exception:
        return ""


def add_to_history(manga, cover_bytes=None):
    settings = load_settings()
    limit = int(settings.get("history_limit", 200))

    items_existing = load_history()
    prev = next((x for x in items_existing if x.get("url") == manga.url), None)

    cover_path = ""
    if cover_bytes:
        cover_path = _save_cover_bytes(manga.title, cover_bytes)
    elif prev and prev.get("cover_path"):
        cover_path = prev["cover_path"]

    entry = {
        "title": manga.title,
        "url": manga.url,
        "alternative_title": getattr(manga, "alternative_title", "") or "",
        "author": getattr(manga, "author", "") or "",
        "status": getattr(manga, "status", "") or "",
        "genres": list(getattr(manga, "genres", []) or []),
        "cover_url": getattr(manga, "cover_url", "") or "",
        "cover_path": cover_path,
        "chapters_count": len(getattr(manga, "chapters", []) or []),
        "last_opened": datetime.now().isoformat(timespec="seconds"),
    }

    items = [x for x in items_existing if x.get("url") != manga.url]
    items.insert(0, entry)
    if len(items) > limit:
        items = items[:limit]

    save_history(items)
    return entry


def remove_from_history(url):
    items = [x for x in load_history() if x.get("url") != url]
    save_history(items)


def clear_history():
    save_history([])


def delete_manga_folder(title, download_dir=None):
    if not title:
        return False
    if download_dir is None:
        download_dir = load_settings().get("download_dir", "downloads")

    safe = re.sub(r'[<>:"/\\|?*]', "_", title)
    safe = re.sub(r"\s+", " ", safe).strip()[:150] or "Untitled"

    folder = Path(download_dir) / safe
    if not folder.exists():
        return False

    try:
        shutil.rmtree(folder, ignore_errors=True)
        return True
    except Exception:
        return False


def wipe_app_data():
    """Удаляет settings.json, history.json и папку cache."""
    import shutil as _sh

    try:
        base = get_data_dir()
        for name in ("settings.json", "history.json", "cache"):
            p = base / name
            if p.is_dir():
                _sh.rmtree(p, ignore_errors=True)
            elif p.exists():
                p.unlink()
        return True
    except Exception:
        return False


# ============================================================
# MANGA CACHE
# ============================================================


def _url_slug(url):
    slug = (url or "").rstrip("/").split("/")[-1].lower()
    slug = re.sub(r"[^a-z0-9_-]+", "-", slug).strip("-")
    return slug or "unknown"


def get_cached_manga(url):
    d = _manga_cache_dir()
    slug = _url_slug(url)
    path = d / f"{slug}.json"
    data = _read_json(path, None)
    if not isinstance(data, dict):
        return None
    cover = d / f"{slug}.cover"
    data["_cover_path"] = str(cover) if cover.exists() else ""
    return data


def save_cached_manga(manga, cover_bytes=None):
    d = _manga_cache_dir()
    d.mkdir(parents=True, exist_ok=True)
    slug = _url_slug(manga.url)

    data = {
        "title": manga.title,
        "url": manga.url,
        "alternative_title": getattr(manga, "alternative_title", "") or "",
        "author": getattr(manga, "author", "") or "",
        "status": getattr(manga, "status", "") or "",
        "description": getattr(manga, "description", "") or "",
        "cover_url": getattr(manga, "cover_url", "") or "",
        "views": getattr(manga, "views", "") or "",
        "bookmarks": getattr(manga, "bookmarks", "") or "",
        "genres": list(getattr(manga, "genres", []) or []),
        "chapters": [
            {
                "number": c.number,
                "url": c.url,
                "label": c.label,
                "updated": c.updated,
                "order": c.order,
            }
            for c in (getattr(manga, "chapters", []) or [])
        ],
        "cached_at": datetime.now().isoformat(timespec="seconds"),
    }
    _write_json(d / f"{slug}.json", data)

    if cover_bytes:
        try:
            (d / f"{slug}.cover").write_bytes(cover_bytes)
        except Exception:
            pass


def invalidate_manga_cache(url):
    d = _manga_cache_dir()
    slug = _url_slug(url)
    for ext in (".json", ".cover"):
        p = d / f"{slug}{ext}"
        try:
            if p.exists():
                p.unlink()
        except Exception:
            pass


def manga_from_cache_dict(data):
    from models import Manga, Chapter

    chapters = []
    for c in data.get("chapters", []) or []:
        chapters.append(
            Chapter(
                number=str(c.get("number", "?")),
                url=c.get("url", ""),
                label=c.get("label", ""),
                updated=c.get("updated", ""),
                order=float(c.get("order", 0) or 0),
            )
        )

    return Manga(
        title=data.get("title", "Без названия"),
        url=data.get("url", ""),
        alternative_title=data.get("alternative_title", ""),
        author=data.get("author", ""),
        status=data.get("status", ""),
        description=data.get("description", ""),
        cover_url=data.get("cover_url", ""),
        views=data.get("views", ""),
        bookmarks=data.get("bookmarks", ""),
        genres=list(data.get("genres", []) or []),
        chapters=chapters,
    )
