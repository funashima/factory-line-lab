# Factory Line Lab — Pythonプログラムと研究用データの使い方

工程の順番、処理時間、設備台数を設定し、製品が完成するまでの時間や設備待ちを調べる研究用プログラムです。画面で工程を編集するGUIと、コマンドで繰り返し実験するCLIを備えています。

このREADMEは、最新版の **`factory-line-lab/` にPython本体・研究用データ・解説文書をまとめた構成**に対応しています。対象プログラムは `mock_line_editor.py` v1.0.0です。今回のパッケージ整備では、本体と研究データの値を維持し、不足していた実行補助ファイル・サンプル・検証結果を追加しました。

工程・接続・画面配置・実験条件はJSONで保存し、読み込み直して変更できます。研究用データについては、原典の値と、計算のために追加した仮定を区別して扱います。

## 1. 必要なファイルと配置

`factory-line-lab.zip`を展開し、`mock_line_editor.py`があるフォルダへ移動します。エクスプローラーやFinderで展開しても構いません。

```bash
unzip factory-line-lab.zip
cd factory-line-lab
```


| パス | 役割 |
|---|---|
| [mock_line_editor.py](mock_line_editor.py) | 実行本体。データ読込、計算、GUI、CLI |
| [variance_sweep.py](variance_sweep.py) | 仮想ラインの構造・投入間隔・ばらつきを12条件で比較 |
| [build_docs.py](build_docs.py) | 2つのLuaLaTeX原稿を、それぞれ2回コンパイル |
| `requirements-core.txt` / `requirements.txt` / `requirements-dev.txt` | CLI用／GUI用／開発検証用のライブラリ一覧 |
| `examples/` | 直列・分岐ラインと5シナリオのJSON・CSV入力例 |
| `results/benchmark/` / `results/variance/` | 今回再実行した5シナリオ・12条件の結果 |
| [tests/test_line_lab.py](tests/test_line_lab.py) | 計算式・再現性・保存・GUI編集等の自動テスト |
| [plan.md](plan.md) | 添付された研究計画 |
| `docs/easy-guide.tex` / `docs/easy-guide.pdf` | 本体の仕組みと操作の解説 |
| `research_data_pack/json/` | 公開データに基づく入力モデルと資料用JSON |
| `research_data_pack/sources/` | 原ファイルと取得記録 |
| [convert_sources.py](research_data_pack/convert_sources.py) | 原ファイルからJSONを再生成 |
| [verify_data.py](research_data_pack/verify_data.py) | データと本体の互換性・計算の整合性を確認 |
| [データ側のREADME](research_data_pack/README.md) | 研究用データの案内 |
| [VALIDATION.json](VALIDATION.json) | 今回のパッケージ検証結果 |
| [PACKAGE_CHANGES.md](PACKAGE_CHANGES.md) | 添付最新版から追加・修正した内容 |
| `SHA256SUMS` | 配布ファイルの指紋。再計算後のファイルとは一致しなくなります |
| [LICENSE](LICENSE) | プログラムのMITライセンス。原データの条件は15節を参照 |

Python本体・依存ライブラリの指定・研究用データがこのZIPに入っています。ライブラリそのものは、次の手順でインストールします。

## 2. 導入

### GUIを含めて使う場合

Python 3.12とLinuxで動作確認しています。以下はPython 3.12が利用できる環境での手順です。最初に `python3 --version` で使用する版を確認してください。

