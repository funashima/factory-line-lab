# 研究用データセット — Factory Line Lab同梱版

1つ上のフォルダにある `mock_line_editor.py` v1.0.0 用のデータです。導入手順と全体構成は [全体のREADME](../README.md) を参照してください。原典、抽出条件、仮定、制約は **data_sources_guide.tex** と確認用PDFに記載しています。

## まず使うファイル

| ファイル | 内容 | 用途 |
|---|---|---|
| `json/jackson_11.json` | 公表ベンチマーク・11作業、13接続 | 分岐・合流を小さな例で確認 |
| `json/mitchell_21.json` | 公表ベンチマーク・21作業、27接続 | 20工程程度で比較 |
| `json/heskia_28.json` | 公表ベンチマーク・28作業、39接続 | 30工程に近い規模で比較 |
| `json/smart_factory_10_mean.json` | 実験工場ログの10作業を標本平均で固定 | 実測値との対応を理解する最初の例 |
| `json/smart_factory_10_lognormal.json` | 同じ平均・標本標準偏差から作る対数正規分布の近似 | 分布を仮定した場合の試行。分布形は未検証 |

5件はすべてGUIの「JSON読込」から読み込めます。JSONの工程、接続、配置、実験条件は編集・保存できます。**GUIで再保存すると追加の出典メタデータは落ちるため、配布JSONと `json/provenance.json` を原本として残し、編集版は別名で保存してください。**

以下の3ファイルは資料用であり、GUI入力ではありません。

- `json/smart_factory_observations.json`：15生産×10作業の150件の観測値、元の記録ID・配列位置、開始・終了時刻。
- `json/provenance.json`：原ファイルのSHA256、抽出条件、統計量、作業・接続の対応、追加仮定。
- `json/catalog.json`：5つの入力モデルの一覧。

## 実行例

パッケージの最上位 `factory-line-lab/` から始める例です。最初の `cd` の後は、このデータフォルダ内で実行します。

```bash
cd research_data_pack
python ../mock_line_editor.py validate --model json/jackson_11.json
python ../mock_line_editor.py run \
  --model json/smart_factory_10_mean.json --out my_results/mean
python ../mock_line_editor.py run \
  --model json/smart_factory_10_lognormal.json --out my_results/lognormal
python ../mock_line_editor.py run \
  --model json/heskia_28.json --jobs 60 --runs 1 --interval 1 \
  --out my_results/heskia
```

出力先には新規または空のフォルダを使ってください。Python本体と依存ライブラリ一覧は1つ上のフォルダに同梱されています。

## 原典と大切な制約

**Scholl (1993) の配布データ**：https://assembly-line-balancing.de/salbp/benchmark-data-sets-1993/

JACKSON / MITCHELL / HESKIA の作業時間と先行関係をそのまま変換しました。時間単位は原IN2に明記されていないため「秒」とはしません。元の問題は作業を作業台へ割り当てる問題です。本プログラムの「各作業に独立した設備1台」は追加仮定です。実工場の測定ログではなく、標準偏差や実測ボトルネックの正解はありません。

**Ronny Seiger, Zenodo (2024)**：https://doi.org/10.5281/zenodo.14441997

St.Gallen大学のFischertechnik小型実験工場の公開記録です。2023-04-11、`production_process_new3`、バージョン2、完了済みの15生産だけを採用しました。各自動作業の `durationInMillis / 1000` を使用し、外れ値を削除していません。ユーザー操作・開始/終了イベントは除外しました。

これは制御ソフトが記録した作業の経過時間であり、純粋な加工時間とは限りません。同じロボットを複数工程が共用する制約を既存プログラムは扱えないため、実測由来の2モデルの既定値は **製品1個** です。製品数を増やした結果で実工場の生産能力やボトルネックを断定しないでください。

## 再作成・確認

原データは `sources/` に収録しています。BPMNは工程順を表すXML形式です。大型のセンサーログ2件は取得していません。必要な開始/終了時刻と経過時間は取得済みの工程ログにあります。

```bash
# Python標準ライブラリのみ。既存ファイルを守るため空の出力先が必要。
python convert_sources.py --out rebuilt

# 本体のコアライブラリが必要。5モデルと15生産の整合性を検証。
python verify_data.py --program ../mock_line_editor.py

# LuaLaTeX原稿は図・表を内蔵。同じフォルダのmyfont-setting.styも必要。
lualatex data_sources_guide.tex
lualatex data_sources_guide.tex
```

LuaLaTeXには `luatexja`、HaranoAji・Latin Modernフォント、`tikz`、`tcolorbox` などを含むTeX Live環境を使用してください。`myfont-setting.sty` は添付版の指定フォントを優先し、見つからなければ代替フォントを使います。PDFの作成に原データファイルは不要です。2文書をまとめて作る `../build_docs.py` の手順は全体のREADMEにあります。

実施済みの確認結果は `validation.json`（今回再確認済み）、配布ファイルの指紋は `SHA256SUMS` にあります。検証は形式・計算の整合性を調べたもので、現実の工場モデルの妥当性の証明ではありません。

## 取得記録の日付

添付文書の表紙は2026-09-21、`sources/acquisition.json` は2026-09-23を記録しており、日付に差があります。双方を維持しています。取得元・取得経緯を追跡する際は `sources/acquisition.json` と `json/provenance.json` を参照してください。

## 利用条件

Zenodoデータのメタデータ上のライセンスはCC BY 4.0です。著者、DOI、変換した旨を示してください。Schollサイトは独自の利用条件を掲示しており、CC BYとはしません。詳細は `SOURCE_NOTICES.md` を参照してください。
