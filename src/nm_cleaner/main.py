#!/usr/bin/env python3
"""
nm_cleaner - Clean node_modules directories recursively

This tool scans the specified directory for node_modules directories
and removes them after user confirmation.
"""

import argparse
import os
import shutil
import sys
from pathlib import Path
from typing import List


def find_node_modules(root_path: Path) -> List[Path]:
    """
    Find all node_modules directories under the specified root path.

    Args:
        root_path: The root directory to start searching from

    Returns:
        List of paths to node_modules directories found
    """
    node_modules_dirs: List[Path] = []

    try:
        for current_dir, subdirs, _ in os.walk(root_path):
            current_path = Path(current_dir)

            # If current directory is node_modules, record it
            if current_path.name == "node_modules":
                node_modules_dirs.append(current_path)
                # Don't search inside node_modules
                subdirs.clear()
                continue

            # If subdirectory contains node_modules, add it and exclude from further search
            if "node_modules" in subdirs:
                node_modules_path = current_path / "node_modules"
                node_modules_dirs.append(node_modules_path)
                subdirs.remove("node_modules")

    except PermissionError as e:
        print(f"Warning: Permission denied: {e}", file=sys.stderr)

    return node_modules_dirs


def display_directories(
    directories: List[Path],
    root_directory: Path
) -> None:
    """
    Display the list of found node_modules directories.

    Args:
        directories: List of directory paths to display
        root_directory: The root directory for relative path display
    """
    if not directories:
        print("No node_modules directories found.")
        return

    print(f"\nFound {len(directories)} node_modules director{'ies' if len(directories) > 1 else 'y'}:\n")
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
        print("No node_modules directories found.")
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
        description="Clean node_modules directories recursively",
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

    node_modules_dirs = find_node_modules(root_directory)

    if args.interactive:
        # Interactive mode
        deleted, skipped = interactive_delete(
            node_modules_dirs,
            root_directory,
            args.dry_run
        )
        print(f"\nDeleted: {deleted} director{'ies' if deleted != 1 else 'y'}")
        if skipped > 0:
            print(f"Skipped: {skipped} director{'ies' if skipped != 1 else 'y'}")
    else:
        # Normal mode
        display_directories(node_modules_dirs, root_directory)

        if not node_modules_dirs:
            return 0

        if args.dry_run:
            print("Dry run mode - no directories were deleted.")
            return 0

        if not args.yes:
            if not confirm_deletion():
                print("Deletion cancelled.")
                return 0

        deleted = delete_directories(node_modules_dirs, root_directory)
        print(f"\nDeleted {deleted} director{'ies' if deleted != 1 else 'y'}.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
