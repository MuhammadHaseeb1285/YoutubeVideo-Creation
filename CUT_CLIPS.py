#!/usr/bin/env python3
"""
CUT_CLIPS - Process 2 of the pipeline.
Splits every video in youtube_videos/ and pexels_videos/ into
exactly 4-second clips inside clips_4s/.

Already-cut clips are skipped, so re-running is fast and safe.
"""

import subprocess
from pathlib import Path

CLIP_LEN = 4
SOURCES = [Path("youtube_videos"), Path("pexels_videos")]
CLIPS_DIR = Path("clips_4s")


def duration_of(path: Path) -> float:
    cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration",
           "-of", "default=noprint_wrappers=1:nokey=1", str(path)]
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
    return float(out.stdout.strip())


def main():
    print("\n" + "=" * 70)
    print("CUT ALL VIDEOS INTO 4-SECOND CLIPS")
    print("=" * 70)

    CLIPS_DIR.mkdir(exist_ok=True)

    videos = []
    for src in SOURCES:
        if src.exists():
            videos.extend(sorted(src.glob("*.mp4")))

    if not videos:
        print("[!] No videos found. Run DOWNLOAD_VIDEOS.py first.")
        return False

    print(f"[*] {len(videos)} source videos found\n")

    total_created = 0
    total_skipped = 0

    for video in videos:
        try:
            dur = duration_of(video)
        except Exception:
            print(f"  [!] {video.name}: cannot read duration, skipped")
            continue

        n = max(1, int(dur / CLIP_LEN))
        created = skipped = 0

        for i in range(n):
            clip = CLIPS_DIR / f"{video.stem}_clip_{i:03d}.mp4"
            if clip.exists():
                skipped += 1
                continue
            cmd = ["ffmpeg", "-ss", str(i * CLIP_LEN), "-i", str(video),
                   "-t", str(CLIP_LEN),
                   "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
                   "-an", "-y", str(clip)]
            subprocess.run(cmd, capture_output=True, timeout=60)
            if clip.exists():
                created += 1

        total_created += created
        total_skipped += skipped
        state = f"{created} new" + (f", {skipped} existing" if skipped else "")
        print(f"  [OK] {video.name}: {state}")

    total = len(list(CLIPS_DIR.glob("*.mp4")))
    print("\n" + "=" * 70)
    print(f"[OK] clips_4s/ now holds {total} clips "
          f"({total_created} new, {total_skipped} already existed)")
    print("[->] NEXT: run GENERATE_FINAL_VIDEO.py  (menu option 3)")
    print("=" * 70)
    return True


if __name__ == "__main__":
    raise SystemExit(0 if main() else 1)
