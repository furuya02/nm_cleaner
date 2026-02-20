# nm_cleaner

A command-line tool to clean `node_modules`, `__pycache__`, and `venv` directories recursively.

## Overview

`nm_cleaner` scans your project directory, identifies all `node_modules`, `__pycache__`, and Python `venv` virtual environment directories, and removes them after confirmation. This is useful for freeing up disk space by cleaning up unused Node.js project dependencies, Python cache files, and virtual environments.

## Features

- Recursively finds all `node_modules`, `__pycache__`, and `venv` directories
- Shows a list of directories to be deleted before deletion
- Asks for confirmation before deleting
- Supports interactive mode for individual confirmations
- Supports dry-run mode to preview what would be deleted
- Efficient scanning (doesn't search inside target directories)
- **Automatically generates requirements.txt before deleting venv** (skipped if already exists)

## venv Virtual Environment Detection

A `venv` directory is only detected for deletion if it meets **both** of the following conditions:

- `pyvenv.cfg` file exists
- `bin/activate` (Unix) or `Scripts/activate` (Windows) exists

This ensures that only virtual environments created by Python's `venv` module are targeted, preventing accidental deletion of regular directories simply named "venv".

### Automatic requirements.txt Generation

When deleting a venv, if `requirements.txt` does not exist in the project root (venv's parent directory), `pip freeze` is executed to automatically save the list of installed packages. This allows you to recreate the environment after venv deletion:

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## Installation

### Using pip

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
usage: nm_cleaner [-h] [-d DIRECTORY] [-i] [-n] [-y] [-v]

Clean node_modules, __pycache__, and venv directories recursively

options:
  -h, --help            show this help message and exit
  -d DIRECTORY, --directory DIRECTORY
                        Directory to clean (default: current directory)
  -i, --interactive     Interactive mode: confirm deletion for each directory
  -n, --dry-run         Show what would be deleted without actually deleting
  -y, --yes             Skip confirmation prompt
  -v, --version         show program's version number and exit
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

**Skip confirmation prompt:**

```bash
nm_cleaner --yes
```

**Combine options:**

```bash
nm_cleaner -d /path/to/projects --dry-run
```

## How it works

1. Scans the target directory recursively
2. Identifies all `node_modules`, `__pycache__`, and `venv` directories (doesn't search inside them for efficiency)
3. Displays a list of directories to be deleted
4. Asks for user confirmation (unless `-y` is used)
5. For venv directories, automatically generates requirements.txt if it doesn't exist
6. Deletes the confirmed directories

## Requirements

- Python 3.10 or higher

## License

MIT License

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.
