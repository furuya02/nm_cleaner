#!/usr/bin/env python3
"""
nm_cleaner - node_modules, __pycache__, Python venv仮想環境ディレクトリを再帰的に削除するツール

指定されたディレクトリ配下のnode_modules、__pycache__、
およびPythonのvenv仮想環境ディレクトリを検索し、
ユーザーの確認後に削除する。

Python venv仮想環境は、ディレクトリ名（venv、.venv等）に関わらず、
pyvenv.cfgファイルとactivateスクリプトの存在によって検出する。
これにより、Python venvモジュールで作成された仮想環境のみを対象とし、
同名の通常ディレクトリの誤削除を防ぐ。

venv削除時の自動バックアップ機能:
    venv仮想環境を削除する際、pip freezeを実行して
    依存パッケージの一覧をrequirements.txtとして自動的に保存する。
    既存のrequirements.txtがある場合は上書きする。これにより、
    venv削除後も `pip install -r requirements.txt` で
    環境を再構築できる。
"""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

# Target directories to clean
TARGET_DIRS = {"node_modules", "__pycache__"}


def is_python_venv(directory: Path) -> bool:
    """
    指定されたディレクトリがPythonのvenv仮想環境かどうかを判定する。

    Pythonのvenvモジュールで作成された仮想環境は以下の特徴を持つ:
    - ルートディレクトリにpyvenv.cfgファイルが存在する
    - bin/activate (Unix系) または Scripts/activate (Windows) が存在する

    単に「venv」という名前のディレクトリを誤って削除しないよう、
    上記の両方の条件を満たす場合のみTrueを返す。

    Args:
        directory: 検証対象のディレクトリパス

    Returns:
        Pythonのvenv仮想環境の場合はTrue、そうでなければFalse
    """
    # pyvenv.cfgファイルの存在確認
    pyvenv_cfg = directory / "pyvenv.cfg"
    if not pyvenv_cfg.exists():
        return False

    # activateスクリプトの存在確認 (Unix: bin/activate, Windows: Scripts/activate)
    unix_activate = directory / "bin" / "activate"
    windows_activate = directory / "Scripts" / "activate"

    return unix_activate.exists() or windows_activate.exists()


def get_venv_pip_path(venv_dir: Path) -> Optional[Path]:
    """
    venv仮想環境内のpip実行ファイルのパスを取得する。

    Args:
        venv_dir: venv仮想環境のディレクトリパス

    Returns:
        pipのパス。見つからない場合はNone
    """
    # Unix系: bin/pip
    unix_pip = venv_dir / "bin" / "pip"
    if unix_pip.exists():
        return unix_pip

    # Windows: Scripts/pip.exe
    windows_pip = venv_dir / "Scripts" / "pip.exe"
    if windows_pip.exists():
        return windows_pip

    return None


def export_venv_requirements(venv_dir: Path, dry_run: bool = False) -> bool:
    """
    venv仮想環境からrequirements.txtをエクスポートする。

    venvの親ディレクトリ（通常はプロジェクトルート）に
    pip freezeを実行して依存パッケージの一覧をrequirements.txtとして保存する。
    既存のrequirements.txtがある場合は上書きする。

    Args:
        venv_dir: venv仮想環境のディレクトリパス
        dry_run: Trueの場合、実際にはファイルを作成しない

    Returns:
        requirements.txtを作成した場合はTrue、
        作成に失敗した場合はFalse
    """
    # requirements.txtの出力先（venvの親ディレクトリ）
    project_dir = venv_dir.parent
    requirements_path = project_dir / "requirements.txt"
    is_update = requirements_path.exists()

    # venv内のpipのパスを取得
    pip_path = get_venv_pip_path(venv_dir)
    if pip_path is None:
        print(f"  Warning: pip not found in {venv_dir}", file=sys.stderr)
        return False

    if dry_run:
        action = "update" if is_update else "create"
        print(f"  Would {action}: {requirements_path}")
        return True

    try:
        # pip freezeを実行してrequirements.txtを生成
        result = subprocess.run(
            [str(pip_path), "freeze"],
            capture_output=True,
            text=True,
            timeout=60
        )

        if result.returncode != 0:
            print(
                f"  Warning: pip freeze failed for {venv_dir}: {result.stderr}",
                file=sys.stderr
            )
            return False

        # 出力が空でない場合のみファイルを作成
        if result.stdout.strip():
            requirements_path.write_text(result.stdout)
            action = "Updated" if is_update else "Created"
            print(f"  {action}: {requirements_path}")
            return True
        else:
            print(f"  Skipped: {venv_dir} (no packages installed)")
            return False

    except subprocess.TimeoutExpired:
        print(f"  Warning: pip freeze timed out for {venv_dir}", file=sys.stderr)
        return False
    except OSError as e:
        print(f"  Warning: Failed to export requirements: {e}", file=sys.stderr)
        return False


