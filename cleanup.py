"""
PLANA_DP Cleanup — уборка проекта перед загрузкой на GitHub.

Использование:
    python cleanup.py            # dry-run, ничего не удаляет
    python cleanup.py --apply    # удаляет после подтверждения
    python cleanup.py --keep-static   # не трогать static/
"""

import argparse
import ast
import shutil
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
ENTRY_POINTS = ["main.py"]

# Что не считаем мусором и что нельзя сканировать
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
    "node_modules",
    "static",
}

# Файлы и папки, которые точно чистим при --apply
JUNK_PATTERNS = [
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "*.pyc",
    "*.pyo",
    "build",
    "dist",
    "debug",
    "cache",
    "logs",
    "settings.json",
    "history.json",
    "bootstrap.json",
    "*.spec",
]

# Файлы, которые не должны уехать в репозиторий
SENSITIVE_FILES = [
    "settings.json",
    "history.json",
    "bootstrap.json",
]


# ============================================================
# ИМПОРТ-ГРАФ
# ============================================================


def iter_python_files():
    for path in PROJECT_ROOT.rglob("*.py"):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.name in {
            "cleanup.py",
            "health_check.py",
            "push_to_github.py",
            "build_exe.py",
        }:
            # сами утилиты не считаем частью графа приложения
            continue
        yield path


def resolve_module(name, current_file, level):
    """
    Возвращает путь к .py или __init__.py для импорта.
    name: 'core.mgeko', 'models', '' (для относительного)
    level: число точек для относительного импорта
    """
    if level > 0:
        # относительный импорт
        base = current_file.parent
        for _ in range(level - 1):
            base = base.parent
        parts = [p for p in (name.split(".") if name else []) if p]
        candidate = base.joinpath(*parts) if parts else base
        if candidate.is_file() and candidate.suffix == ".py":
            return candidate
        if candidate.is_dir():
            init = candidate / "__init__.py"
            if init.exists():
                return init
        return None

    parts = name.split(".")
    candidate = PROJECT_ROOT.joinpath(*parts).with_suffix(".py")
    if candidate.exists():
        return candidate
    candidate = PROJECT_ROOT.joinpath(*parts) / "__init__.py"
    if candidate.exists():
        return candidate
    return None


def parse_imports(path):
    try:
        src = path.read_text(encoding="utf-8")
    except Exception:
        return []

    try:
        tree = ast.parse(src, filename=str(path))
    except SyntaxError:
        return []

    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append((alias.name, 0))
        elif isinstance(node, ast.ImportFrom):
            level = node.level or 0
            module = node.module or ""
            # сам модуль
            if module:
                imports.append((module, level))
            # подмодули из from x import a, b
            for alias in node.names:
                if alias.name == "*":
                    continue
                full = f"{module}.{alias.name}" if module else alias.name
                imports.append((full, level))

    return imports


def build_import_graph():
    """
    Возвращает (used_paths, all_paths).
    used_paths — достижимые из ENTRY_POINTS.
    """
    all_files = {p.resolve() for p in iter_python_files()}

    used = set()
    queue = []
    for entry in ENTRY_POINTS:
        p = PROJECT_ROOT / entry
        if p.exists():
            used.add(p.resolve())
            queue.append(p.resolve())

    # обычные модули проекта могут быть импортированы из воркеров и т.п.
    # их надо учитывать как корни, потому что Qt грузит их по имени
    # (например, workers.search_worker импортируется из ui)
    roots = list(all_files)

    while queue:
        current = queue.pop()
        for name, level in parse_imports(current):
            target = resolve_module(name, current, level)
            if not target:
                continue
            target = target.resolve()
            if target in all_files and target not in used:
                used.add(target)
                queue.append(target)

    # файлы в корне, которые не в SKIP и не в junk, тоже считаем «возможно нужны»
    # — это config.py, models.py, storage.py и т.п.
    # Их всегда оставляем.
    for f in all_files:
        if f.parent == PROJECT_ROOT.resolve() and f not in used:
            used.add(f)

    # __init__.py всегда оставляем — нужны пакетам
    for f in all_files:
        if f.name == "__init__.py":
            used.add(f)

    # Покажем подозрительные (недостижимые), кроме корневых и __init__
    unreachable = all_files - used
    return used, all_files, unreachable


# ============================================================
# МУСОР
# ============================================================


