from googleapiclient.discovery import build
from datetime import datetime, timedelta, timezone
import csv
import os
import re
import sys

# JST
JST = timezone(timedelta(hours=9))
API_KEY = os.getenv("API_KEY")

# 永続台帳と、毎日出力するランキング
MASTER_FILE = "yararara_video_master.csv"
RANKING_FILE = "yararara_ranking.csv"

# 既存のCSVがある場合、初回の台帳作成時に取り込む候補。
# 1015/1016のCSVもリポジトリに置けば、そこにあるIDを復元できます。
SEED_FILES = [
    "yararara_ranking.csv",
    "yararara_ranking_1015.csv",
    "yararara_ranking_1016.csv",
]

MASTER_FIELDS = [
    "videoId", "title", "views", "duration", "seconds", "isShort",
    "first_seen_at", "last_seen_search_at", "last_success_at",
    "last_attempt_at", "consecutive_failures", "data_status",
]
RANKING_FIELDS = [
    "rank", "title", "videoId", "views", "duration", "seconds",
    "isShort", "collected_at", "views_status", "last_success_at",
]


def now_jst():
    return datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S")


def parse_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def duration_to_seconds(duration):
    match = re.fullmatch(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", duration or "")
    if not match:
        return None
    hours = int(match.group(1) or 0)
    minutes = int(match.group(2) or 0)
    seconds = int(match.group(3) or 0)
    return hours * 3600 + minutes * 60 + seconds


def search_yararara_all(youtube):
    """日本語・ローマ字の両方で検索。APIエラー時は処理全体を失敗させる。"""
    videos = {}

    # 英語表記の動画も発見できるよう、検索語を分ける。
    # 同じ動画が複数の検索語に出てもvideoIdで重複排除する。
    for query in ("ヤラララ", "YARARARA"):
        next_page = None
        while True:
            kwargs = {
                "q": query,
                "part": "snippet",
                "type": "video",
                "maxResults": 50,
            }
            if next_page:
                kwargs["pageToken"] = next_page

            response = youtube.search().list(**kwargs).execute()

            for item in response.get("items", []):
                video_id = item.get("id", {}).get("videoId")
                snippet = item.get("snippet", {})
                title = snippet.get("title", "")
                if not video_id:
                    continue
                lowered = title.lower()
                if "ヤラララ" in title or "yararara" in lowered:
                    videos[video_id] = {
                        "videoId": video_id,
                        "title": title,
                    }

            next_page = response.get("nextPageToken")
            if not next_page:
                break

    return videos


def read_csv_rows(path):
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", newline="", encoding="utf-8-sig") as f:
            return list(csv.DictReader(f))
    except (OSError, csv.Error) as exc:
        print(f"⚠ CSVを読み込めませんでした: {path}: {exc}")
        return []


def load_master():
    """既存台帳を読み込み、初回のみ既存ランキングCSVから種データを作る。"""
    master = {}
    current_time = now_jst()

    if os.path.exists(MASTER_FILE):
        rows = read_csv_rows(MASTER_FILE)
        for row in rows:
            video_id = (row.get("videoId") or "").strip()
            if not video_id:
                continue
            master[video_id] = {
                "videoId": video_id,
                "title": row.get("title", ""),
                "views": row.get("views", ""),
                "duration": row.get("duration", ""),
                "seconds": row.get("seconds", ""),
                "isShort": row.get("isShort", ""),
                "first_seen_at": row.get("first_seen_at") or current_time,
                "last_seen_search_at": row.get("last_seen_search_at", ""),
                "last_success_at": row.get("last_success_at", ""),
                "last_attempt_at": row.get("last_attempt_at", ""),
                "consecutive_failures": str(parse_int(row.get("consecutive_failures"))),
                "data_status": row.get("data_status") or "seeded",
            }
        print(f"✔ 既存台帳を読み込み: {len(master)} 件")
        return master

    # 台帳がまだない初回だけ、旧ランキングCSVを取り込む。
    # 同じIDが複数ファイルにあれば、後のファイルの値で補完・更新する。
    seed_count = 0
    for path in SEED_FILES:
        for row in read_csv_rows(path):
            video_id = (row.get("videoId") or row.get("videoID") or "").strip()
            if not video_id:
                continue

            old = master.get(video_id, {})
            views = row.get("views", old.get("views", ""))
            duration = row.get("duration", old.get("duration", ""))
            seconds = row.get("seconds", old.get("seconds", ""))
            is_short = row.get("isShort", old.get("isShort", ""))

            master[video_id] = {
                "videoId": video_id,
                "title": row.get("title") or old.get("title", ""),
                "views": views,
                "duration": duration,
                "seconds": seconds,
                "isShort": is_short,
                "first_seen_at": old.get("first_seen_at") or current_time,
                "last_seen_search_at": old.get("last_seen_search_at", ""),
                "last_success_at": old.get("last_success_at") or row.get("collected_at", ""),
                "last_attempt_at": "",
                "consecutive_failures": "0",
                "data_status": "seeded_from_csv",
            }
            seed_count += 1

    print(f"✔ 初回台帳の種データ: {len(master)} 件（CSV行の取込数 {seed_count}）")
    return master


def fetch_video_details(youtube, video_ids):
    """
    videos.listで詳細を取得。
    戻り値には成功して返された動画だけが入る。
    取得失敗IDは呼び出し元で前回値を維持する。
    """
    details = {}
    for start in range(0, len(video_ids), 50):
        chunk = video_ids[start:start + 50]
        try:
            response = youtube.videos().list(
                id=",".join(chunk),
                part="snippet,statistics,contentDetails",
                maxResults=50,
            ).execute()
        except Exception as exc:
            print(f"⚠ 詳細取得に失敗したバッチ（{len(chunk)}件）: {exc}")
            continue

        for item in response.get("items", []):
            video_id = item.get("id")
            if not video_id:
                continue

            snippet = item.get("snippet", {})
            statistics = item.get("statistics", {})
            content = item.get("contentDetails", {})
            duration = content.get("duration", "")
            seconds = duration_to_seconds(duration) if duration else None
            views = statistics.get("viewCount")

            # 再生数または動画長が取れない場合は、今回の成功データとして採用しない。
            if views is None or seconds is None:
                print(f"⚠ 必須情報が不足: {video_id} (views={views}, duration={duration})")
                continue

            details[video_id] = {
                "title": snippet.get("title", ""),
                "views": int(views),
                "duration": duration,
                "seconds": seconds,
                "isShort": seconds <= 60,
            }

    return details


def update_master(master, searched_videos, details, timestamp):
    # 検索で見つかった動画を登録。すでにあるIDは消さない。
    for video_id, video in searched_videos.items():
        if video_id not in master:
            master[video_id] = {
                "videoId": video_id,
                "title": video["title"],
                "views": "",
                "duration": "",
                "seconds": "",
                "isShort": "",
                "first_seen_at": timestamp,
                "last_seen_search_at": timestamp,
                "last_success_at": "",
                "last_attempt_at": "",
                "consecutive_failures": "0",
                "data_status": "new_pending_details",
            }
        else:
            if video.get("title"):
                master[video_id]["title"] = video["title"]
            master[video_id]["last_seen_search_at"] = timestamp

    # 取得対象全IDについて、今回の試行日時を記録する。
    for video_id in master:
        master[video_id]["last_attempt_at"] = timestamp

    # 詳細取得成功したIDのみ値を更新。成功しないIDは前回値を維持する。
    for video_id, detail in details.items():
        row = master[video_id]
        if detail.get("title"):
            row["title"] = detail["title"]
        row["views"] = str(detail["views"])
        row["duration"] = detail["duration"]
        row["seconds"] = str(detail["seconds"])
        row["isShort"] = str(detail["isShort"])
        row["last_success_at"] = timestamp
        row["consecutive_failures"] = "0"
        row["data_status"] = "current"

    for video_id, row in master.items():
        if video_id not in details:
            row["consecutive_failures"] = str(parse_int(row.get("consecutive_failures")) + 1)
            row["data_status"] = "stale_last_known" if row.get("views") not in ("", None) else "no_details_yet"


def save_master(master):
    temp_file = MASTER_FILE + ".tmp"
    with open(temp_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=MASTER_FIELDS)
        writer.writeheader()
        for video_id in sorted(master):
            row = master[video_id]
            writer.writerow({field: row.get(field, "") for field in MASTER_FIELDS})
    os.replace(temp_file, MASTER_FILE)


def save_ranking(master, timestamp):
    # 最新値がある動画を再生数順に並べる。未取得動画も末尾に残す。
    rows = list(master.values())
    rows.sort(
        key=lambda row: (
            row.get("views", "") not in ("", None),
            parse_int(row.get("views"), -1),
            row.get("videoId", ""),
        ),
        reverse=True,
    )

    temp_file = RANKING_FILE + ".tmp"
    with open(temp_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=RANKING_FIELDS)
        writer.writeheader()
        for rank, row in enumerate(rows, start=1):
            writer.writerow({
                "rank": rank,
                "title": row.get("title", ""),
                "videoId": row.get("videoId", ""),
                "views": row.get("views", ""),
                "duration": row.get("duration", ""),
                "seconds": row.get("seconds", ""),
                "isShort": row.get("isShort", ""),
                "collected_at": timestamp,
                "views_status": row.get("data_status", ""),
                "last_success_at": row.get("last_success_at", ""),
            })
    os.replace(temp_file, RANKING_FILE)


def main():
    if not API_KEY:
        raise RuntimeError("環境変数 API_KEY が設定されていません。")

    timestamp = now_jst()
    print("🔍 YouTube APIに接続します…")
    youtube = build("youtube", "v3", developerKey=API_KEY)

    # 検索そのものが失敗した場合は、成功したような新規ランキングを作らず終了。
    print("🔎 新しい検索結果を取得中…")
    searched_videos = search_yararara_all(youtube)
    print(f"✔ 今回の検索で確認した動画: {len(searched_videos)} 件")

    master = load_master()
    before_count = len(master)

    # 検索結果に出なかった過去IDもすべて更新対象に含める。
    for video_id, video in searched_videos.items():
        if video_id not in master:
            master[video_id] = {
                "videoId": video_id,
                "title": video["title"],
                "views": "",
                "duration": "",
                "seconds": "",
                "isShort": "",
                "first_seen_at": timestamp,
                "last_seen_search_at": timestamp,
                "last_success_at": "",
                "last_attempt_at": "",
                "consecutive_failures": "0",
                "data_status": "new_pending_details",
            }
        else:
            master[video_id]["last_seen_search_at"] = timestamp
            if video.get("title"):
                master[video_id]["title"] = video["title"]

    all_ids = list(master.keys())
    print(f"📚 詳細情報の更新対象（過去IDを含む）: {len(all_ids)} 件")

    details = fetch_video_details(youtube, all_ids)
    update_master(master, searched_videos, details, timestamp)

    save_master(master)
    save_ranking(master, timestamp)

    current_count = sum(1 for row in master.values() if row.get("data_status") == "current")
    stale_count = sum(1 for row in master.values() if row.get("data_status") == "stale_last_known")
    no_data_count = sum(1 for row in master.values() if row.get("data_status") == "no_details_yet")

    print(f"📊 台帳件数: {before_count} → {len(master)}")
    print(f"✔ 今回の詳細取得成功: {len(details)} 件")
    print(f"⚠ 前回値を保持: {stale_count} 件")
    print(f"⚠ 詳細情報未取得: {no_data_count} 件")
    print(f"💾 保存: {MASTER_FILE}, {RANKING_FILE}")
    print("🎉 完了")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"❌ 処理失敗: {exc}", file=sys.stderr)
        raise
