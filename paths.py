import json
import os
import shutil
import sys
from pathlib import Path


APP_DIR_NAME = "PLANA_DP"


def is_frozen():
    return getattr(sys, "frozen", False)


def app_root():
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def _user_config_root():
    if sys.platform.startswith("win"):
        base = os.environ.get("APPDATA") or str(Path.home())
        return Path(base) / APP_DIR_NAME
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_DIR_NAME
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / APP_DIR_NAME


BOOTSTRAP_FILE = _user_config_root() / "bootstrap.json"


def load_bootstrap():
    try:
        if BOOTSTRAP_FILE.exists():
            return json.loads(BOOTSTRAP_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return None


def save_bootstrap(data):
    try:
        BOOTSTRAP_FILE.parent.mkdir(parents=True, exist_ok=True)
        BOOTSTRAP_FILE.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return True
    except Exception:
        return False


def default_data_dir():
    return _user_config_root() / "data"


def _ensure(p):
    try:
        p.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    return p


def get_data_dir():
    boot = load_bootstrap()
    if boot and boot.get("data_dir"):
        return _ensure(Path(boot["data_dir"]))
    return _ensure(default_data_dir())


def get_download_dir():
    boot = load_bootstrap()
    if boot and boot.get("download_dir"):
        return _ensure(Path(boot["download_dir"]))
    return _ensure(get_data_dir() / "downloads")


def get_static_dir():
    if is_frozen():
        base = Path(getattr(sys, "_MEIPASS", app_root()))
        return base / "static"
    return app_root() / "static"


# ============================================================
# DATA LOCATION / MIGRATION
# ============================================================


def is_in_user_config(path) -> bool:
    """True, если путь находится внутри %APPDATA%/PLANA_DP (или аналога)."""
    try:
        p = Path(path).resolve()
        root = _user_config_root().resolve()
        return root == p or root in p.parents
    except Exception:
        return False


def migrate_data_dir_to_default() -> bool:
    """
    Переносит содержимое текущего data_dir в default_data_dir().
    Обновляет bootstrap.json (data_dir и, при необходимости, download_dir).
    Возвращает True при успехе.
    """
    try:
        current = get_data_dir().resolve()
        target = default_data_dir().resolve()

        if current == target:
            return True

        target.mkdir(parents=True, exist_ok=True)

        for item in current.iterdir():
            dest = target / item.name
            if dest.exists():
                # не перезаписываем — вдруг там уже что-то есть
                continue
            try:
                shutil.move(str(item), str(dest))
            except Exception:
                # если move не сработал (cross-device), пробуем copy+rm
                if item.is_dir():
                    shutil.copytree(item, dest)
                    shutil.rmtree(item, ignore_errors=True)
                else:
                    shutil.copy2(item, dest)
                    try:
                        item.unlink()
                    except Exception:
                        pass

        boot = load_bootstrap() or {}
        boot["data_dir"] = str(target)

        # если download_dir лежал внутри старого data_dir — переносим путь
        old_dl = boot.get("download_dir")
        if old_dl:
            try:
                old_dl_path = Path(old_dl).resolve()
                if current == old_dl_path or current in old_dl_path.parents:
                    rel = old_dl_path.relative_to(current)
                    boot["download_dir"] = str(target / rel)
            except Exception:
                pass

        save_bootstrap(boot)
        return True
    except Exception:
        return False
