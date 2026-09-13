from googleapiclient.discovery import build
from datetime import datetime
import csv
import os

API_KEY = os.getenv("API_KEY")  # GitHub Actions用

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


def filter_yararara(videos):
    result = []
    for v in videos:
        title = v["title"].lower()
        if "ヤラララ" in title or "yararara" in title:
            result.append(v)
    return result


def fetch_view_count(video_ids):
    youtube = build("youtube", "v3", developerKey=API_KEY)

    stats = {}
    for i in range(0, len(video_ids), 50):
        chunk = video_ids[i:i+50]
        res = youtube.videos().list(
            id=",".join(chunk),
            part="statistics"
        ).execute()

        for item in res["items"]:
            stats[item["id"]] = int(item["statistics"]["viewCount"])

    return stats


def make_ranking(videos, view_stats):
    ranking = sorted(
        [
            {
                "title": v["title"],
                "videoId": v["videoId"],
                "views": view_stats.get(v["videoId"], 0)
            }
            for v in videos
        ],
        key=lambda x: x["views"],
        reverse=True
    )
    return ranking


def save_csv(ranking):
    collected_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    filename = "yararara_ranking.csv"

    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["collected_at", collected_at])
        writer.writerow(["rank", "title", "videoId", "views"])
        for i, r in enumerate(ranking, start=1):
            writer.writerow([i, r["title"], r["videoId"], r["views"]])

    # ★ CSV の絶対パスをログに出す
    print("📌 CSV生成場所:", os.path.abspath(filename))

    return filename


def main():
    print("📂 現在の作業ディレクトリ:", os.getcwd())

    print("🔍 ヤラララ動画を検索中…")
    videos = search_yararara_all()
    print(f"✔ 検索ヒット数（日本語）: {len(videos)} 件")

    print("🔎 日本語＋英語タイトルでフィルタ中…")
    videos = filter_yararara(videos)
    print(f"✔ フィルタ後: {len(videos)} 件")

    # 重複排除（videoIdでユニーク化）
    unique = {}
    for v in videos:
        unique[v["videoId"]] = v
    videos = list(unique.values())
    print(f"✔ 重複排除後: {len(videos)} 件")

    video_ids = [v["videoId"] for v in videos]

    print("📥 再生数を取得中…")
    view_stats = fetch_view_count(video_ids)

    print("🏆 ランキング生成中…")
    ranking = make_ranking(videos, view_stats)

    ranking = ranking[:1000]

    print("💾 CSV保存中…")
    filename = save_csv(ranking)

    print("\n=== ヤラララ / YARARARA 再生数ランキング（1000位まで） ===\n")
    for i, r in enumerate(ranking, start=1):
        print(f"{i:2d}位  {r['views']:>10}回  {r['title']}")

    print(f"\n📁 保存先: {filename}")
    print("🎉 完了！")


if __name__ == "__main__":
    main()
