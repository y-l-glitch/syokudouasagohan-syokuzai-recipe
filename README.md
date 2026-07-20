# 食堂あさごはん レシピ検索

YouTubeチャンネル「食堂あさごはん」の全動画の字幕・説明欄を収集し、
食材名で横断検索できる静的ページ (index.html) を生成するツール。

## ファイル構成

| ファイル | 役割 |
|---|---|
| collect.py | 収集スクリプト (yt-dlp 使用) |
| template.html | 検索ページの雛形 |
| index.json | 収集データ (再実行時のスキップ判定にも使用) |
| index.html | 生成される検索ページ。**これ1つだけで動く** |

## 使い方

```
python collect.py            # 新着動画だけ追加取得して index.html を更新
python collect.py --limit 5  # お試し (5本だけ)
python collect.py --retry-nosubs   # 字幕なし扱いだった動画を再チェック
python collect.py --rebuild-only   # 取得せず index.html だけ再生成
```

- 途中で Ctrl+C で止めても、取得済み分は index.json に保存されているので
  再実行すれば続きから取得される。
- リクエスト間に 2〜4秒のスリープを入れている (`--sleep-min/--sleep-max` で変更可)。
- 429 (レート制限) が続いた場合は自動で中断されるので、時間を置いて再実行する。

## 字幕の取得ロジック

1. 日本語の手動字幕 / 自動生成字幕 (ja, ja-orig) を優先
2. 多言語吹き替え動画で ja 系トラックが無い場合は、android クライアント経由で
   「英語字幕の日本語機械翻訳 (ja-en)」を取得 (ページ上に「字幕は自動翻訳」と表示)
3. それでも無ければ「字幕なし」として、タイトル・説明欄のみ索引に載せる

## GitHub Pages に置く場合

index.html を1ファイルアップロードするだけでよい
(データはHTML内に埋め込み済み。外部APIには依存しない。
サムネイル画像のみ YouTube の画像サーバー i.ytimg.com から読み込む)。

## 必要環境

- Python 3.x / `pip install yt-dlp curl_cffi`
  (curl_cffi は翻訳字幕取得の429回避に必要)
