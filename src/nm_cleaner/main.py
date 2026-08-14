#!/usr/bin/env python3
"""
nm_cleaner - 再生成可能なディレクトリを再帰的に削除するツール

指定されたディレクトリ配下から、ツールが自動生成したディレクトリ
（node_modules、__pycache__、cdk.out、各種ビルドキャッシュなど）と
Pythonのvenv仮想環境を検索し、ユーザーの確認後に削除する。

削除対象の判定は、誤削除を防ぐため3段階に分けている:

1. 名前一致のみで判定 (TARGET_DIRS)
   node_modules や cdk.out のように、その名前であればツールの生成物で
   あることがほぼ確実なもの。

2. マーカーファイルの併用が必要 (MARKER_REQUIRED_DIRS)
   dist / build は一般名詞でもあるため、同じ階層に package.json などの
   ビルド設定ファイルがある場合のみビルド成果物とみなす。

3. 内容で判定
   Python venv仮想環境は、ディレクトリ名（venv、.venv等）に関わらず、
   pyvenv.cfgファイルとactivateスクリプトの存在によって検出する。

venv削除時の自動バックアップ機能:
    venv仮想環境を削除する際、pip freezeを実行して
    依存パッケージの一覧をrequirements.txtとして自動的に保存する。
    既存のrequirements.txtがある場合は上書きする。これにより、
    venv削除後も `pip install -r requirements.txt` で
    環境を再構築できる。

学習チェックポイントの世代削除:
    checkpoints ディレクトリ配下には学習途中の世代が蓄積し、
    容量の大半を占めることが多い。最新の世代だけを残し、
    それより古い世代を削除する（--keep-last で保持数を変更可能）。
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Set, Tuple

__version__ = "0.2.0"

# 名前が一致すれば削除対象とするディレクトリ。
# いずれもツールが自動生成し、コマンド一つで再生成できるものに限定する。
TARGET_DIRS = {
    "node_modules",   # npm / yarn / pnpm の依存パッケージ
    "__pycache__",    # Python バイトコードキャッシュ
    "cdk.out",        # AWS CDK の合成結果 (cdk synth で再生成)
    ".terraform",     # Terraform のプラグイン等 (terraform init で再取得)
    ".next",          # Next.js のビルド成果物
    ".nuxt",          # Nuxt のビルド成果物
    ".svelte-kit",    # SvelteKit のビルド成果物
    ".turbo",         # Turborepo のキャッシュ
    ".parcel-cache",  # Parcel のキャッシュ
    ".pytest_cache",  # pytest のキャッシュ
    ".mypy_cache",    # mypy のキャッシュ
    ".ruff_cache",    # ruff のキャッシュ
}

# 名前だけでは判断できないディレクトリ。
# dist / build は写真の配布用フォルダなど一般的な用途でも使われるため、
# 同じ階層にビルド設定ファイル (BUILD_MARKERS) がある場合のみ対象とする。
MARKER_REQUIRED_DIRS = {"dist", "build"}

# dist / build をビルド成果物と判定するためのマーカーファイル
BUILD_MARKERS = {
    "package.json",
    "pyproject.toml",
    "setup.py",
    "setup.cfg",
    "Cargo.toml",
    "tsconfig.json",
    "vite.config.ts",
    "vite.config.js",
    "webpack.config.js",
    "rollup.config.js",
    "angular.json",
    "Makefile",
    "CMakeLists.txt",
    "pom.xml",
    "build.gradle",
    "build.gradle.kts",
}

# チェックポイントの世代を格納する親ディレクトリの名前。
# この配下に限り、数字のみのディレクトリ名（例: 005000）を世代とみなす。
CHECKPOINT_PARENT_NAMES = {"checkpoints", "checkpoint", "ckpts", "ckpt"}

# 数字のみの世代ディレクトリ名（例: lerobot の 005000）
BARE_STEP_PATTERN = re.compile(r"^(\d+)$")

# 接頭辞付きの世代ディレクトリ名。名前自体が用途を示しているため、
# 親ディレクトリの名前に関わらず世代とみなしてよい。
PREFIXED_STEP_PATTERNS = (
    re.compile(r"^checkpoint[-_](\d+)$"),  # HuggingFace Trainer: checkpoint-500
    re.compile(r"^ckpt[-_](\d+)$"),        # ckpt-500
    re.compile(r"^step[-_](\d+)$"),        # step_1000
    re.compile(r"^epoch[-_](\d+)$"),       # epoch_10
)

# 「最新」「最良」の世代を指すシンボリックリンクの名前。
# これらが指す世代は、世代番号に関わらず保持する。
KEEP_LINK_NAMES = {"last", "latest", "best", "final"}


@dataclass
class Target:
    """削除対象の1件を表す。

    Attributes:
        path: 削除対象のディレクトリパス
        kind: 検出理由を示すラベル（表示用。例: node_modules, venv, checkpoint）
        size: ディレクトリの合計サイズ（バイト）。未計測の場合は0
    """

    path: Path
    kind: str
    size: int = field(default=0)


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


def has_build_marker(directory: Path) -> bool:
    """
    指定されたディレクトリにビルド設定ファイルが存在するかを判定する。

    dist / build のような一般的な名前のディレクトリを削除してよいかは、
    その親ディレクトリがビルド対象のプロジェクトかどうかで決まる。
    package.json や pyproject.toml などが同じ階層にあれば、
    配下の dist / build はビルド成果物とみなせる。

    Args:
        directory: dist / build の親ディレクトリ

    Returns:
        マーカーファイルが1つ以上存在する場合はTrue
    """
    return any((directory / marker).exists() for marker in BUILD_MARKERS)


def parse_step_number(name: str, allow_bare_number: bool) -> Optional[int]:
    """
    ディレクトリ名から学習ステップ数を取り出す。

    Args:
        name: ディレクトリ名
        allow_bare_number: 数字のみの名前（例: 005000）を世代として扱うか。
            checkpoints ディレクトリ配下でのみTrueにする。連番ディレクトリで
            構成されたデータセットを誤って世代と判定しないための制限。

    Returns:
        ステップ数。世代として解釈できない場合はNone
    """
    if allow_bare_number:
        match = BARE_STEP_PATTERN.match(name)
        if match:
            return int(match.group(1))

    for pattern in PREFIXED_STEP_PATTERNS:
        match = pattern.match(name)
        if match:
            return int(match.group(1))

    return None


def find_stale_checkpoints(
    parent: Path,
    keep_last: int,
    allow_bare_number: bool
) -> List[Path]:
    """
    指定ディレクトリ直下の古い世代のチェックポイントを検出する。

    保持するのは以下の世代:
    - ステップ数が大きい上位 keep_last 個
    - last / latest / best / final といったシンボリックリンクが指す世代

    数字のみの名前を世代として扱う場合 (allow_bare_number=True)、
    世代として解釈できないディレクトリが混在していれば、
    チェックポイント置き場ではないと判断して何も返さない。
    連番ディレクトリで構成されたデータセット等の誤削除を防ぐため。

    Args:
        parent: 世代ディレクトリを格納している親ディレクトリ
        keep_last: 保持する最新世代の数
        allow_bare_number: 数字のみの名前を世代として扱うか

    Returns:
        削除してよい世代ディレクトリのパスリスト
    """
    try:
        entries = list(parent.iterdir())
    except OSError:
        return []

    generations: List[Tuple[int, Path]] = []
    linked_targets: Set[Path] = set()
    has_unknown_dir = False

    for entry in entries:
        # last -> 030000 のようなリンクは、参照先を保持対象として記録する
        if entry.is_symlink():
            if entry.name.lower() in KEEP_LINK_NAMES:
                try:
                    linked_targets.add(entry.resolve())
                except OSError:
                    pass
            continue

        if not entry.is_dir():
            # 設定ファイルやログが混ざっていても世代判定には影響しない
            continue

        step = parse_step_number(entry.name, allow_bare_number)
        if step is None:
            has_unknown_dir = True
            continue

        generations.append((step, entry))

    # 数字のみを世代とみなす場合は、想定外のディレクトリがあれば処理しない
    if allow_bare_number and has_unknown_dir:
        return []

    if len(generations) <= keep_last:
        return []

    # ステップ数の降順に並べ、上位 keep_last 個とリンク先を保持する
    generations.sort(key=lambda item: item[0], reverse=True)

    keep: Set[Path] = set()
    for _, path in generations[:keep_last]:
        try:
            keep.add(path.resolve())
        except OSError:
            keep.add(path)
    keep |= linked_targets

    stale: List[Path] = []
    for _, path in generations:
        try:
            resolved = path.resolve()
        except OSError:
            resolved = path
        if resolved not in keep:
            stale.append(path)

    return stale


def get_directory_size(path: Path) -> int:
    """
    ディレクトリの合計サイズをバイト単位で算出する。

    シンボリックリンクは辿らず、リンク自体のサイズも加算しない。
    同じ実体を二重に数えないための措置。

    Args:
        path: 対象ディレクトリ

    Returns:
        合計サイズ（バイト）
    """
    total = 0

    for current_dir, _, files in os.walk(path, followlinks=False):
        current_path = Path(current_dir)
        for file_name in files:
            file_path = current_path / file_name
            try:
                stat_result = file_path.lstat()
            except OSError:
                continue
            # シンボリックリンク自体はサイズに含めない
            if not os.path.islink(file_path):
                total += stat_result.st_size

    return total


def format_size(size: int) -> str:
    """
    バイト数を読みやすい単位に変換する。

    Args:
        size: バイト数

    Returns:
        単位付きの文字列（例: "1.2 GB"）
    """
    units = ("B", "KB", "MB", "GB", "TB")
    value = float(size)

    for unit in units:
        if value < 1024.0 or unit == units[-1]:
            return f"{value:.1f} {unit}"
        value /= 1024.0

    return f"{value:.1f} TB"


def find_targets(
    root_path: Path,
    keep_last: int = 1,
    scan_checkpoints: bool = True
) -> List[Target]:
    """
    指定されたルートパス配下の削除対象を全て検索する。

    削除対象:
    - TARGET_DIRS: 名前が一致するディレクトリ（node_modules、cdk.out 等）
    - MARKER_REQUIRED_DIRS: 同階層にビルド設定がある dist / build
    - Python venv仮想環境: ディレクトリ名に関わらず内容で判定（is_python_venv参照）
    - 古い世代のチェックポイント（scan_checkpoints が True の場合）

    Args:
        root_path: 検索を開始するルートディレクトリ
        keep_last: チェックポイントで保持する最新世代の数
        scan_checkpoints: チェックポイントの世代削除を行うか

    Returns:
        検出された削除対象のリスト
    """
    targets: List[Target] = []

    try:
        for current_dir, subdirs, _ in os.walk(root_path):
            current_path = Path(current_dir)

            # ルート自体が削除対象として指定された場合
            if current_path.name in TARGET_DIRS:
                targets.append(Target(current_path, current_path.name))
                # 対象ディレクトリ内部は検索しない
                subdirs.clear()
                continue

            # 現在のディレクトリがPython venv仮想環境かチェック（名前を問わない）
            if is_python_venv(current_path):
                targets.append(Target(current_path, "venv"))
                # venv内部は検索しない
                subdirs.clear()
                continue

            # 古い世代のチェックポイントを検出する。
            # 保持する世代は subdirs に残すため、配下の探索は継続される。
            if scan_checkpoints:
                allow_bare_number = current_path.name.lower() in CHECKPOINT_PARENT_NAMES
                for stale_path in find_stale_checkpoints(
                    current_path, keep_last, allow_bare_number
                ):
                    targets.append(Target(stale_path, "checkpoint"))
                    if stale_path.name in subdirs:
                        subdirs.remove(stale_path.name)

            # サブディレクトリを種類ごとに判定する
            for subdir_name in list(subdirs):
                subdir_path = current_path / subdir_name

                if subdir_name in TARGET_DIRS:
                    targets.append(Target(subdir_path, subdir_name))
                    subdirs.remove(subdir_name)
                    continue

                # dist / build は同階層にビルド設定がある場合のみ対象
                if subdir_name in MARKER_REQUIRED_DIRS and has_build_marker(current_path):
                    targets.append(Target(subdir_path, subdir_name))
                    subdirs.remove(subdir_name)
                    continue

                if is_python_venv(subdir_path):
                    targets.append(Target(subdir_path, "venv"))
                    subdirs.remove(subdir_name)

    except PermissionError as e:
        print(f"Warning: Permission denied: {e}", file=sys.stderr)

    return targets


def measure_targets(targets: List[Target]) -> None:
    """
    各削除対象のサイズを計測し、Target に記録する。

    Args:
        targets: 計測対象のリスト（破壊的に更新される）
    """
    for target in targets:
        target.size = get_directory_size(target.path)


def display_targets(
    targets: List[Target],
    root_directory: Path,
    show_size: bool = True
) -> None:
    """
    検出された削除対象の一覧を表示する。

    Args:
        targets: 表示する削除対象のリスト
        root_directory: 相対パス表示用のルートディレクトリ
        show_size: サイズを表示するか
    """
    if not targets:
        print("No target directories found.")
        return

    total_size = sum(target.size for target in targets)
    plural = "ies" if len(targets) > 1 else "y"

    if show_size:
        print(f"\nFound {len(targets)} director{plural} ({format_size(total_size)}):\n")
    else:
        print(f"\nFound {len(targets)} director{plural}:\n")

    for target in targets:
        try:
            relative_path = target.path.relative_to(root_directory)
        except ValueError:
            relative_path = target.path

        label = f"[{target.kind}]"
        if show_size:
            print(f"  {label:<16}{format_size(target.size):>10}  {relative_path}/")
        else:
            print(f"  {label:<16}{relative_path}/")

    if show_size:
        print(f"\nTotal: {format_size(total_size)}")
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


def delete_targets(
    targets: List[Target],
    root_directory: Path,
    dry_run: bool = False
) -> Tuple[int, int]:
    """
    指定された削除対象を削除する。

    venvの場合は、削除前にrequirements.txtを
    自動生成する（既に存在する場合は上書き）。

    Args:
        targets: 削除対象のリスト
        root_directory: 相対パス表示用のルートディレクトリ
        dry_run: Trueの場合、実際には削除しない

    Returns:
        (削除に成功した件数, 解放されたサイズ) のタプル
    """
    deleted_count = 0
    freed_size = 0

    for target in targets:
        try:
            relative_path = target.path.relative_to(root_directory)
        except ValueError:
            relative_path = target.path

        # Python venv仮想環境の場合、削除前にrequirements.txtを生成
        if is_python_venv(target.path):
            export_venv_requirements(target.path, dry_run)

        try:
            if not dry_run:
                shutil.rmtree(target.path)
            print(f"Deleted: {relative_path}/")
            deleted_count += 1
            freed_size += target.size
        except OSError as error:
            print(f"Error deleting {relative_path}/: {error}", file=sys.stderr)

    return deleted_count, freed_size


def interactive_delete(
    targets: List[Target],
    root_directory: Path,
    dry_run: bool = False,
    show_size: bool = True
) -> Tuple[int, int, int]:
    """
    各削除対象の削除を対話的に確認する。

    venvの場合は、削除前にrequirements.txtを
    自動生成する（既に存在する場合は上書き）。

    Args:
        targets: 削除候補のリスト
        root_directory: 相対パス表示用のルートディレクトリ
        dry_run: Trueの場合、実際には削除しない
        show_size: サイズを表示するか

    Returns:
        (削除数, スキップ数, 解放されたサイズ) のタプル
    """
    if not targets:
        print("No target directories found.")
        return 0, 0, 0

    deleted_count = 0
    skipped_count = 0
    freed_size = 0

    for target in targets:
        try:
            relative_path = target.path.relative_to(root_directory)
        except ValueError:
            relative_path = target.path

        if show_size:
            print(f"\nFound: [{target.kind}] {relative_path}/ ({format_size(target.size)})")
        else:
            print(f"\nFound: [{target.kind}] {relative_path}/")
        print("Delete this directory? (yes/no/quit): ", end="")

        response = input().strip().lower()

        if response in ("quit", "q"):
            print("Aborted.")
            break
        elif response in ("yes", "y"):
            # Python venv仮想環境の場合、削除前にrequirements.txtを生成
            if is_python_venv(target.path):
                export_venv_requirements(target.path, dry_run)

            try:
                if not dry_run:
                    shutil.rmtree(target.path)
                print("Deleted.")
                deleted_count += 1
                freed_size += target.size
            except OSError as error:
                print(f"Error: Failed to delete: {error}", file=sys.stderr)
        elif response in ("no", "n"):
            print("Skipped.")
            skipped_count += 1
        else:
            print("Invalid input. Skipping.")
            skipped_count += 1

    return deleted_count, skipped_count, freed_size


def main() -> int:
    """
    Main entry point for nm_cleaner.

    Returns:
        Exit code (0 for success, 1 for error)
    """
    parser = argparse.ArgumentParser(
        description="node_modules, __pycache__, cdk.out, venv 等の再生成可能なディレクトリを再帰的に削除",
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
        "-k", "--keep-last",
        type=int,
        default=1,
        metavar="N",
        help="Number of latest checkpoint generations to keep (default: 1)"
    )
    parser.add_argument(
        "--no-checkpoints",
        action="store_true",
        help="Do not delete old checkpoint generations"
    )
    parser.add_argument(
        "--no-size",
        action="store_true",
        help="Skip size calculation (faster scan)"
    )
    parser.add_argument(
        "-v", "--version",
        action="version",
        version=f"%(prog)s {__version__}"
    )

    args = parser.parse_args()

    if args.keep_last < 1:
        print("Error: --keep-last must be 1 or greater.", file=sys.stderr)
        return 1

    root_directory = Path(args.directory).resolve()

    if not root_directory.exists():
        print(f"Error: Directory '{root_directory}' does not exist.", file=sys.stderr)
        return 1

    if not root_directory.is_dir():
        print(f"Error: '{root_directory}' is not a directory.", file=sys.stderr)
        return 1

    print(f"Scanning: {root_directory}")

    targets = find_targets(
        root_directory,
        keep_last=args.keep_last,
        scan_checkpoints=not args.no_checkpoints
    )

    show_size = not args.no_size
    if show_size and targets:
        print("Calculating sizes...")
        measure_targets(targets)
        # 削減効果が大きいものから確認できるよう、サイズの降順に並べる
        targets.sort(key=lambda target: target.size, reverse=True)
    else:
        targets.sort(key=lambda target: target.path)

    if args.interactive:
        # Interactive mode
        deleted, skipped, freed = interactive_delete(
            targets,
            root_directory,
            args.dry_run,
            show_size
        )
        print(f"\nDeleted: {deleted} director{'ies' if deleted != 1 else 'y'}")
        if skipped > 0:
            print(f"Skipped: {skipped} director{'ies' if skipped != 1 else 'y'}")
        if show_size and freed > 0:
            print(f"Freed: {format_size(freed)}")
    else:
        # Normal mode
        display_targets(targets, root_directory, show_size)

        if not targets:
            return 0

        if args.dry_run:
            print("Dry run mode - no directories were deleted.")
            return 0

        if not args.yes:
            if not confirm_deletion():
                print("Deletion cancelled.")
                return 0

        deleted, freed = delete_targets(targets, root_directory)
        print(f"\nDeleted {deleted} director{'ies' if deleted != 1 else 'y'}.")
        if show_size and freed > 0:
            print(f"Freed: {format_size(freed)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
