# nm_cleaner

A command-line tool to recursively clean regenerable directories: `node_modules`, `__pycache__`, `cdk.out`, build caches, `venv`, and stale training checkpoints.

## Overview

`nm_cleaner` scans a directory recursively and finds directories that tools generate automatically — the kind you can recreate with a single command. It shows a size-annotated list and asks for confirmation before deleting, so nothing disappears by surprise. Useful for cleaning up before a backup, or for reclaiming disk space.

## Features

- Recursively finds regenerable directories
- Shows the size of each target and the total (so you know how much you will free)
- Asks for confirmation before deleting
- Supports interactive mode for individual confirmations
- Supports dry-run mode to preview what would be deleted
- Efficient scanning (doesn't search inside target directories)
- **Automatically generates requirements.txt before deleting a venv** (overwrites if it exists)
- **Keeps only the latest training checkpoint generation and removes older ones**

## What gets deleted

Detection happens in three tiers to avoid deleting anything you cannot regenerate.

### 1. Deleted by name

Limited to names that are almost certainly tool output.

| Directory | How to regenerate |
|---|---|
| `node_modules` | `npm install`, etc. |
| `__pycache__` | Generated automatically |
| `cdk.out` | `cdk synth` |
| `.terraform` | `terraform init` |
| `.next` / `.nuxt` / `.svelte-kit` | Framework build |
| `.turbo` / `.parcel-cache` | Build cache |
| `.pytest_cache` / `.mypy_cache` / `.ruff_cache` | Tool cache |

### 2. Deleted only when a marker file is present

`dist` and `build` are ordinary English words — a folder of photos might well be named `dist`. They are treated as build output **only when one of these files sits in the same directory**:

`package.json` / `pyproject.toml` / `setup.py` / `setup.cfg` / `Cargo.toml` / `tsconfig.json` / `vite.config.ts` / `vite.config.js` / `webpack.config.js` / `rollup.config.js` / `angular.json` / `Makefile` / `CMakeLists.txt` / `pom.xml` / `build.gradle` / `build.gradle.kts`

```
project/
├── package.json   ← marker present
└── dist/          ← deleted

photos/
└── dist/          ← no marker; left alone
```

### 3. Detected by content (venv)

A virtual environment is detected **regardless of its directory name**, and only when **both** conditions hold:

- `pyvenv.cfg` exists
- `bin/activate` (Unix) or `Scripts/activate` (Windows) exists

This targets only environments created by Python's `venv` module, so a regular directory that happens to be named `venv` is never removed.

#### Automatic requirements.txt generation

Before deleting a venv, `pip freeze` writes the installed package list to `requirements.txt` in the project root (the venv's parent directory), overwriting any existing file. You can then recreate the environment:

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## Checkpoint generation cleanup

Machine learning `checkpoints` directories accumulate intermediate generations that often dominate disk usage. `nm_cleaner` **keeps the newest generation and removes older ones**.

```
outputs/train/my_model/checkpoints/
├── 005000/   ← deleted
├── 010000/   ← deleted
├── 030000/   ← kept
└── last -> 030000
```

### Supported layouts

| Layout | Example | Condition |
|---|---|---|
| Bare number | `005000` | Only when the parent is `checkpoints` / `checkpoint` / `ckpts` / `ckpt` |
| Prefixed | `checkpoint-500`, `ckpt_500`, `step_1000`, `epoch_10` | Parent name does not matter |

### Safeguards

- A generation pointed to by a `last` / `latest` / `best` / `final` symlink is **always kept**, whatever its number
- Bare numeric names count as generations only under a `checkpoints`-style parent, so a numbered dataset such as `frames/000`, `frames/001` is never mistaken for checkpoints
- If a `checkpoints` directory contains anything that cannot be read as a generation, **nothing there is deleted** — the layout is probably not what we assume

Use `--no-checkpoints` to skip this entirely, or `--keep-last N` to keep more generations.

## Installation

```bash
git clone https://github.com/furuya02/nm_cleaner.git
cd nm_cleaner
pip install -e .
```

After installing with pip, the `nm_cleaner` command will be available globally:

```bash
nm_cleaner
```

## Usage

### Basic usage

Navigate to a directory and run:

```bash
nm_cleaner
```

### Options

```
usage: nm_cleaner [-h] [-d DIRECTORY] [-i] [-n] [-y] [-k N]
                  [--no-checkpoints] [--no-size] [-v]

Clean regenerable directories (node_modules, __pycache__, cdk.out, venv, ...) recursively

options:
  -h, --help            show this help message and exit
  -d DIRECTORY, --directory DIRECTORY
                        Directory to clean (default: current directory)
  -i, --interactive     Interactive mode: confirm deletion for each directory
  -n, --dry-run         Show what would be deleted without actually deleting
  -y, --yes             Skip confirmation prompt
  -k N, --keep-last N   Number of latest checkpoint generations to keep (default: 1)
  --no-checkpoints      Do not delete old checkpoint generations
  --no-size             Skip size calculation (faster scan)
  -v, --version         show program's version number and exit
```

### Sample output

```
$ nm_cleaner -d ~/Data --dry-run
Scanning: /Users/xxx/Data
Calculating sizes...

Found 8 directories (10.9 GB):

  [cdk.out]           8.5 GB  Business/proposal/poc/cdk/cdk.out/
  [checkpoint]      394.0 MB  ml/outputs/train/v1/checkpoints/005000/
  [checkpoint]      394.0 MB  ml/outputs/train/v1/checkpoints/010000/
  [node_modules]    120.0 MB  tools/web/node_modules/
  ...

Total: 10.9 GB

Dry run mode - no directories were deleted.
```

### Examples

**Preview directories to be deleted (dry-run mode):**

```bash
nm_cleaner --dry-run
```

**Clean a specific directory:**

```bash
nm_cleaner -d /path/to/projects
```

**Interactive mode (confirm each directory):**

```bash
nm_cleaner -i
```

**Keep the latest three checkpoint generations:**

```bash
nm_cleaner --keep-last 3
```

**Leave checkpoints untouched:**

```bash
nm_cleaner --no-checkpoints
```

**Skip confirmation prompt:**

```bash
nm_cleaner --yes
```

## How it works

1. Scans the target directory recursively
2. Identifies targets (doesn't search inside them for efficiency)
3. Measures the size of each target (skippable with `--no-size`)
4. Displays the list, largest first
5. Asks for user confirmation (unless `-y` is used)
6. Generates requirements.txt for venv directories
7. Deletes the confirmed directories and reports the space freed

## Requirements

- Python 3.10 or higher

## License

MIT License

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.
