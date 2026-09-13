def main():
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

    # 1000位までに制限
    ranking = ranking[:1000]

    print("💾 CSV保存中…")
    filename = save_csv(ranking)

    print("\n=== ヤラララ / YARARARA 再生数ランキング（1000位まで） ===\n")
    for i, r in enumerate(ranking, start=1):
        print(f"{i:2d}位  {r['views']:>10}回  {r['title']}")

    print(f"\n📁 保存先: {filename}")
    print("🎉 完了！")
