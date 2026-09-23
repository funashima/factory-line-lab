# 添付最新版からの変更

パッケージ整備日：2026-09-23。Python本体の版は1.0.0です。

## 追加したファイル

- `README.md`：本体が最上位、研究データが `research_data_pack/` にある現在の構成に対応。
- `variance_sweep.py`：構造2種類×投入間隔2種類×変動係数3種類の12条件を計算するスクリプト。
- `requirements-core.txt`、`requirements.txt`、`requirements-dev.txt`：CLI・GUI・テスト用の依存一覧。
- `tests/test_line_lab.py`：計算、再現性、保存、GUI編集を検証する27件のテスト。
- `examples/`：本体の `examples` コマンドで生成したJSON・CSV入力例。
- `results/benchmark/`、`results/variance/`：同梱本体と追加スクリプトで再実行した結果。
- `build_docs.py`：一時フォルダでLuaLaTeXを各2回実行し、新しい出力先にPDFとログを保存。
- `VALIDATION.json`、`SHA256SUMS`：今回の検証記録と配布ファイルの指紋。

## 更新した内容

- データ側のREADMEとLuaLaTeX原稿に残っていた旧フォルダ名を修正。
- 解説書のコンパイル対象名を `easy-guide.tex` に修正。
- 両方の `myfont-setting.sty` に、指定フォントがない場合の代替を追加。指定フォントがあれば優先して使用。
- 修正した原稿から2つのPDFを再作成。
- データ検証結果、パッケージ情報、データ側の指紋一覧を更新。

## 引き継いだ内容

Python本体、計画書、MITライセンス、原データ、変換済みJSON、抽出条件・変換処理は添付版と同一です。解説の表題・著者名・表紙の日付も維持しています。添付版の文書日付と取得記録の日付の差は、READMEに明記しました。

配布ZIPには実行に不要なキャッシュやTeXの中間ファイルを収録していません。