```bash
python3 --version
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

`python3`が別の版を指す場合は、導入済みのPython 3.12を `python3.12 -m venv .venv` のように指定してください。

インストール後は、仮想環境内の `python` を使います。新しく端末を開いたときは、作業フォルダへ移動してから次を実行します。

```bash
source .venv/bin/activate
```

Ubuntuで仮想環境を作成できず、`venv`や`ensurepip`がないというエラーが出る場合は、使用中のPythonに対応するvenvパッケージを導入してください。Ubuntu標準のPythonを使う場合の例は次のとおりです。

```bash
sudo apt install python3-venv
```

### 画面を使わず、CLIだけで計算する場合

仮想環境を作成・有効化した後、次の依存ファイルだけを導入できます。Qt関連ライブラリは不要です。

```bash
python -m pip install -r requirements-core.txt
```

### 使用ライブラリ

| ライブラリ | 配布時の指定版 | 主な用途 |
|---|---|---|
| NumPy | 2.3.5 | 乱数、配列、時間標本の計算 |
| NetworkX | 3.7 | 工程グラフ、循環の検査、工程順序 |
| SciPy | 1.17.0 | 平均の95%信頼区間 |
| Matplotlib | 3.10.8 | 結果のPNG・PDF出力 |
| PyQt6 | 6.11.0 | GUIのウィンドウと操作部品 |
| pyqtgraph | 0.14.0 | GUI内のグラフ |
| pytest | 9.1.1 | 開発・検証用。通常の実行には不要 |

`convert_sources.py`によるデータ変換はPython標準ライブラリだけで実行できます。`verify_data.py`はシミュレーターを読み込むため、コアライブラリが必要です。LuaLaTeXは文書を再コンパイルするときだけ必要です。

## 3. 最初の動作確認

まず、小さなJACKSONモデルの工程と接続を検査します。

```bash
python mock_line_editor.py validate \
  --model research_data_pack/json/jackson_11.json
```

正常なら次のように表示されます。

```text
OK: 11 processes, 13 edges, AND-fork/join DAG
```

続いて、実測の平均時間を使う10工程モデルを実行します。

```bash
python mock_line_editor.py run \
  --model research_data_pack/json/smart_factory_10_mean.json \
  --out results/smart_mean_01
```

このJSONの既定値は製品1個・試行1回です。全体完了時間は約 **238.159秒** になり、`results/smart_mean_01/` にCSV・JSON・図が保存されます。

この値は、モデル化した10個の自動作業の平均時間の合計です。人による色入力や作業間の小さな時間差を含む、生産全体の実測経過時間とは区別してください。

出力先は、存在しないフォルダまたは空のフォルダを指定します。同じコマンドを再実行する際は、例えば `results/smart_mean_02` に変更してください。

## 4. GUIで工程を編集・実行する

```bash
python mock_line_editor.py
```

起動直後は内蔵の分岐例が表示されます。研究用データを使うときは次の手順で読み込みます。

1. ツールバーの「JSON読込」を選ぶ。
2. `research_data_pack/json/` 内の入力モデルを選ぶ。
3. 左側の製品数・試行回数・投入間隔・seed・処理時間短縮率を確認する。
4. 「シミュレーション実行」を押す。
5. 「完了時間」「設備待ち」「改善効果」「数値表」の各タブで結果を見る。
6. 「結果を保存 (CSV・図・JSON)」で、空の出力フォルダを選ぶ。

| 操作 | 方法 |
|---|---|
| 工程を追加 | 「工程追加」 |
| 工程を接続 | 接続元の橙端子をクリックし、接続先の青端子をクリック |
| 処理時間・設備台数などを変更 | 工程を選択し、左側の「工程の設定」を編集 |
| 工程の配置を変更 | 工程をドラッグ |
| 拡大・縮小 | マウスホイール |
| 表示位置を移動 | 中ボタンを押してドラッグ |
| 図全体を表示 | 「全体表示」 |
| 工程・接続を削除 | 対象を選び「選択削除」またはDelete |
| 接続操作を取り消す | Esc |
| 工程と条件を保存 | 「JSON保存」 |

「JSON保存」は入力条件の保存、「結果を保存」は計算結果の出力です。工程や条件を変更すると古い結果は無効になるため、再度シミュレーションを実行してください。

## 5. Research dataの内容と選び方

### シミュレーターへ読み込む5つのJSON

次のファイルは、GUIの「JSON読込」またはCLIの `run --model` で使えます。

| ファイル | 作業・接続数 | 時間の設定 | 既定の製品数／試行回数／投入間隔 |
|---|---|---|---|
| [jackson_11.json](research_data_pack/json/jackson_11.json) | 11作業・13接続 | 原典の定数値 | 60／1／1 |
| [mitchell_21.json](research_data_pack/json/mitchell_21.json) | 21作業・27接続 | 原典の定数値 | 60／1／1 |
| [heskia_28.json](research_data_pack/json/heskia_28.json) | 28作業・39接続 | 原典の定数値 | 60／1／1 |
| [smart_factory_10_mean.json](research_data_pack/json/smart_factory_10_mean.json) | 10作業・9接続 | 実測の標本平均で固定 | 1／1／0 |
| [smart_factory_10_lognormal.json](research_data_pack/json/smart_factory_10_lognormal.json) | 10作業・9接続 | 実測平均・標準偏差による対数正規近似 | 1／50／0 |

分岐と合流の動作を理解するにはJACKSON、規模を広げるにはMITCHELL・HESKIAを使えます。実測値との対応を確認するには `smart_factory_10_mean.json` から始めてください。

**時間単位に注意してください。** 標準問題3件は原IN2ファイルに単位が明記されていないため、任意の時間単位として扱います。実験工場由来の2件は秒です。GUIや図の共通ラベルだけから単位を判断しないでください。

全入力モデルのseedは42、改善比較の短縮率は10%です。設備台数、製品数、投入間隔などの追加設定は、原典で観測された条件とは限りません。

### 観測値・出典を確認するためのJSON

次の3件は資料用です。シミュレーターの入力モデルとしては開けません。

| ファイル | 内容 |
|---|---|
| [smart_factory_observations.json](research_data_pack/json/smart_factory_observations.json) | 15生産×10作業の150件の観測値。元の記録ID、開始・終了時刻、作業時間 |
| [provenance.json](research_data_pack/json/provenance.json) | 原ファイルの指紋、抽出条件、統計量、工程・接続の対応、追加した仮定 |
| [catalog.json](research_data_pack/json/catalog.json) | 5入力モデルの一覧と既定条件 |

実験工場データは、2023年4月11日、`production_process_new3`のバージョン2、完了済み生産に限定しています。開始・終了イベントと人による色入力を除外し、10個の自動作業を採用しました。小さな時間値を含め、外れ値の削除は行っていません。

## 6. CLIで条件を指定して実験する

### 公開ベンチマークを実行

```bash
python mock_line_editor.py run \
  --model research_data_pack/json/heskia_28.json \
  --jobs 60 --runs 1 --interval 1 --seed 42 \
  --out results/heskia_01