def find_target_directories(root_path: Path) -> List[Path]:
    """
    指定されたルートパス配下の削除対象ディレクトリを全て検索する。

    削除対象:
    - node_modules: Node.jsの依存パッケージディレクトリ
    - __pycache__: Pythonのバイトコードキャッシュディレクトリ
    - Python venv仮想環境: ディレクトリ名に関わらず、
      pyvenv.cfgとactivateスクリプトの存在によって検出（is_python_venv参照）

    Args:
        root_path: 検索を開始するルートディレクトリ

    Returns:
        検出された削除対象ディレクトリのパスリスト
    """
    target_dirs: List[Path] = []

    try:
        for current_dir, subdirs, _ in os.walk(root_path):
            current_path = Path(current_dir)

            # If current directory is a target, record it
            if current_path.name in TARGET_DIRS:
                target_dirs.append(current_path)
                # Don't search inside target directories
                subdirs.clear()
                continue

            # 現在のディレクトリがPython venv仮想環境かチェック（名前を問わない）
            if is_python_venv(current_path):
                target_dirs.append(current_path)
                # venv内部は検索しない
                subdirs.clear()
                continue

            # Check for target directories in subdirs
            for target_name in TARGET_DIRS:
                if target_name in subdirs:
                    target_path = current_path / target_name
                    target_dirs.append(target_path)
                    subdirs.remove(target_name)

            # サブディレクトリのうち、Python venv仮想環境であるものをチェック（名前を問わない）
            for subdir_name in list(subdirs):
                subdir_path = current_path / subdir_name
                if is_python_venv(subdir_path):
                    target_dirs.append(subdir_path)
                    subdirs.remove(subdir_name)

    except PermissionError as e:
        print(f"Warning: Permission denied: {e}", file=sys.stderr)

    return target_dirs


def display_directories(
    directories: List[Path],
    root_directory: Path
) -> None:
    """
    Display the list of found target directories.

    Args:
        directories: List of directory paths to display
        root_directory: The root directory for relative path display
    """
    if not directories:
        print("No target directories found.")
        return

    print(f"\nFound {len(directories)} director{'ies' if len(directories) > 1 else 'y'}:\n")
    for directory in sorted(directories):
        try:
            relative_path = directory.relative_to(root_directory)
            print(f"  [DIR] {relative_path}/")
        except ValueError:
            print(f"  [DIR] {directory}/")
    print()


def confirm_deletion() -> bool:
    """
    Ask user for confirmation before deletion.

    Returns:
        True if user confirms, False otherwise
    """
    while True:
        response = input("Do you want to delete these directories? (yes/no): ").strip().lower()
        if response in ("yes", "y"):
            return True
        elif response in ("no", "n"):
            return False
        else:
            print("Please enter 'yes' or 'no'.")


def delete_directories(
    directories: List[Path],
    root_directory: Path,
    dry_run: bool = False
) -> int:
    """
    指定されたディレクトリを削除する。

    venvディレクトリの場合は、削除前にrequirements.txtを
    自動生成する（既に存在する場合は上書き）。

    Args:
        directories: 削除対象のディレクトリリスト
        root_directory: 相対パス表示用のルートディレクトリ
        dry_run: Trueの場合、実際には削除しない

    Returns:
        削除に成功したディレクトリの数
    """
    deleted_count = 0

    for directory in directories:
        try:
            relative_path = directory.relative_to(root_directory)
        except ValueError:
            relative_path = directory

        # Python venv仮想環境の場合、削除前にrequirements.txtを生成
        if is_python_venv(directory):
            export_venv_requirements(directory, dry_run)

        try:
            if not dry_run:
                shutil.rmtree(directory)
            print(f"Deleted: {relative_path}/")
            deleted_count += 1
        except OSError as error:
            print(f"Error deleting {relative_path}/: {error}", file=sys.stderr)

    return deleted_count


