# nm_cleaner

`node_modules`、`__pycache__`、`venv`ディレクトリを再帰的に検索して削除するコマンドラインツール

## 概要

`nm_cleaner`は、指定されたディレクトリ配下を再帰的にスキャンし、すべての`node_modules`、`__pycache__`、およびPythonの`venv`仮想環境ディレクトリを見つけて削除します。削除前にユーザーに確認を求めるため、誤削除を防ぐことができます。使用していないNode.jsプロジェクトの依存関係、Pythonのキャッシュファイル、仮想環境を削除してディスク容量を節約するのに便利です。

## 機能

- すべての`node_modules`、`__pycache__`、`venv`ディレクトリを再帰的に検索
- 削除前にディレクトリ一覧を表示
- 削除前に確認を求める
- 対話モードで1つずつ確認可能
- ドライランモードで削除せずにプレビュー可能
- 効率的なスキャン（対象ディレクトリ内部は検索しない）
- **venv削除時にrequirements.txtを自動生成**（既存の場合はスキップ）

## venv仮想環境の検出

`venv`ディレクトリは、以下の条件を**両方満たす場合のみ**削除対象として検出されます：

- `pyvenv.cfg`ファイルが存在する
- `bin/activate`（Unix系）または`Scripts/activate`（Windows）が存在する

これにより、Pythonの`venv`モジュールで作成された仮想環境のみが対象となり、単に「venv」という名前の通常ディレクトリを誤って削除することを防ぎます。

### requirements.txt自動生成

venv削除時、プロジェクトルート（venvの親ディレクトリ）に`requirements.txt`が存在しない場合、`pip freeze`を実行して依存パッケージの一覧を自動的に保存します。これにより、venv削除後も以下のコマンドで環境を再構築できます：

```bash
python -m venv venv
source venv/bin/activate  # Windowsの場合: venv\Scripts\activate
pip install -r requirements.txt
```

## インストール

### pipを使用

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
usage: nm_cleaner [-h] [-d DIRECTORY] [-i] [-n] [-y] [-v]

node_modules, __pycache__, venvディレクトリを再帰的に削除します

options:
  -h, --help            ヘルプメッセージを表示して終了
  -d DIRECTORY, --directory DIRECTORY
                        対象ディレクトリ（デフォルト: カレントディレクトリ）
  -i, --interactive     対話モード: 各ディレクトリごとに削除確認
  -n, --dry-run         実際には削除せず、削除対象を表示
  -y, --yes             確認プロンプトをスキップ
  -v, --version         バージョン情報を表示して終了
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

**確認プロンプトをスキップ：**

```bash
nm_cleaner --yes
```

**オプションの組み合わせ：**

```bash
nm_cleaner -d /path/to/projects --dry-run
```

## 動作の仕組み

1. 対象ディレクトリを再帰的にスキャン
2. すべての`node_modules`、`__pycache__`、`venv`ディレクトリを特定（効率化のため内部は検索しない）
3. 削除対象のディレクトリ一覧を表示
4. ユーザーに確認を求める（`-y`オプションがない場合）
5. venvの場合、requirements.txtが存在しなければ自動生成
6. 確認されたディレクトリを削除

## 必要要件

- Python 3.10以上

## ライセンス

MIT License

## コントリビューション

コントリビューションは歓迎します！お気軽にPull Requestを送ってください。
