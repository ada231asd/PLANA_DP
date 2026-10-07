"""
PLANA_DP Health Check — проверка работоспособности приложения.

Использование:
    python health_check.py
    python health_check.py --online   # + проверить доступ к mgeko.cc
"""

import argparse
import importlib
import py_compile
import subprocess
import sys
import traceback
import urllib.request
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent

SKIP_DIRS = {
    "__pycache__",
    ".git",
    ".venv",
    "venv",
    "env",
    "build",
    "dist",
    "debug",
    "cache",
    "logs",
    "downloads",
    ".idea",
    ".vscode",
}

REQUIRED_PACKAGES = [
    "PySide6",
    "playwright",
    "bs4",
    "deep_translator",
]

REQUIRED_FILES = [
    "main.py",
    "config.py",
    "paths.py",
    "storage.py",
    "logger.py",
    "models.py",
    "requirements.txt",
    "core/mgeko.py",
    "ui/main_window.py",
    "ui/theme.py",
    "ui/overlay.py",
    "ui/setup_wizard.py",
    "ui/pages/search_page.py",
    "ui/pages/history_page.py",
    "ui/pages/settings_page.py",
    "workers/search_worker.py",
    "workers/manga_worker.py",
    "workers/download_worker.py",
    "workers/translate_worker.py",
    "workers/update_worker.py",
    "workers/uninstall_worker.py",
]

STATIC_FILES = [
    "static/logo.jpg",
]


# ============================================================
# ЦВЕТА
# ============================================================

OK = "[ OK ]"
WARN = "[WARN]"
FAIL = "[FAIL]"


def banner(text):
    print()
    print("=" * 72)
    print(text)
    print("=" * 72)


def check_python_version():
    print(
        f"{OK if sys.version_info >= (3, 9) else FAIL} Python {sys.version.split()[0]}"
    )
    if sys.version_info < (3, 9):
        return False
    return True


def check_packages():
    ok = True
    for pkg in REQUIRED_PACKAGES:
        try:
            mod = importlib.import_module(pkg)
            version = getattr(mod, "__version__", "?")
            print(f"{OK} Пакет {pkg} ({version})")
        except Exception as exc:
            print(f"{FAIL} Пакет {pkg} не установлен: {exc}")
            ok = False
    return ok


def check_playwright_browsers():
    ok = True
    try:
        result = subprocess.run(
            [sys.executable, "-m", "playwright", "--version"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode == 0:
            print(f"{OK} Playwright CLI: {result.stdout.strip()}")
        else:
            print(f"{WARN} Playwright CLI вернул код {result.returncode}")
    except Exception as exc:
        print(f"{FAIL} Playwright CLI недоступен: {exc}")
        ok = False

    # пробуем импортировать и запустить браузер
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as pw:
            browser = pw.firefox.launch(headless=True)
            browser.close()
        print(f"{OK} Firefox-движок Playwright работает")
    except Exception as exc:
        print(f"{FAIL} Не удалось запустить Firefox: {exc}")
        print(f"       Попробуй: python -m playwright install firefox")
        ok = False

    return ok


def check_files():
    ok = True
    print()
    print("--- Структура проекта ---")
    for rel in REQUIRED_FILES:
        p = PROJECT_ROOT / rel
        if p.exists():
            print(f"{OK} {rel}")
        else:
            print(f"{FAIL} НЕТ ФАЙЛА: {rel}")
            ok = False
    return ok


def check_static():
    ok = True
    print()
    print("--- Static ---")
    for rel in STATIC_FILES:
        p = PROJECT_ROOT / rel
        if p.exists():
            print(f"{OK} {rel} ({p.stat().st_size} байт)")
        else:
            print(f"{WARN} Нет {rel} (не критично)")
    return ok


def check_compile():
    ok = True
    errors = []
    print()
    print("--- Компиляция .py ---")
    for path in PROJECT_ROOT.rglob("*.py"):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        try:
            py_compile.compile(str(path), doraise=True)
        except py_compile.PyCompileError as exc:
            errors.append((path, exc))
            ok = False
    if ok:
        print(f"{OK} Все .py файлы компилируются")
    else:
        for path, exc in errors:
            rel = path.relative_to(PROJECT_ROOT)
            print(f"{FAIL} {rel}: {exc}")
    return ok


def check_imports():
    ok = True
    errors = []

    print()
    print("--- Импорт модулей ---")

    # Временно CWD = PROJECT_ROOT, чтобы относительные импорты работали
    old_cwd = Path.cwd()
    old_syspath = list(sys.path)

    try:
        import os

        os.chdir(PROJECT_ROOT)
        if str(PROJECT_ROOT) not in sys.path:
            sys.path.insert(0, str(PROJECT_ROOT))

        modules = [
            "config",
            "paths",
            "storage",
            "logger",
            "models",
            "core.mgeko",
            "workers.search_worker",
            "workers.manga_worker",
            "workers.download_worker",
            "workers.translate_worker",
            "workers.update_worker",
            "workers.uninstall_worker",
        ]

        # UI-модули импортируем без запуска QApplication
        # (PySide6 требует, но большинство модулей не запускает ничего при импорте)
        ui_modules = [
            "ui.theme",
            "ui.overlay",
            "ui.pages.search_page",
            "ui.pages.history_page",
            "ui.pages.settings_page",
            "ui.main_window",
            "ui.setup_wizard",
        ]

        for name in modules + ui_modules:
            try:
                importlib.import_module(name)
                print(f"{OK} import {name}")
            except Exception as exc:
                print(f"{FAIL} import {name}: {exc}")
                errors.append((name, traceback.format_exc()))
                ok = False

    finally:
        os.chdir(old_cwd)
        sys.path[:] = old_syspath

    return ok, errors


def check_online():
    ok = True
    print()
    print("--- Сеть ---")
    for url in ("https://www.mgeko.cc/", "https://api.github.com/"):
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "PLANA_DP-HealthCheck"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                print(f"{OK} {url} — HTTP {resp.status}")
        except Exception as exc:
            print(f"{WARN} {url}: {exc}")
            ok = False
    return ok


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--online", action="store_true", help="Проверить доступ к mgeko.cc и github.com"
    )
    args = parser.parse_args()

    banner("PLANA_DP — HEALTH CHECK")
    print(f"Проект: {PROJECT_ROOT}")
    print(f"Python: {sys.executable}")

    results = {}

    print()
    print("--- Окружение ---")
    results["python"] = check_python_version()
    results["packages"] = check_packages()

    results["files"] = check_files()
    results["static"] = check_static()
    results["compile"] = check_compile()

    imports_ok, import_errors = check_imports()
    results["imports"] = imports_ok

    if args.online:
        results["online"] = check_online()

    results["playwright"] = check_playwright_browsers()

    # --- итог ---
    banner("ИТОГ")
    for key, val in results.items():
        mark = OK if val else FAIL
        print(f"{mark} {key}")

    all_ok = all(results.values())

    print()
    if all_ok:
        print("✓ Всё в порядке — можно собирать .exe и заливать на GitHub.")
    else:
        print("✗ Есть проблемы. Смотри вывод выше.")
        if import_errors:
            print()
            print("Детали импорт-ошибок:")
            for name, tb in import_errors:
                print()
                print(f"--- {name} ---")
                print(tb)
        sys.exit(1)


if __name__ == "__main__":
    main()
