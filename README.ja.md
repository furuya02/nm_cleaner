# nm_cleaner

再生成可能なディレクトリ（`node_modules`、`__pycache__`、`cdk.out`、各種ビルドキャッシュ、`venv`、古い学習チェックポイント）を再帰的に検索して削除するコマンドラインツール

## 概要

`nm_cleaner`は、指定されたディレクトリ配下を再帰的にスキャンし、ツールが自動生成した「消してもコマンド一つで元に戻せる」ディレクトリを見つけて削除します。削除前にサイズ付きの一覧を表示し、確認を求めるため、誤削除を防ぐことができます。バックアップ前の掃除や、ディスク容量の確保に便利です。

## 機能

- 再生成可能なディレクトリを再帰的に検索
- 削除対象のサイズと合計を表示（どれだけ空くかが分かる）
- 削除前に確認を求める
- 対話モードで1つずつ確認可能
- ドライランモードで削除せずにプレビュー可能
- 効率的なスキャン（対象ディレクトリ内部は検索しない）
- **venv削除時にrequirements.txtを自動生成**（既存の場合は上書き）
- **学習チェックポイントは最新世代だけを残して古い世代を削除**

## 削除対象

誤削除を防ぐため、判定を3段階に分けています。

### 1. 名前が一致すれば削除

その名前であればツールの生成物であることがほぼ確実なものに限定しています。

| ディレクトリ | 再生成方法 |
|---|---|
| `node_modules` | `npm install` 等 |
| `__pycache__` | 自動生成 |
| `cdk.out` | `cdk synth` |
| `.terraform` | `terraform init` |
| `.next` / `.nuxt` / `.svelte-kit` | 各フレームワークのビルド |
| `.turbo` / `.parcel-cache` | ビルドキャッシュ |
| `.pytest_cache` / `.mypy_cache` / `.ruff_cache` | 各ツールのキャッシュ |

### 2. マーカーファイルがある場合のみ削除

`dist` と `build` は写真の配布用フォルダなど一般的な用途でも使われる名前です。そのため、**同じ階層に以下のいずれかのファイルがある場合のみ**ビルド成果物とみなして削除します。

`package.json` / `pyproject.toml` / `setup.py` / `setup.cfg` / `Cargo.toml` / `tsconfig.json` / `vite.config.ts` / `vite.config.js` / `webpack.config.js` / `rollup.config.js` / `angular.json` / `Makefile` / `CMakeLists.txt` / `pom.xml` / `build.gradle` / `build.gradle.kts`

```
project/
├── package.json   ← マーカーあり
└── dist/          ← 削除対象

photos/
└── dist/          ← マーカー無し。削除しない
```

### 3. 内容で判定（venv仮想環境）

`venv`ディレクトリは、**ディレクトリ名に関わらず**、以下の条件を**両方満たす場合のみ**削除対象として検出されます。

- `pyvenv.cfg`ファイルが存在する
- `bin/activate`（Unix系）または`Scripts/activate`（Windows）が存在する

これにより、Pythonの`venv`モジュールや`uv`等で作成された仮想環境のみが対象となり、同名の通常ディレクトリを誤って削除することを防ぎます。

#### requirements.txt自動生成

venv削除時、プロジェクトルート（venvの親ディレクトリ）に`pip freeze`を実行して依存パッケージの一覧を`requirements.txt`として保存します（既存の場合は上書き）。これにより、venv削除後も以下のコマンドで環境を再構築できます：

```bash
python -m venv venv
source venv/bin/activate  # Windowsの場合: venv\Scripts\activate
pip install -r requirements.txt
```

## 学習チェックポイントの世代削除

機械学習の`checkpoints`ディレクトリには学習途中の世代が蓄積し、容量の大半を占めることがあります。`nm_cleaner`は**最新の世代だけを残して古い世代を削除**します。

```
outputs/train/my_model/checkpoints/
├── 005000/   ← 削除
├── 010000/   ← 削除
├── 030000/   ← 残す
└── last -> 030000
```

### 対応する形式

| 形式 | 例 | 条件 |
|---|---|---|
| 数字のみ | `005000` | 親が `checkpoints` / `checkpoint` / `ckpts` / `ckpt` の場合のみ |
| 接頭辞付き | `checkpoint-500`、`ckpt_500`、`step_1000`、`epoch_10` | 親の名前は問わない |

### 誤削除を防ぐ仕組み

- `last` / `latest` / `best` / `final` のシンボリックリンクが指す世代は、世代番号に関わらず**必ず残します**
- 数字のみのディレクトリ名は、親が`checkpoints`等の場合にのみ世代とみなします。これにより`frames/000`、`frames/001` のような連番データセットを誤って削除しません
- `checkpoints`配下に世代として解釈できないディレクトリが混在している場合は、構成を誤認している可能性があるため**何も削除しません**

世代削除を行いたくない場合は`--no-checkpoints`を指定してください。保持する世代数は`--keep-last N`で変更できます。

## インストール

```bash
git clone https://github.com/furuya02/nm_cleaner.git
cd nm_cleaner
pip install -e .
```

pipでインストール後、`nm_cleaner`コマンドがグローバルに使用可能になります：

```bash
nm_cleaner
```

## 使用方法

### 基本的な使い方

ディレクトリに移動して実行：

```bash
nm_cleaner
```

### オプション

```
usage: nm_cleaner [-h] [-d DIRECTORY] [-i] [-n] [-y] [-k N]
                  [--no-checkpoints] [--no-size] [-v]

node_modules, __pycache__, cdk.out, venv 等の再生成可能なディレクトリを再帰的に削除

options:
  -h, --help            ヘルプメッセージを表示して終了
  -d DIRECTORY, --directory DIRECTORY
                        対象ディレクトリ（デフォルト: カレントディレクトリ）
  -i, --interactive     対話モード: 各ディレクトリごとに削除確認
  -n, --dry-run         実際には削除せず、削除対象を表示
  -y, --yes             確認プロンプトをスキップ
  -k N, --keep-last N   保持する最新チェックポイント世代の数（デフォルト: 1）
  --no-checkpoints      古いチェックポイントを削除しない
  --no-size             サイズ計算をスキップ（スキャンが高速になる）
  -v, --version         バージョン情報を表示して終了
```

### 出力例

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

### 使用例

**削除対象をプレビュー（ドライランモード）：**

```bash
nm_cleaner --dry-run
```

**特定のディレクトリを指定：**

```bash
nm_cleaner -d /path/to/projects
```

**対話モード（各ディレクトリを個別に確認）：**

```bash
nm_cleaner -i
```

**チェックポイントを最新3世代まで残す：**

```bash
nm_cleaner --keep-last 3
```

**チェックポイントには手を触れない：**

```bash
nm_cleaner --no-checkpoints
```

**確認プロンプトをスキップ：**

```bash
nm_cleaner --yes
```

## 動作の仕組み

1. 対象ディレクトリを再帰的にスキャン
2. 削除対象を特定（効率化のため対象の内部は検索しない）
3. 各対象のサイズを計測（`--no-size`でスキップ可能）
4. サイズの大きい順に一覧を表示
5. ユーザーに確認を求める（`-y`オプションがない場合）
6. venvの場合、requirements.txtを生成
7. 確認されたディレクトリを削除し、解放されたサイズを表示

## 必要要件

- Python 3.10以上

## ライセンス

MIT License

## コントリビューション

コントリビューションは歓迎します！お気軽にPull Requestを送ってください。