def interactive_delete(
    directories: List[Path],
    root_directory: Path,
    dry_run: bool = False
) -> tuple[int, int]:
    """
    各ディレクトリの削除を対話的に確認する。

    venvディレクトリの場合は、削除前にrequirements.txtを
    自動生成する（既に存在する場合は上書き）。

    Args:
        directories: 削除候補のディレクトリリスト
        root_directory: 相対パス表示用のルートディレクトリ
        dry_run: Trueの場合、実際には削除しない

    Returns:
        (削除数, スキップ数) のタプル
    """
    if not directories:
        print("No target directories found.")
        return 0, 0

    deleted_count = 0
    skipped_count = 0

    for directory in directories:
        try:
            relative_path = directory.relative_to(root_directory)
        except ValueError:
            relative_path = directory

        print(f"\nFound: {relative_path}/")
        print("Delete this directory? (yes/no/quit): ", end="")

        response = input().strip().lower()

        if response in ("quit", "q"):
            print("Aborted.")
            break
        elif response in ("yes", "y"):
            # Python venv仮想環境の場合、削除前にrequirements.txtを生成
            if is_python_venv(directory):
                export_venv_requirements(directory, dry_run)

            try:
                if not dry_run:
                    shutil.rmtree(directory)
                print("Deleted.")
                deleted_count += 1
            except OSError as error:
                print(f"Error: Failed to delete: {error}", file=sys.stderr)
        elif response in ("no", "n"):
            print("Skipped.")
            skipped_count += 1
        else:
            print("Invalid input. Skipping.")
            skipped_count += 1

    return deleted_count, skipped_count


def main() -> int:
    """
    Main entry point for nm_cleaner.

    Returns:
        Exit code (0 for success, 1 for error)
    """
    parser = argparse.ArgumentParser(
        description="node_modules, __pycache__, venvディレクトリを再帰的に削除",
        prog="nm_cleaner"
    )
    parser.add_argument(
        "-d", "--directory",
        type=str,
        default=".",
        help="Directory to clean (default: current directory)"
    )
    parser.add_argument(
        "-i", "--interactive",
        action="store_true",
        help="Interactive mode: confirm deletion for each directory"
    )
    parser.add_argument(
        "-n", "--dry-run",
        action="store_true",
        help="Show what would be deleted without actually deleting"
    )
    parser.add_argument(
        "-y", "--yes",
        action="store_true",
        help="Skip confirmation prompt"
    )
    parser.add_argument(
        "-v", "--version",
        action="version",
        version="%(prog)s 0.1.0"
    )

    args = parser.parse_args()

    root_directory = Path(args.directory).resolve()

    if not root_directory.exists():
        print(f"Error: Directory '{root_directory}' does not exist.", file=sys.stderr)
        return 1

    if not root_directory.is_dir():
        print(f"Error: '{root_directory}' is not a directory.", file=sys.stderr)
        return 1

    print(f"Scanning: {root_directory}")

    target_dirs = find_target_directories(root_directory)

    if args.interactive:
        # Interactive mode
        deleted, skipped = interactive_delete(
            target_dirs,
            root_directory,
            args.dry_run
        )
        print(f"\nDeleted: {deleted} director{'ies' if deleted != 1 else 'y'}")
        if skipped > 0:
            print(f"Skipped: {skipped} director{'ies' if skipped != 1 else 'y'}")
    else:
        # Normal mode
        display_directories(target_dirs, root_directory)

        if not target_dirs:
            return 0

        if args.dry_run:
            print("Dry run mode - no directories were deleted.")
            return 0

        if not args.yes:
            if not confirm_deletion():
                print("Deletion cancelled.")
                return 0

        deleted = delete_directories(target_dirs, root_directory)
        print(f"\nDeleted {deleted} director{'ies' if deleted != 1 else 'y'}.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