```

### 実測由来の対数正規近似を実行

```bash
python mock_line_editor.py run \
  --model research_data_pack/json/smart_factory_10_lognormal.json \
  --jobs 1 --runs 50 --seed 42 \
  --out results/smart_lognormal_01
```

### 主な引数

| 引数 | 意味 |
|---|---|
| `--model PATH` | 入力モデルJSON |
| `--csv-dir DIR` | `proc_time.csv`と`edges.csv`を含むフォルダ。`--model`との併用は不可 |
| `--out DIR` | 結果の保存先。新規または空のフォルダ |
| `--jobs 60` | 1試行で投入する製品数 |
| `--runs 50` | 条件を繰り返して計算する回数 |
| `--interval 1` | 製品を投入する時間間隔。工程時間と同じ単位 |
| `--seed 42` | 乱数系列を再現するための整数 |
| `--improvement 0.1` | 各工程の処理時間を10%短縮して比較。GUIでは「10 %」と表示 |
| `--no-sensitivity` | 工程ごとの改善比較を省略 |
| `--no-figures` | PNG・PDFの図出力を省略 |
| `--all-traces` | 全基準試行の製品・工程別の時刻表を保存 |

条件の優先順位は **CLIで明示した値 → 入力JSONの `simulation` → プログラムの既定値** です。

確率的な入力では、試行回数を増やすと乱数による変動を調べやすくなります。定数だけのモデルでは、同じ条件を繰り返しても同じ結果になります。改善比較は各工程を一つずつ変更して再計算するため、工程数と試行回数を増やすと計算量も増えます。

ヘルプは次のように確認できます。

```bash
python mock_line_editor.py --help
python mock_line_editor.py run --help
```

## 7. 工程を変更し、JSONで管理する

作業用フォルダを作り、配布モデルをコピーしてから変更すると、原データとの比較がしやすくなります。

```bash
mkdir -p models
cp research_data_pack/json/jackson_11.json models/jackson_working.json
```

GUIで `models/jackson_working.json` を開き、工程、接続、時間、設備台数、実験条件を変更して保存してください。例えば、投入間隔だけを変えた版は `models/jackson_interval2.json` のように別名にします。

| JSONの項目 | 保存する内容 |
|---|---|
| `nodes` | 工程ID、工程名、時間分布、設備台数 |
| `edges` | 接続ID、前工程`src`、後工程`dst` |
| `layout` | 各工程の画面上の座標 |
| `simulation` | 製品数、試行回数、投入間隔、seed、改善比較の条件 |
| `meta.version` | JSON形式のバージョン。配布モデルは2 |

工程IDを直接変更するときは、関連する接続と配置のIDも合わせて変更してください。工程IDは乱数系列にも使うため、条件比較では同じ工程のIDを維持する方が比較しやすくなります。

接続途中の下書きはGUIで保存・再読込できます。計算時には、孤立や分離のない、循環しない工程ネットワークが必要です。下書きの保存に成功しても、計算可能とは限りません。

### 出典情報と変更履歴を残す

**現在のプログラムは、追加した出典情報をGUIで再保存したときや、結果の `model.json` を出力したときに引き継ぎません。** 工程と実験条件は残りますが、原データのDOI・取得URL・仮定を自動で保存し続ける仕組みではありません。

配布JSON、`research_data_pack/json/provenance.json`、`research_data_pack/sources/`を保持し、変更版とは分けて管理してください。必要に応じ、次のような**資料用の変更記録JSON**を別に保存できます。

```json
{
  "record_type": "model_change_log",
  "based_on": "research_data_pack/json/jackson_11.json",
  "saved_model": "models/jackson_interval2.json",
  "changes": [
    {
      "field": "simulation.interval",
      "before": 1.0,
      "after": 2.0,
      "reason": "投入間隔が設備待ちに与える影響を比較する"
    }
  ]
}
```

これは記録方法の例であり、プログラムが自動作成するファイルでも、GUIへ読み込む入力モデルでもありません。実際に変更した内容と日付を記録してください。

## 8. 処理時間の設定とCSV入力

| `service.dist` | `p1` | `p2` |
|---|---|---|
| `constant` | 正の固定時間 | 0 |
| `normal` | 元の正規分布の正の平均 | 0以上の標準偏差 |
| `uniform` | 0以上の下限 | 下限より大きい上限 |
| `lognormal` | 時間そのものの正の平均 | 時間そのものの標準偏差 |

`normal`の負の標本は0に置き換えます。そのため、最終的な時間の平均は、指定した元の正規分布の平均と一般には一致しません。`lognormal`の`p1`・`p2`には、対数を取る前の時間の平均・標準偏差を指定します。

CSVで入力する場合は、UTF-8の `proc_time.csv` と `edges.csv` を同じフォルダに置きます。例えば、架空の2工程を次のように記述できます。

`proc_time.csv`:

```csv
process,name,dist_type,p1,p2,capacity
A,Cut,constant,2,0,1
B,Assemble,lognormal,5,1,1
```

`edges.csv`:

```csv
from,to
A,B
```

同梱のCSV例を読み込むコマンドは次のとおりです。

```bash
python mock_line_editor.py run \
  --csv-dir examples/fork \
  --jobs 60 --runs 50 --interval 1 --seed 42 \
  --out results/from_csv_01
