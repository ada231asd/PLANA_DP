"""
PLANA_DP → GitHub.

Использование:
    python push_to_github.py
    python push_to_github.py --repo https://github.com/user/PLANA_DP.git
    python push_to_github.py --branch main

Требует установленный git в PATH.
"""

import argparse
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent


def run(cmd, check=True, capture=False):
    print(f"$ {' '.join(cmd)}")
    result = subprocess.run(
        cmd,
        cwd=PROJECT_ROOT,
        capture_output=capture,
        text=True,
    )
    if check and result.returncode != 0:
        if capture:
            print(result.stdout)
            print(result.stderr)
        raise SystemExit(f"Команда не выполнена: {cmd}")
    return result


def has_git():
    try:
        subprocess.run(["git", "--version"], capture_output=True, check=True)
        return True
    except Exception:
        return False


def is_repo():
    return (PROJECT_ROOT / ".git").is_dir()


def ensure_gitignore():
    p = PROJECT_ROOT / ".gitignore"
    if not p.exists():
        print("⚠ Нет .gitignore — создай его перед пушем!")
        print("   Возьми готовый из инструкции.")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--repo", default="", help="URL удалённого репозитория (если ещё не задан)"
    )
    parser.add_argument(
        "--branch", default="main", help="Имя ветки (по умолчанию main)"
    )
    parser.add_argument(
        "--message", default="Update PLANA_DP", help="Сообщение коммита"
    )
    args = parser.parse_args()

    if not has_git():
        print("✗ git не найден. Установи Git и добавь в PATH.")
        sys.exit(1)

    ensure_gitignore()

    if not is_repo():
        print("→ git init")
        run(["git", "init", "-b", args.branch])

    # Проверим статус
    print()
    print("--- git status ---")
    status = run(["git", "status", "--short"], capture=True)
    print(status.stdout or "(пусто)")

    # Настроим user, если не настроен
    name = run(["git", "config", "user.name"], capture=True, check=False)
    email = run(["git", "config", "user.email"], capture=True, check=False)
    if not name.stdout.strip():
        n = input("Введи user.name для git: ").strip()
        if n:
            run(["git", "config", "user.name", n])
    if not email.stdout.strip():
        e = input("Введи user.email для git: ").strip()
        if e:
            run(["git", "config", "user.email", e])

    # add + commit
    print()
    print("→ git add .")
    run(["git", "add", "."])

    print("→ git commit")
    commit = run(
        ["git", "commit", "-m", args.message],
        capture=True,
        check=False,
    )
    print(commit.stdout or commit.stderr or "(нет изменений)")

    # remote
    remote = run(["git", "remote", "-v"], capture=True, check=False)
    has_origin = "origin" in (remote.stdout or "")

    if not has_origin:
        repo = (
            args.repo
            or input(
                "Введи URL репозитория (https://github.com/user/repo.git): "
            ).strip()
        )
        if not repo:
            print("✗ URL не указан.")
            sys.exit(1)
        run(["git", "remote", "add", "origin", repo])
    elif args.repo:
        run(["git", "remote", "set-url", "origin", args.repo])

    # push
    print()
    print(f"→ git push -u origin {args.branch}")
    run(["git", "push", "-u", "origin", args.branch], check=False)

    print()
    print("✓ Готово.")


if __name__ == "__main__":
    main()
