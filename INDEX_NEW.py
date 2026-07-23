#!/usr/bin/env python3
"""
INDEX_NEW - scene-detect videos not yet in shot_index.json, then build
labeled contact sheets for the NEW scenes only (vision_sheets2/,
sheets_map2.json) so they can be visually classified into
vision_tags2.json without disturbing the existing classification.
"""

import json
import re
import subprocess
from pathlib import Path

ROOT = Path(r"D:\Youtube\RYAN_REYNOLDS_DEADPOOL_VIDEO_BLUEPRINT")
INDEX_FILE = ROOT / "shot_index.json"
FRAMES = ROOT / "vision_frames2"
SHEETS = ROOT / "vision_sheets2"
MAP_FILE = ROOT / "sheets_map2.json"
SOURCES = [ROOT / "youtube_videos", ROOT / "pexels_videos",
           ROOT / "build", ROOT / "reference"]
COLS, ROWS = 4, 5


def dur_of(p):
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(p)],
        capture_output=True, text=True, timeout=30)
    return float(r.stdout.strip())


def detect(p):
    r = subprocess.run(
        ["ffmpeg", "-hide_banner", "-i", str(p),
         "-vf", "scale=320:180,select='gt(scene,0.30)',"
                "metadata=print:file=-",
         "-an", "-f", "null", "-"],
        capture_output=True, text=True, timeout=1800)
    return sorted({float(m.group(1))
                   for m in re.finditer(r"pts_time:([0-9.]+)",
                                        r.stdout or "")})


def main():
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        subprocess.run(["pip", "install", "pillow", "-q"], check=True)
        from PIL import Image, ImageDraw

    cache = json.loads(INDEX_FILE.read_text()) if INDEX_FILE.exists() else {}

    vids = []
    for d in SOURCES:
        if d.exists():
            vids += [p for p in sorted(d.rglob("*"))
                     if p.suffix.lower() in
                     {".mp4", ".mov", ".mkv", ".webm", ".avi"}]

    new_sources = []
    for v in vids:
        if str(v) in cache:
            continue
        try:
            d = dur_of(v)
        except Exception:
            print(f"[!] unreadable: {v.name}")
            continue
        print(f"[*] detecting scenes: {v.name} ({d:.0f}s)...", flush=True)
        cuts = detect(v)
        cache[str(v)] = {"size": v.stat().st_size,
                         "mtime": int(v.stat().st_mtime),
                         "duration": d, "cuts": cuts}
        new_sources.append(v)
        print(f"    {len(cuts)} cuts")

    INDEX_FILE.write_text(json.dumps(cache))
    if not new_sources:
        print("[OK] no new videos to index")
        return

    FRAMES.mkdir(exist_ok=True)
    SHEETS.mkdir(exist_ok=True)
    cells = []
    for v in new_sources:
        meta = cache[str(v)]
        d = meta["duration"]
        bounds = [0.0] + [c for c in meta["cuts"] if 0.5 < c < d - 0.5] + [d]
        for si in range(len(bounds) - 1):
            a, b = bounds[si], bounds[si + 1]
            if b - a < 1.2:
                continue
            cells.append({"id": len(cells), "source": v.stem,
                          "src": str(v), "scene": si,
                          "t": round((a + b) / 2, 2)})

    print(f"[*] photographing {len(cells)} new scenes")
    for i, c in enumerate(cells):
        f = FRAMES / f"f_{c['id']:04d}.jpg"
        if not f.exists():
            subprocess.run(
                ["ffmpeg", "-ss", str(c["t"]), "-i", c["src"],
                 "-frames:v", "1", "-vf", "scale=320:180", "-q:v", "4",
                 "-y", str(f)], capture_output=True, timeout=60)
        if (i + 1) % 100 == 0:
            print(f"    [{i+1}/{len(cells)}]")

    per = COLS * ROWS
    n = (len(cells) + per - 1) // per
    for s in range(n):
        sheet = Image.new("RGB", (COLS * 320, ROWS * 200), "black")
        drw = ImageDraw.Draw(sheet)
        for k in range(per):
            idx = s * per + k
            if idx >= len(cells):
                break
            c = cells[idx]
            fp = FRAMES / f"f_{c['id']:04d}.jpg"
            x, y = (k % COLS) * 320, (k // COLS) * 200
            if fp.exists():
                try:
                    sheet.paste(Image.open(fp).resize((320, 180)), (x, y))
                except Exception:
                    pass
            drw.rectangle([x, y + 180, x + 320, y + 200], fill="black")
            drw.text((x + 4, y + 183),
                     f"#{c['id']} {c['source'][:26]} s{c['scene']}",
                     fill="white")
        sheet.save(SHEETS / f"sheet_{s:02d}.jpg", quality=85)

    MAP_FILE.write_text(json.dumps(cells, indent=0))
    print(f"[OK] {len(cells)} new scenes -> {n} sheets in vision_sheets2/")


if __name__ == "__main__":
    main()
