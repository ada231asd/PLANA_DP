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
    try:
        p = Path(path).resolve()
        root = _user_config_root().resolve()
        return root == p or root in p.parents
    except Exception:
        return False


def migrate_data_dir_to_default() -> bool:
    try:
        current = get_data_dir().resolve()
        target = default_data_dir().resolve()

        if current == target:
            return True

        target.mkdir(parents=True, exist_ok=True)

        for item in current.iterdir():
            dest = target / item.name
            if dest.exists():
                continue
            try:
                shutil.move(str(item), str(dest))
            except Exception:
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


# ============================================================
# LOCAL BROWSERS
# ============================================================


def _reg_app_paths(exe_name):
    """Читает HKCU/HKLM App Paths для указанного exe. Возвращает Path или None."""
    if not sys.platform.startswith("win"):
        return None
    try:
        import winreg
    except Exception:
        return None

    sub = rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{exe_name}"
    for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        try:
            with winreg.OpenKey(hive, sub) as k:
                value, _ = winreg.QueryValueEx(k, "")
                if value:
                    p = Path(value)
                    if p.exists():
                        return p
        except OSError:
            continue
    return None


def _candidate_paths():
    """
    Известные места установки браузеров на Windows.
    Список намеренно широкий: Opera GX, обычная Opera, Chrome, Edge,
    Brave, Vivaldi, Firefox, Yandex.
    """
    if sys.platform.startswith("win"):
        local = Path(os.environ.get("LOCALAPPDATA") or "")
        prog = Path(os.environ.get("PROGRAMFILES") or "")
        progx86 = Path(os.environ.get("PROGRAMFILES(X86)") or "")
        return [
            ("chrome", local / "Google/Chrome/Application/chrome.exe"),
            ("chrome", prog / "Google/Chrome/Application/chrome.exe"),
            ("chrome", progx86 / "Google/Chrome/Application/chrome.exe"),
            ("msedge", prog / "Microsoft/Edge/Application/msedge.exe"),
            ("msedge", progx86 / "Microsoft/Edge/Application/msedge.exe"),
            ("brave", local / "BraveSoftware/Brave-Browser/Application/brave.exe"),
            ("brave", prog / "BraveSoftware/Brave-Browser/Application/brave.exe"),
            ("vivaldi", local / "Vivaldi/Application/vivaldi.exe"),
            ("vivaldi", prog / "Vivaldi/Application/vivaldi.exe"),
            ("opera", local / "Programs/Opera/opera.exe"),
            ("opera", prog / "Opera/opera.exe"),
            ("opera", progx86 / "Opera/opera.exe"),
            ("operagx", local / "Programs/Opera GX/opera.exe"),
            ("operagx", prog / "Opera GX/opera.exe"),
            ("operagx", progx86 / "Opera GX/opera.exe"),
            ("firefox", prog / "Mozilla Firefox/firefox.exe"),
            ("firefox", progx86 / "Mozilla Firefox/firefox.exe"),
            ("yandex", local / "Yandex/YandexBrowser/Application/browser.exe"),
            ("yandex", prog / "Yandex/YandexBrowser/Application/browser.exe"),
        ]
    if sys.platform == "darwin":
        return [
            (
                "chrome",
                Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
            ),
            (
                "msedge",
                Path("/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"),
            ),
            ("firefox", Path("/Applications/Firefox.app/Contents/MacOS/firefox")),
            ("opera", Path("/Applications/Opera.app/Contents/MacOS/Opera")),
            ("operagx", Path("/Applications/Opera GX.app/Contents/MacOS/Opera")),
            (
                "brave",
                Path("/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"),
            ),
        ]
    return []


def find_installed_browsers():
    """
    Возвращает dict {name: str(path)} для найденных браузеров.
    Приоритет: реестр App Paths → известные папки установки.
    Один и тот же путь не дублируется под разными именами
    (кроме случая, когда Opera и Opera GX реально разные файлы).
    """
    found = {}

    registry_pairs = [
        ("chrome", "chrome.exe"),
        ("msedge", "msedge.exe"),
        ("brave", "brave.exe"),
        ("vivaldi", "vivaldi.exe"),
        ("opera", "opera.exe"),
        ("firefox", "firefox.exe"),
    ]
    for name, exe in registry_pairs:
        p = _reg_app_paths(exe)
        if p:
            found.setdefault(name, str(p))

    for name, p in _candidate_paths():
        if p and p.exists():
            found.setdefault(name, str(p))

    # Убираем дубли путей, оставляя первое имя
    uniq = {}
    used_paths = set()
    for name, path in found.items():
        rp = str(Path(path).resolve()).lower()
        if rp in used_paths:
            continue
        used_paths.add(rp)
        uniq[name] = path

    return uniq


def is_chromium_browser(path):
    """True, если путь ведёт на Chromium-совместимый браузер."""
    name = Path(path).name.lower()
    return any(
        token in name
        for token in (
            "chrome",
            "chromium",
            "msedge",
            "brave",
            "vivaldi",
            "opera",
            "browser.exe",
            "yandex",
        )
    )
