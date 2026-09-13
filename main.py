from googleapiclient.discovery import build
from datetime import datetime, timedelta, timezone
import csv
import os
import re

# JST タイムゾーン
JST = timezone(timedelta(hours=9))
API_KEY = os.getenv("API_KEY")  # GitHub Actions用

# -------------------------
# 動画検索
# -------------------------
def search_yararara_all():
    youtube = build("youtube", "v3", developerKey=API_KEY)

    videos = []
    next_page = None

    while True:
        res = youtube.search().list(
            q="ヤラララ",
            part="snippet",
            type="video",
            maxResults=50,
            pageToken=next_page
        ).execute()

        for item in res["items"]:
            videos.append({
                "videoId": item["id"]["videoId"],
                "title": item["snippet"]["title"]
            })

        next_page = res.get("nextPageToken")
        if not next_page:
            break

    return videos

# -------------------------
# タイトルフィルタ
# -------------------------
def filter_yararara(videos):
    result = []
    for v in videos:
        title = v["title"].lower()
        if "ヤラララ" in title or "yararara" in title:
            result.append(v)
    return result

# -------------------------
# ISO8601 → 秒数変換（H/M/S 全対応）
# -------------------------
def duration_to_seconds(duration):
    match = re.match(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', duration)
    hours = int(match.group(1)) if match.group(1) else 0
    minutes = int(match.group(2)) if match.group(2) else 0
    seconds = int(match.group(3)) if match.group(3) else 0
    return hours * 3600 + minutes * 60 + seconds

# -------------------------
# 再生数＋duration 取得
# -------------------------
def fetch_video_details(video_ids):
    youtube = build("youtube", "v3", developerKey=API_KEY)

    details = {}
    for i in range(0, len(video_ids), 50):
        chunk = video_ids[i:i+50]
        res = youtube.videos().list(
            id=",".join(chunk),
            part="statistics,contentDetails"
        ).execute()

        for item in res["items"]:
            vid = item["id"]

            # duration 欠損動画をスキップ
            if "contentDetails" not in item or "duration" not in item["contentDetails"]:
                print(f"⚠ duration が無い動画をスキップ: {vid}")
                continue

            duration = item["contentDetails"]["duration"]
            view_count = int(item["statistics"]["viewCount"])
            sec = duration_to_seconds(duration)

            details[vid] = {
                "views": view_count,
                "duration": duration,
                "seconds": sec,
                "isShort": sec <= 60
            }

    return details

# -------------------------
# ランキング生成
# -------------------------
def make_ranking(videos, details):
    ranking = sorted(
        [
            {
                "title": v["title"],
                "videoId": v["videoId"],
                "views": details[v["videoId"]]["views"],
                "duration": details[v["videoId"]]["duration"],
                "seconds": details[v["videoId"]]["seconds"],
                "isShort": details[v["videoId"]]["isShort"]
            }
            for v in videos
        ],
        key=lambda x: x["views"],
        reverse=True
    )
    return ranking

# -------------------------
# CSV 保存（ヘッダー1行に統合）
# -------------------------
def save_csv(ranking):
    collected_at = datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S")
    filename = "yararara_ranking.csv"

    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)

        # GitHub が壊れた CSV と判定しないようヘッダーは1行に統合
        writer.writerow([
            "rank", "title", "videoId", "views",
            "duration", "seconds", "isShort", "collected_at"
        ])

        for i, r in enumerate(ranking, start=1):
            writer.writerow([
                i,
                r["title"],
                r["videoId"],
                r["views"],
                r["duration"],
                r["seconds"],
                r["isShort"],
                collected_at
            ])

    print("📌 CSV生成場所:", os.path.abspath(filename))
    return filename

# -------------------------
# メイン処理
# -------------------------
def main():
    print("📂 現在の作業ディレクトリ:", os.getcwd())

    print("🔍 ヤラララ動画を検索中…")
    videos = search_yararara_all()
    print(f"✔ 検索ヒット数（日本語）: {len(videos)} 件")

    print("🔎 日本語＋英語タイトルでフィルタ中…")
    videos = filter_yararara(videos)
    print(f"✔ フィルタ後: {len(videos)} 件")

    # 重複排除
    unique = {}
    for v in videos:
        unique[v["videoId"]] = v
    videos = list(unique.values())
    print(f"✔ 重複排除後: {len(videos)} 件")

    video_ids = [v["videoId"] for v in videos]

    print("📥 再生数＋duration を取得中…")
    details = fetch_video_details(video_ids)

    # ★ duration 欠損動画を videos から除外（KeyError 防止）
    videos = [v for v in videos if v["videoId"] in details]
    print(f"✔ duration 取得成功動画のみ: {len(videos)} 件")

    print("🏆 ランキング生成中…")
    ranking = make_ranking(videos, details)

    ranking = ranking[:1000]

    print("💾 CSV保存中…")
    filename = save_csv(ranking)

    print("\n=== ヤラララ / YARARARA 再生数ランキング（1000位まで） ===\n")
    for i, r in enumerate(ranking, start=1):
        print(f"{i:2d}位  {r['views']:>10}回  {r['title']}  (Short={r['isShort']})")

    print(f"\n📁 保存先: {filename}")
    print("🎉 完了！")

if __name__ == "__main__":
    main()
