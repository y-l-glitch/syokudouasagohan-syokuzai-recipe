# -*- coding: utf-8 -*-
"""食堂あさごはん — 字幕収集スクリプト

チャンネルの全動画の一覧・説明欄・日本語自動生成字幕(json3)を取得して
index.json にまとめ、検索ページ index.html を生成する。

使い方:
    python collect.py --limit 5      # まず5本だけ試す
    python collect.py                # 全動画(取得済みはスキップ)
    python collect.py --retry-nosubs # 字幕なし扱いだった動画を再チェック
    python collect.py --rebuild-only # 取得せず index.html だけ再生成
"""
import argparse
import json
import os
import random
import sys
import tempfile
import time

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

CHANNEL_ID = "UCvFqPP4f-inG-cE0zDD9WpA"
TABS = ["videos", "shorts", "streams"]

BASE = os.path.dirname(os.path.abspath(__file__))
INDEX_PATH = os.path.join(BASE, "index.json")
TEMPLATE_PATH = os.path.join(BASE, "template.html")
HTML_PATH = os.path.join(BASE, "index.html")

# 字幕イベントを連結して1チャンクにまとめる際の目安文字数
CHUNK_LEN = 42


def load_index():
    if os.path.exists(INDEX_PATH):
        with open(INDEX_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {"channel_id": CHANNEL_ID, "videos": []}


def save_atomic(path, text):
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def save_index(index):
    save_atomic(INDEX_PATH, json.dumps(index, ensure_ascii=False, indent=1))


def fmt_date(d):
    if d and len(d) == 8:
        return f"{d[:4]}-{d[4:6]}-{d[6:]}"
    return ""


def list_channel_videos():
    """全タブ(videos/shorts/streams)の動画ID・タイトルをフラット取得する。"""
    seen, out = set(), []
    for tab in TABS:
        url = f"https://www.youtube.com/channel/{CHANNEL_ID}/{tab}"
        opts = {"quiet": True, "no_warnings": True, "extract_flat": "in_playlist"}
        try:
            with YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
        except DownloadError:
            print(f"  [{tab}] タブなし(スキップ)")
            continue
        entries = info.get("entries") or []
        n = 0
        for e in entries:
            vid = e.get("id")
            if vid and vid not in seen:
                seen.add(vid)
                out.append({"id": vid, "title": e.get("title") or ""})
                n += 1
        print(f"  [{tab}] {n}本")
    return out


def parse_json3(path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    events = []
    for ev in data.get("events", []):
        segs = ev.get("segs")
        if not segs:
            continue
        text = "".join(s.get("utf8", "") for s in segs).replace("\n", "").strip()
        if not text:
            continue
        events.append((ev.get("tStartMs", 0) / 1000.0, text))
    # 細かいイベントを CHUNK_LEN 文字目安のチャンクへ連結(データ量削減)
    chunks = []
    cur_start, cur_text = None, ""
    for start, text in events:
        if cur_start is None:
            cur_start, cur_text = start, text
        elif len(cur_text) + len(text) <= CHUNK_LEN:
            cur_text += text
        else:
            chunks.append({"start": round(cur_start, 1), "text": cur_text})
            cur_start, cur_text = start, text
    if cur_start is not None:
        chunks.append({"start": round(cur_start, 1), "text": cur_text})
    return chunks


# 取得を試す字幕トラックの優先順。ja / ja-orig は日本語の自動生成(または手動)字幕、
# ja-en は「英語字幕の日本語機械翻訳」。ja-en は多言語吹き替え動画向けの
# フォールバック時のみ要求する(通常クライアントで要求すると429になりやすいため)
SUB_LANGS = ["ja", "ja-orig"]
FALLBACK_LANGS = ["ja", "ja-orig", "ja-en"]


def _try_download_subs(url, tmpdir, video_id, langs, player_client=None):
    opts = {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "skip_download": True,
        "writesubtitles": True,
        "writeautomaticsub": True,
        "subtitleslangs": langs,
        "subtitlesformat": "json3",
        "outtmpl": {"default": os.path.join(tmpdir, "%(id)s.%(ext)s")},
    }
    if player_client:
        opts["extractor_args"] = {"youtube": {"player_client": [player_client]}}
    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
    for lang in langs:
        p = os.path.join(tmpdir, f"{video_id}.{lang}.json3")
        if os.path.exists(p):
            return info, lang, p
    return info, None, None


def fetch_video(video_id, tmpdir):
    url = f"https://www.youtube.com/watch?v={video_id}"
    info, lang, path = _try_download_subs(url, tmpdir, video_id, SUB_LANGS)
    caption_429 = False
    if path is None:
        # 多言語吹き替え動画では既定クライアントに ja 系トラックが出ないことが
        # あるため、android クライアントで再試行する。翻訳字幕(ja-en)の
        # エンドポイントは429になりやすいので、その場合は字幕なしとして
        # メタデータだけ索引に入れる(--retry-nosubs で後日取り直せる)
        try:
            info2, lang, path = _try_download_subs(url, tmpdir, video_id,
                                                   FALLBACK_LANGS,
                                                   player_client="android")
            info = info2 or info
        except DownloadError as err:
            if "429" not in str(err) and "Too Many Requests" not in str(err):
                raise
            caption_429 = True
    rec = {
        "video_id": video_id,
        "title": info.get("title") or "",
        "upload_date": fmt_date(info.get("upload_date")),
        "duration": info.get("duration") or 0,
        "description": info.get("description") or "",
        "segments": [],
    }
    if path:
        rec["segments"] = parse_json3(path)
        rec["caption_lang"] = lang
        os.remove(path)
    if not rec["segments"]:
        rec["no_captions"] = True
        rec.pop("caption_lang", None)
        if caption_429:
            rec["caption_429"] = True
    return rec


def fetch_meta(video_id):
    """字幕エンドポイントに触れず、タイトル・説明欄などのメタデータだけ取得する。
    レート制限中でも比較的通りやすく、新規動画を即座に検索対象へ加えられる。
    字幕は未取得なので caption_429 として後日リトライ対象に残す。"""
    url = f"https://www.youtube.com/watch?v={video_id}"
    opts = {"quiet": True, "no_warnings": True, "noprogress": True,
            "skip_download": True}
    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    return {
        "video_id": video_id,
        "title": info.get("title") or "",
        "upload_date": fmt_date(info.get("upload_date")),
        "duration": info.get("duration") or 0,
        "description": info.get("description") or "",
        "segments": [],
        "no_captions": True,
        "caption_429": True,
    }


def build_html(index):
    with open(TEMPLATE_PATH, encoding="utf-8") as f:
        tpl = f.read()
    videos = sorted(
        index["videos"],
        key=lambda v: (v.get("upload_date") or "", v["video_id"]),
        reverse=True,
    )
    payload = {"updated": time.strftime("%Y-%m-%d"), "videos": videos}
    blob = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    blob = blob.replace("</", "<\\/")  # </script> によるタグ閉じを防ぐ
    save_atomic(HTML_PATH, tpl.replace("__DATA_JSON__", blob))
    size_mb = os.path.getsize(HTML_PATH) / 1024 / 1024
    print(f"index.html を更新しました ({len(videos)}本, {size_mb:.1f}MB)")


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace",
                               line_buffering=True)

    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, help="今回取得する最大本数(お試し用)")
    ap.add_argument("--sleep-min", type=float, default=2.0)
    ap.add_argument("--sleep-max", type=float, default=4.0)
    ap.add_argument("--retry-nosubs", action="store_true",
                    help="字幕なし扱いの動画を再チェックする")
    ap.add_argument("--rebuild-only", action="store_true",
                    help="取得を行わず index.html だけ再生成する")
    ap.add_argument("--meta-only", action="store_true",
                    help="字幕エンドポイントに触れず、新規動画のタイトル・説明欄だけ"
                         "索引化する(レート制限中でも検索対象に加えられる。字幕は"
                         "caption_429として後日リトライされる)")
    args = ap.parse_args()

    index = load_index()

    if args.rebuild_only:
        build_html(index)
        return

    print("チャンネルの動画一覧を取得中…")
    listing = list_channel_videos()
    print(f"合計 {len(listing)}本")

    known = {v["video_id"]: v for v in index["videos"]}
    targets = []
    for e in listing:
        v = known.get(e["id"])
        if v is None:
            targets.append(e)                    # 未取得の新規動画
        elif args.meta_only:
            continue                             # meta-only は新規動画のみ対象
        elif v.get("caption_429"):
            targets.append(e)                    # レート制限で保留中 → 毎回リトライして自己修復
        elif args.retry_nosubs and v.get("no_captions"):
            targets.append(e)                    # 字幕なし全件の再チェック(--retry-nosubs 指定時のみ)
    # 未取得の新規動画を先頭に。限られた取得枠を、まだ検索対象に入っていない
    # 動画に優先して使う(429保留の再取得より新規のメタデータ確保を優先)
    targets.sort(key=lambda e: 0 if known.get(e["id"]) is None else 1)
    if args.limit:
        targets = targets[: args.limit]
    print(f"今回取得: {len(targets)}本 (取得済み {len(listing) - len(targets)}本はスキップ)\n")

    errors = []
    consecutive_429 = 0
    tmpdir = tempfile.mkdtemp(prefix="subs_")
    try:
        for i, e in enumerate(targets, 1):
            vid = e["id"]
            try:
                rec = fetch_meta(vid) if args.meta_only else fetch_video(vid, tmpdir)
                consecutive_429 = 0
            except DownloadError as err:
                msg = str(err)
                if "429" in msg or "Too Many Requests" in msg:
                    consecutive_429 += 1
                    if consecutive_429 >= 3:
                        print("\n429(レート制限)が続いています。時間を置いて再実行してください。")
                        break
                    print(f"  429を検出。60秒待機してリトライします…")
                    time.sleep(60)
                    try:
                        rec = fetch_meta(vid) if args.meta_only else fetch_video(vid, tmpdir)
                        consecutive_429 = 0
                    except DownloadError as err2:
                        errors.append((vid, e["title"], str(err2).splitlines()[0]))
                        continue
                else:
                    errors.append((vid, e["title"], msg.splitlines()[0]))
                    continue

            # 既存レコードの置き換え or 追加
            if rec["video_id"] in known:
                index["videos"] = [
                    rec if v["video_id"] == rec["video_id"] else v
                    for v in index["videos"]
                ]
            else:
                index["videos"].append(rec)
            known[rec["video_id"]] = rec
            save_index(index)

            if args.meta_only:
                mark = "メタのみ(字幕は後日)"
            else:
                mark = "字幕なし" if rec.get("no_captions") else f"{len(rec['segments'])}区間"
            print(f"[{i}/{len(targets)}] {rec['title'][:40]}  ({mark})")

            if i < len(targets):
                time.sleep(random.uniform(args.sleep_min, args.sleep_max))
    except KeyboardInterrupt:
        print("\n中断しました。取得済み分は保存されています(再実行で続きから)。")
    finally:
        for f in os.listdir(tmpdir):
            os.remove(os.path.join(tmpdir, f))
        os.rmdir(tmpdir)

    no_subs = [v for v in index["videos"]
               if v.get("no_captions") and not v.get("caption_429")]
    pending = [v for v in index["videos"] if v.get("caption_429")]
    print(f"\n=== 結果 ===")
    print(f"索引済み: {len(index['videos'])}本 "
          f"(うち字幕なし {len(no_subs)}本、レート制限で字幕未取得 {len(pending)}本)")
    if no_subs:
        print("\n-- 字幕がなかった動画 --")
        for v in no_subs:
            print(f"  {v['video_id']}  {v['title']}")
        print("  ※ --retry-nosubs で再チェックできます")
    if pending:
        print("\n-- レート制限(429)で字幕を取得できなかった動画 --")
        for v in pending:
            print(f"  {v['video_id']}  {v['title']}")
        print("  ※ タイトル・説明欄のみ索引済み。時間を置いて --retry-nosubs で再取得してください")
    if errors:
        print("\n-- 取得エラー(次回実行時に再試行されます) --")
        for vid, title, msg in errors:
            print(f"  {vid}  {title}\n      {msg}")

    build_html(index)


if __name__ == "__main__":
    main()