```

CSVには工程と接続を保存します。画面配置・実験条件もまとめて残す場合はJSONを使ってください。

## 9. 出力ファイルと結果の読み方

各実行の出力フォルダには、次のファイルが作成されます。

| ファイル／フォルダ | 内容 |
|---|---|
| `model.json` | 実行した工程と実験条件。再実行に使用可能 |
| `summary.json` | 指標の平均、標準偏差、個別の95%信頼区間、最大の工程ID |
| `runs.csv` | 各試行の全体完了時間、処理量、平均滞在時間 |
| `node_metrics.csv` | 試行×工程ごとの設備待ち、合流待ち、稼働率など |
| `trace.csv` | 製品×工程ごとの開始・終了時刻、処理時間、待ち時間 |
| `interventions.csv` | 各工程を短縮したときの全体完了時間と改善量 |
| `ranking.csv` | 改善量順の工程一覧。改善比較を省略した場合は設備待ち順 |
| `input_csv/` | 実行モデルをCSVにしたもの |
| `reproducibility.json` | Python・ライブラリの版、条件、実行コードのSHA256など |
| `figures/` | 工程図、待ち時間、改善効果、完了時間、時間標本、時系列の図 |

図はPNG・PDFの両形式で出力します。`--no-figures`指定時は図を出力しません。

| 指標 | 意味 |
|---|---|
| `makespan` | 最初の投入から全製品の完成までの時間 |
| `throughput` | 製品数÷全体完了時間。単位は製品／時間単位 |
| `mean_flow` | 各製品の投入から完成までの時間の平均 |
| `queue_mean` | 前工程はそろったが、その工程の設備が空かずに待った時間の平均 |
| `sync_mean` | 合流する前工程のうち、最初の完了から最後の完了までの時間差の平均 |
| `utilization` | 全体完了時間に対する、その工程の設備の稼働割合 |
| `delta` | その工程を短縮したとき、全体完了時間がどれだけ減るか |

合流待ちは、すべての部品の待ち時間を足した値ではありません。また、処理量や稼働率は、空の状態から有限個の製品を流した実験の値です。

通常の `trace.csv` は基準条件の試行0だけを保存します。全基準試行の時刻が必要なら `--all-traces` を指定してください。改善後の詳細時刻表は出力しません。

`figures/service_samples.*` は**シミュレーションの最初の試行で生成した時間標本**の図です。元の15生産の観測値の図ではありません。実測の再解析には `smart_factory_observations.json` を使ってください。

試行1回では、標準偏差や信頼区間は `null` になります。複数回の95%区間も、モデルと仮定した乱数の下での計算結果の区間です。実測15件から推定したパラメータ自体の不確かさを、すべて取り込んだ区間ではありません。

**設備待ちが最も長い工程と、短縮すると全体が最も速くなる工程は一致しない場合があります。** 同率の最大値は `summary.json` の `queue_top`・`improvement_top` で確認してください。

## 10. 研究用データを再生成・検証する

### 原ファイルからJSONを再生成

```bash
python research_data_pack/convert_sources.py --out rebuilt_data
```

原ファイルの指紋を確認し、配布時と同じ抽出条件で8個のJSONを作ります。内訳は入力モデル5個、観測値・出典・一覧の資料3個です。原ファイルは書き換えません。出力先が空でない場合は、別のフォルダを指定してください。

生成したJSONをGUIで変更しても、変換スクリプトの処理は変わりません。対象日や採用作業など、**原データからの抽出規則**を変える場合は、`convert_sources.py`の条件も別途見直す必要があります。

### 配布データと本体の整合性を確認

```bash
python research_data_pack/verify_data.py \
  --program mock_line_editor.py \
  --out verification/data_check_01.json
