"""
Сборка PLANA_DP в .exe.

Использование:
    python build_exe.py
    python build_exe.py --onefile     # всё в один файл (медленнее старт)

Требует: pip install pyinstaller pillow

ВАЖНО: перед сборкой установи переменную окружения
    $env:PLAYWRIGHT_BROWSERS_PATH = "0"
и один раз выполни
    python -m playwright install firefox --force
чтобы браузеры легли внутрь site-packages.
"""

import argparse
import subprocess
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
ICON_JPG = HERE / "static" / "logo.jpg"
ICON_ICO = HERE / "static" / "logo.ico"
SEP = ";" if sys.platform.startswith("win") else ":"


def playwright_browsers_dir():
    try:
        import playwright
    except ImportError:
        return None
    p = Path(playwright.__file__).parent / "driver" / "package" / ".local-browsers"
    return p if p.exists() else None


def ensure_icon():
    if ICON_ICO.exists():
        return True
    if not ICON_JPG.exists():
        print("[!] static/logo.jpg не найден — .exe без иконки")
        return False
    try:
        from PIL import Image
    except ImportError:
        print("[!] Pillow не установлен. Выполни: pip install pillow")
        return False
    img = Image.open(ICON_JPG).convert("RGBA")
    img.save(
        ICON_ICO,
        format="ICO",
        sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    print(f"[+] {ICON_ICO.name} создан")
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--onefile", action="store_true", help="Собрать одним файлом")
    parser.add_argument(
        "--no-browsers", action="store_true", help="Не встраивать браузеры Playwright"
    )
    args = parser.parse_args()

    has_icon = ensure_icon()

    browsers_dir = None
    if not args.no_browsers:
        browsers_dir = playwright_browsers_dir()
        if browsers_dir:
            print(f"[+] Firefox-браузеры: {browsers_dir}")
        else:
            print("[!] .local-browsers не найден.")
            print("    Перед сборкой выполни:")
            print('      $env:PLAYWRIGHT_BROWSERS_PATH = "0"')
            print("      python -m playwright install firefox --force")

    args_py = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--name",
        "PLANA_DP",
        "--noconsole",
        "--add-data",
        f"static{SEP}static",
        "--hidden-import",
        "deep_translator",
        "--collect-all",
        "deep_translator",
        "--collect-all",
        "playwright",
    ]

    if browsers_dir:
        # браузеры кладём туда же, где их будет искать playwright при запуске
        args_py += [
            "--add-data",
            f"{browsers_dir}{SEP}playwright/driver/package/.local-browsers",
        ]

    if args.onefile:
        args_py.append("--onefile")
    if has_icon:
        args_py += ["--icon", str(ICON_ICO)]

    args_py.append("main.py")

    print()
    print("[+] Запуск PyInstaller...")
    print(f"    {' '.join(args_py)}")
    print()
    subprocess.check_call(args_py, cwd=HERE)

    print()
    print("=" * 64)
    if args.onefile:
        print("[+] Готово! Файл: dist/PLANA_DP.exe")
    else:
        print("[+] Готово! Папка: dist/PLANA_DP/")
        print("    Раздавай всю папку целиком (там _internal и static).")
    print("=" * 64)
    print()
    print("Пользовательские данные пишутся вне .exe:")
    print("  bootstrap.json -> %APPDATA%/PLANA_DP/")
    print("  settings.json, history.json, cache/, logs/")
    print("    -> в папке, выбранной мастером при первом запуске")
    print("  downloads/ -> папка загрузок из настроек")


if __name__ == "__main__":
    main()