def find_junk():
    """Возвращает список путей, которые надо удалить."""
    junk = []

    for pattern in JUNK_PATTERNS:
        for path in PROJECT_ROOT.rglob(pattern):
            if any(part == ".git" for part in path.parts):
                continue
            junk.append(path)

    # дедупликация: если папка в junk, её содержимое не нужно
    result = []
    junk_sorted = sorted(set(junk), key=lambda p: len(p.parts))
    seen_parents = []
    for p in junk_sorted:
        if any(parent in p.parents for parent in seen_parents):
            continue
        result.append(p)
        if p.is_dir():
            seen_parents.append(p)

    return result


def size_of(path):
    if path.is_file():
        try:
            return path.stat().st_size
        except Exception:
            return 0
    total = 0
    for f in path.rglob("*"):
        if f.is_file():
            try:
                total += f.stat().st_size
            except Exception:
                pass
    return total


def human(size):
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


# ============================================================
# ОТЧЁТ
# ============================================================


def print_banner(text):
    print()
    print("=" * 72)
    print(text)
    print("=" * 72)


def print_report(used, all_files, unreachable, junk, sensitive_found):
    print_banner("PLANA_DP CLEANUP — ОТЧЁТ")
    print(f"Проект:        {PROJECT_ROOT}")
    print(f"Python файлов: {len(all_files)}")
    print(f"Использовано:  {len(used)}")
    print(
        f"Мусор:         {len(junk)} объект(ов), {human(sum(size_of(j) for j in junk))}"
    )

    # --- подозрительные Python-файлы ---
    if unreachable:
        print()
        print("⚠  Похоже, не используются (но я их не трогаю):")
        for p in sorted(unreachable):
            rel = p.relative_to(PROJECT_ROOT)
            print(f"   - {rel}")
        print("   Если это старые эксперименты — удали вручную.")
    else:
        print()
        print("✓ Все Python-файлы используются.")

    # --- мусор ---
    if junk:
        print()
        print("🗑  Мусор (будет удалён при --apply):")
        for p in junk:
            try:
                rel = p.relative_to(PROJECT_ROOT)
            except ValueError:
                rel = p
            kind = "DIR " if p.is_dir() else "FILE"
            print(f"   [{kind}] {rel}   ({human(size_of(p))})")
    else:
        print()
        print("✓ Мусора нет.")

    # --- sensitive files ---
    if sensitive_found:
        print()
        print("🔒 Приватные файлы в корне (НЕ должны уйти в GitHub):")
        for p in sensitive_found:
            print(f"   - {p.name}")
        print(
            "   Они перечислены в .gitignore — это нормально,"
            " но убедись что файл на месте."
        )


# ============================================================
# MAIN
# ============================================================


def main():
    parser = argparse.ArgumentParser(
        description="Уборка проекта PLANA_DP для загрузки на GitHub",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Удалить найденный мусор (по умолчанию dry-run)",
    )
    parser.add_argument(
        "--keep-static",
        action="store_true",
        help="Не трогать static/ (по умолчанию static не чистится)",
    )
    args = parser.parse_args()

    print_banner("PLANA_DP CLEANUP")
    print(f"Режим: {'APPLY (удаление)' if args.apply else 'DRY-RUN (только отчёт)'}")

    used, all_files, unreachable = build_import_graph()
    junk = find_junk()

    sensitive_found = [
        PROJECT_ROOT / name
        for name in SENSITIVE_FILES
        if (PROJECT_ROOT / name).exists()
    ]

    print_report(used, all_files, unreachable, junk, sensitive_found)

    if not junk:
        print()
        print("Нечего удалять.")
        return

    if not args.apply:
        print()
        print("=" * 72)
        print("Это dry-run. Ничего не удалено.")
        print("Чтобы удалить — запусти: python cleanup.py --apply")
        print("=" * 72)
        return

    # --- apply ---
    print()
    answer = input(f"Удалить {len(junk)} объектов? [y/N]: ").strip().lower()
    if answer != "y":
        print("Отменено.")
        return

    for path in junk:
        try:
            if path.is_dir():
                shutil.rmtree(path, ignore_errors=True)
            else:
                path.unlink()
            print(f"  удалено: {path.relative_to(PROJECT_ROOT)}")
        except Exception as exc:
            print(f"  ошибка удаления {path}: {exc}")

    print()
    print("✓ Готово.")
    print()
    print("Проверь, что в корне есть файл .gitignore — он исключит")
    print("settings.json, history.json, cache, logs и т.п. из репозитория.")


if __name__ == "__main__":
    main()
