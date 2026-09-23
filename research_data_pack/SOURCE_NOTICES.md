# 出典と利用条件

取得日：2026-09-23。これは配布元の表示の記録です。

## St.Gallen実験工場データ

Ronny Seiger (2024), *Dataset from a Smart Factory to evaluate a Semi-automated Approach to Detecting Process-Level Activities from Sensor Data*, Zenodo, DOI: https://doi.org/10.5281/zenodo.14441997

公開レコードのAPIメタデータは `license.id = cc-by-4.0`。ライセンス：https://creativecommons.org/licenses/by/4.0/

関連論文：Luciano García-Bañuelos, Mauricio Jacobo González González, Ronny Seiger, Marco Franceschetti, Alejandra Guadalupe Silva Trujillo (2025), *A semi-automated approach to detecting process-level activities from sensor data*, Procedia Computer Science 257, 856–863. https://doi.org/10.1016/j.procs.2025.03.110

このパッケージでの変更：特定の生産日・工程版・完了状態を選び、自動作業だけを抽出。msから秒に換算し、標本平均と標本標準偏差を集計。作業ID・日本語表示名・仮定した設備台数・シミュレーション条件を付加。元ファイルは `sources/zenodo_14441997/` に変更せず収録。原著者による本変換やモデルの承認を意味しません。

## Schollのベンチマーク

Armin Scholl (1993), *Data of Assembly Line Balancing Problems*, Schriften zur Quantitativen Betriebswirtschaftslehre 16/93, TH Darmstadt. 書誌情報は配布ZIP内の `precedence graphs/README.DOC` によります。

配布ページ：https://assembly-line-balancing.de/salbp/benchmark-data-sets-1993/

取得ZIP：https://assembly-line-balancing.de/wp-content/uploads/2017/01/SALBP-data-sets.zip

利用条件の掲載先：https://assembly-line-balancing.de/home/legal-notice/

同サイトは著作権留保を掲示し、個人の非商用利用のためのダウンロードや、出典を示した個人へのコピーについて条件を示しています。一般への再配布や商用利用を自由に認めるライセンスとは記されていません。本データを公開リポジトリや配布サイトへ再掲載する際は、掲載先の条件を確認してください。本パッケージ全体を一括してCC BYなどの自由なライセンスとして扱わないでください。

使用した原ファイル：JACKSON.IN2、MITCHELL.IN2、HESKIA.IN2。工程時間と先行関係を変更せずJSONに変換し、仮定した専用設備1台・表示座標・実験条件を追加しました。
