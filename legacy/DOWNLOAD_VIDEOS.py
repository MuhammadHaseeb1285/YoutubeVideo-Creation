#!/usr/bin/env python3
"""
DOWNLOAD_VIDEOS - Download YouTube + Pexels videos
Simple script with retry logic for slow internet
"""

import os
import subprocess
import requests
from pathlib import Path


PEXELS_API_KEY = os.environ.get(
    "PEXELS_API_KEY",
    "OqvEHNfwvEjuuvosrZXe5keUApJkPuapj79araQgOWtaxZ1xRY9DRsC8")


def download_youtube_videos():
    """Download 11 YouTube videos"""
    print("\n" + "="*70)
    print("DOWNLOADING YOUTUBE VIDEOS")
    print("="*70)

    youtube_dir = Path("youtube_videos")
    youtube_dir.mkdir(exist_ok=True)

    searches = [
        ("Ryan Reynolds age 38 2016 Deadpool training", "ryan_38"),
        ("Ryan Reynolds age 47 2024 physique", "ryan_47"),
        ("Ryan Reynolds Deadpool 2016 transformation", "deadpool_2016"),
        ("Ryan Reynolds Deadpool Wolverine 2024", "deadpool_2024"),
        ("Don Saladino Ryan Reynolds trainer", "saladino"),
        ("chest press dumbbell training exercise", "chest"),
        ("back row exercise training gym", "back"),
        ("leg squat training exercise", "legs"),
        ("nutrition eating healthy diet", "nutrition"),
        ("running sprint cardio training", "cardio"),
        ("sleep rest recovery stretching", "recovery"),
    ]

    downloaded = 0
    failed = 0

    for query, name in searches:
        output_file = youtube_dir / f"{name}.mp4"

        if output_file.exists():
            size_mb = output_file.stat().st_size / (1024 * 1024)
            print(f"[✓] {name} ({size_mb:.1f} MB)")
            downloaded += 1
            continue

        print(f"[*] {name}: Downloading...", end=" ")

        from CELEB_VIDEO import download_one
        if download_one(query, output_file):
            size_mb = output_file.stat().st_size / (1024 * 1024)
            print(f"OK ({size_mb:.1f} MB)")
            downloaded += 1
        else:
            print("[FAILED after all retries]")
            failed += 1

    print(f"\n[✓] Downloaded: {downloaded}/11")
    if failed > 0:
        print(f"[!] Failed: {failed}")

    return downloaded


def download_pexels_videos():
    """Download 50+ Pexels videos"""
    print("\n" + "="*70)
    print("DOWNLOADING PEXELS VIDEOS (50+)")
    print("="*70)

    pexels_dir = Path("pexels_videos")
    pexels_dir.mkdir(exist_ok=True)

    searches = [
        ("fitness training gym", 5),
        ("strength training weights", 5),
        ("running cardio sprint", 5),
        ("healthy eating nutrition meal", 5),
        ("recovery stretching yoga", 5),
        ("bodybuilding workout exercise", 5),
        ("dumbbell chest press training", 5),
        ("back row pullup exercise", 4),
        ("leg squat lunge exercise", 4),
        ("shoulder arm exercise training", 4),
    ]

    headers = {"Authorization": PEXELS_API_KEY}
    base_url = "https://api.pexels.com/v1/videos/search"
    downloaded = 0

    for query, count in searches:
        print(f"\n[*] Pexels: '{query}'")

        try:
            response = requests.get(
                base_url,
                headers=headers,
                params={"query": query, "per_page": count},
                timeout=60
            )
            data = response.json()

            video_list = data.get("videos", [])
            print(f"    Found: {len(video_list)} videos")

            for i, video in enumerate(video_list[:count]):
                try:
                    download_url = video["video_files"][0]["link"]
                    video_name = f"pexels_{query.replace(' ', '_')}_{i}.mp4"
                    video_path = pexels_dir / video_name

                    if video_path.exists():
                        print(f"    [✓] {video_name} (exists)")
                        downloaded += 1
                        continue

                    print(f"    [*] Downloading {video_name}...", end=" ")

                    video_response = requests.get(download_url, timeout=120)
                    with open(video_path, 'wb') as f:
                        f.write(video_response.content)

                    size_mb = video_path.stat().st_size / (1024 * 1024)
                    print(f"✓ ({size_mb:.1f} MB)")
                    downloaded += 1

                except Exception as e:
                    print(f"[Failed]")

        except Exception as e:
            print(f"    [!] Search error")

    print(f"\n[✓] Pexels videos: {downloaded}")
    return downloaded


if __name__ == "__main__":
    print("\n" + "="*70)
    print("DOWNLOAD ALL VIDEOS")
    print("="*70)

    yt_count = download_youtube_videos()
    px_count = download_pexels_videos()

    print("\n" + "="*70)
    print("SUMMARY")
    print("="*70)
    print(f"[✓] YouTube: {yt_count} videos")
    print(f"[✓] Pexels: {px_count} videos")
    print(f"[✓] Total: {yt_count + px_count} videos")
    print(f"\n[→] NEXT: Run QUICK_COMPILE.py")
    print("="*70)