```

この検証は `research_data_pack/json/` の配布データを対象にします。5モデルの実行、標準問題の1製品の理論値、実測15生産の作業時間合計との一致を確認します。任意の編集済みモデルについては、まず本体の `validate --model` を使ってください。

作成時には、5入力モデルが読み込み・実行できることと、15生産の時間合計が再現されることを確認しました。変換スクリプトから配布JSONと同じ内容を再生成できることも確認済みです。

## 11. 内蔵の検証実験とテスト

`benchmark`は、本体に組み込まれた**5つの仮想的な遅延シナリオ**を実行します。JACKSONなどを使う場合は、6節の `run --model` で入力ファイルを指定してください。

```bash
python mock_line_editor.py benchmark \
  --jobs 60 --runs 50 --interval 1 --seed 42 \
  --out results/builtin_benchmark_01
```

構造2種類×投入間隔2種類×変動係数3種類の、12条件の仮想実験は次のとおりです。

```bash
python variance_sweep.py \
  --jobs 60 --runs 50 --seed 42 \
  --out results/variance_01
```

今回再実行した結果は `results/benchmark/` と `results/variance/` に収録済みです。そこを再実行の出力先にすると、既存ファイルがあるため停止します。新しい結果は別フォルダへ保存してください。

本体の開発用テストを実行する場合は、GUI関連も含む開発用依存ライブラリを導入します。

```bash
python -m pip install -r requirements-dev.txt
QT_QPA_PLATFORM=offscreen python -m pytest -q tests
```

今回のパッケージでも27件のテストが通過しています。GUIの部品生成・工程の選択・削除は、画面を表示しないoffscreen環境で確認しています。計算は別途CLIと自動テストで検証しており、すべてのLinuxデスクトップ環境を検証したものではありません。

入力例を新しいフォルダへ作り直す場合は、次のコマンドを使います。配布済みの `examples/` を出力先に指定すると、上書きを防ぐため停止します。

```bash
python mock_line_editor.py examples --out my_examples
```

Linuxでは配布ファイルの欠損・変更を次で確認できます。利用者が編集・再コンパイルしたファイルは指紋が変わるため、配布時の値と一致しなくなるのが正常です。

```bash
sha256sum -c SHA256SUMS
```

## 12. モデルの前提と、研究結果の限界

### シミュレーター全体の前提

- 1製品がすべての工程を1回ずつ実行します。
- 分岐ではすべての枝を実行し、合流では同じ製品の全前工程が終わるのを待ちます。
- 工程間に循環のないDAGを扱います。経路を確率で選ぶ処理や再加工ループは扱いません。
- 各工程に専用設備を与え、先着順で処理します。
- 待ち場所は無制限、工程間の移動時間は0です。
- 異なる工程での設備・作業員の共用、故障、段取り替え、有限在庫は扱いません。
- 時間分布からの標本は工程間・製品間で独立に生成します。

### 公開ベンチマークについて

JACKSON・MITCHELL・HESKIAは、作業時間と先行関係を持つ標準問題です。元のSALBPは作業を作業台へ割り当てる問題であり、今回の「各作業に独立した設備1台」という設定は追加仮定です。作業台割当の最適解や、実工場の測定値として扱わないでください。

原データに反復測定値や標準偏差はないため、配布JSONでは定数を使っています。ばらつきを追加した場合は、研究者が設定した条件として記録してください。

### 実験工場ログについて

採用したのは、同一日の15生産です。記録された時間は制御ソフトから見た作業の経過時間であり、純粋な加工時間とは限りません。

同じロボットなどを複数工程が使用する制約を、本体は表現できません。そのため、実測由来の2モデルは既定の製品数を1としています。製品数を増やした計算だけで、実設備の生産能力や混雑を再現したとは言えません。

対数正規版は、平均と標準偏差を合わせた近似です。分布形の適合性、工程間の相関、別の日への一般化は未検証です。特にP02には非常に短い記録と約1.7秒の記録の二つの群があります。

1製品が一本道を進む場合、長い工程を同じ割合で短縮すると、合計時間も大きく減ります。この条件で改善順位が得られても、設備待ちのボトルネックを検出した証明にはなりません。

現時点で確認できているのは、公開データの読み込み・変換・モデル内での計算の整合性です。**実工場のボトルネック検出精度、既存手法に対する優位性、学術的新規性は確認していません。**

## 13. 詳しい解説文書とPDFの再作成

| 文書 | 内容 |
|---|---|
| [easy-guide.pdf](docs/easy-guide.pdf) | 実装、計算の仕組み、設定、結果の読み方、制約 |
| [easy-guide.tex](docs/easy-guide.tex) | 上記のLuaLaTeX原稿 |
| [data_sources_guide.pdf](research_data_pack/data_sources_guide.pdf) | 原典、抽出・変換、実測統計量、研究上の使い方 |
| [data_sources_guide.tex](research_data_pack/data_sources_guide.tex) | 上記のLuaLaTeX原稿 |

図と表は原稿に埋め込まれています。同じフォルダにある `myfont-setting.sty` も組版に必要です。原稿の表題・著者名・作成日の指定は添付最新版を引き継いでいます。

LuaLaTeX、LuaTeX-ja、原ノ味（HaranoAji）フォント、Latin Modern、TikZ／PGFPlots、`tcolorbox`、`listings`などを含むTeX環境を用意してください。Pythonの依存ライブラリとは別の導入が必要です。

フォント設定は添付版のFutura ND Book、Helvetica Neue、Inconsolata、ヒラギノを優先します。見つからないフォントはLatin Modern・原ノ味へ切り替えます。`easy-guide.tex` の和文は原稿側の指定により原ノ味を使います。フォントの違いで改行・ページ数が変わることがあります。

同梱の標準ライブラリだけで動くスクリプトから、2文書をまとめて作れます。

```bash
python build_docs.py --out build/docs
```

`build/docs/easy-guide.pdf` と `build/docs/data_sources_guide.pdf`、それぞれの組版ログができます。入力原稿・配布PDFは書き換えません。目次と参照番号のため各原稿を2回処理し、出力先には新規または空のフォルダが必要です。エラー時は `*.failed.log` を確認してください。

LuaLaTeXを直接使う場合は、各原稿のフォルダへ移動します。この方法では、そのフォルダのPDFを更新します。

```bash
cd docs
lualatex -interaction=nonstopmode -halt-on-error easy-guide.tex
lualatex -interaction=nonstopmode -halt-on-error easy-guide.tex
cd ../research_data_pack
lualatex -interaction=nonstopmode -halt-on-error data_sources_guide.tex
lualatex -interaction=nonstopmode -halt-on-error data_sources_guide.tex
cd ..
```

原稿の数値は埋め込みです。別条件で実験しても自動更新されないため、文書を改訂する際は表・図・説明を合わせて直してください。

## 14. よくある問題

| 症状 | 確認すること |
|---|---|
| `can't open file`／ファイルが見つからない | 作業フォルダと展開先を確認。READMEのコマンドは `mock_line_editor.py` がある `factory-line-lab/` を基準にしています |
| `ModuleNotFoundError` | `.venv`を有効にし、同じ`python`で`python -m pip install ...`を実行 |
| GUIが起動しない | GUI用の`requirements.txt`を導入し、デスクトップ上の端末から起動。画面のない環境ではCLIを使用 |
| JSONの読込エラー | 入力用の5モデルか確認。`observations`・`provenance`・`catalog`は資料用です |
| 「循環」「孤立工程」「ラインが分離」と出る | 工程の接続を修正。GUIで保存できる下書きでも、そのまま計算できるとは限りません |
| 「出力先は空のフォルダ」と出る | 実行ごとに新しい保存先名を指定。GUIでは空のフォルダを作ってから選択 |
| 計算が長い | 製品数・試行回数を減らして確認。必要に応じて改善比較や図を省略 |
| 試行を増やしても結果が同じ | 時間分布がすべて定数なら正常です |
| 工程を変更したら結果が消えた | 古い条件の結果を使わないための動作です。再実行してください |
| 再保存したJSONから出典情報が消えた | 現在の保存仕様です。配布原本と`provenance.json`を保持してください |
| LuaLaTeXでフォントや `.sty` が見つからない | TeX側の依存を確認。13節の `build_docs.py` または原稿フォルダからの組版を使用 |
| 文書の日付と取得記録の日付が異なる | 添付文書の表紙は2026-09-21、`sources/acquisition.json` の取得記録は2026-09-23です。双方を維持しており、取得経緯の確認には記録JSONを参照 |

