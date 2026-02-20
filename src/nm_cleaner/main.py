#!/usr/bin/env python3
"""
nm_cleaner - Clean node_modules and __pycache__ directories recursively

This tool scans the specified directory for node_modules and __pycache__
directories and removes them after user confirmation.
"""

import argparse
import os
import shutil
import sys
from pathlib import Path
from typing import List

# Target directories to clean
TARGET_DIRS = {"node_modules", "__pycache__"}

# venvディレクトリは追加の検証が必要なため、別途定義
VENV_DIR_NAME = "venv"


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


def find_target_directories(root_path: Path) -> List[Path]:
    """
    Find all target directories (node_modules, __pycache__) under the specified root path.

    Args:
        root_path: The root directory to start searching from

    Returns:
        List of paths to target directories found
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

            # 現在のディレクトリがPythonのvenv仮想環境かチェック
            if current_path.name == VENV_DIR_NAME and is_python_venv(current_path):
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

            # サブディレクトリ内のvenvディレクトリをチェック
            if VENV_DIR_NAME in subdirs:
                venv_path = current_path / VENV_DIR_NAME
                if is_python_venv(venv_path):
                    target_dirs.append(venv_path)
                    subdirs.remove(VENV_DIR_NAME)

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
    Delete the specified directories.

    Args:
        directories: List of directories to delete
        root_directory: The root directory for relative path display
        dry_run: If True, only simulate deletion

    Returns:
        Number of successfully deleted directories
    """
    deleted_count = 0

    for directory in directories:
        try:
            relative_path = directory.relative_to(root_directory)
        except ValueError:
            relative_path = directory

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
    Interactively confirm deletion for each directory.

    Args:
        directories: List of directories to potentially delete
        root_directory: The root directory for relative path display
        dry_run: If True, only simulate deletion

    Returns:
        Tuple of (deleted_count, skipped_count)
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
        description="Clean node_modules and __pycache__ directories recursively",
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