## 15. 原典と利用条件

プログラムには添付最新版の [MITライセンス](LICENSE)（Copyright (c) 2026 Hiroki Funashima）を引き継いでいます。公開データには、それぞれの原典の利用条件が適用されます。取得し直したデータではなく、添付された原ファイルから再現性を確認したパッケージです。

### 組立ラインの標準問題

Armin Scholl (1993), *Data of Assembly Line Balancing Problems*, Schriften zur Quantitativen Betriebswirtschaftslehre 16/93, TH Darmstadt。書誌情報は配布ZIP内のREADMEによります。

- [データ配布ページ](https://assembly-line-balancing.de/salbp/benchmark-data-sets-1993/)
- [元のSALBPの説明](https://assembly-line-balancing.de/salbp/)
- [配布元の利用条件](https://assembly-line-balancing.de/home/legal-notice/)

使用した原ファイルは `JACKSON.IN2`、`MITCHELL.IN2`、`HESKIA.IN2` です。配布元は独自の利用条件を掲示しており、CC BYとして扱いません。一般公開や再配布の際は掲載条件を確認してください。

### St.Gallen実験工場

Ronny Seiger (2024), *Dataset from a Smart Factory to evaluate a Semi-automated Approach to Detecting Process-Level Activities from Sensor Data*, Zenodo。

- [データ原典：DOI 10.5281/zenodo.14441997](https://doi.org/10.5281/zenodo.14441997)
- [関連論文：DOI 10.1016/j.procs.2025.03.110](https://doi.org/10.1016/j.procs.2025.03.110)

取得メタデータに記されたライセンスはCC BY 4.0です。著者・DOIと、抽出・集計・近似などを加えたことを明記してください。本パッケージでは工程ログとBPMNを使用し、大型のセンサーログ2件は取得していません。

詳しい出典表示と変更内容は [SOURCE_NOTICES.md](research_data_pack/SOURCE_NOTICES.md)、取得記録は [acquisition.json](research_data_pack/sources/acquisition.json) を参照してください。プログラム・文書・すべての原データに一括で同じ利用条件が適用されるわけではありません。
