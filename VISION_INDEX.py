#!/usr/bin/env python3
"""
VISION_INDEX - extract one keyframe per detected scene from every source
video and tile them into labeled contact sheets so each scene's actual
content (subject, gender, activity) can be visually classified.

Outputs:
  vision_frames/  f_<id>.jpg          one frame per scene
  vision_sheets/  sheet_<n>.jpg       4x5 labeled grids of those frames
  sheets_map.json                     cell id -> (source, scene, time)
Reuses the scene cuts cached in shot_index.json (no re-detection).
"""

import json
import subprocess
from pathlib import Path

ROOT = Path(r"D:\Youtube\RYAN_REYNOLDS_DEADPOOL_VIDEO_BLUEPRINT")
INDEX_FILE = ROOT / "shot_index.json"
FRAMES = ROOT / "vision_frames"
SHEETS = ROOT / "vision_sheets"
MAP_FILE = ROOT / "sheets_map.json"

COLS, ROWS = 4, 5
CELL_W, CELL_H = 320, 200   # 180 image + 20 label strip


def main():
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        subprocess.run(["pip", "install", "pillow", "-q"], check=True)
        from PIL import Image, ImageDraw

    cache = json.loads(INDEX_FILE.read_text())
    FRAMES.mkdir(exist_ok=True)
    SHEETS.mkdir(exist_ok=True)

    # one entry per scene of every source video
    cells = []
    for src_path, meta in cache.items():
        src = Path(src_path)
        if not src.exists():
            continue
        dur = meta["duration"]
        cuts = [c for c in meta["cuts"] if 0.5 < c < dur - 0.5]
        bounds = [0.0] + cuts + [dur]
        for si in range(len(bounds) - 1):
            a, b = bounds[si], bounds[si + 1]
            if b - a < 1.2:
                continue
            cells.append({"id": len(cells), "source": src.stem,
                          "src": str(src), "scene": si,
                          "t": round((a + b) / 2, 2)})

    print(f"[*] {len(cells)} scenes to photograph")

    # extract frames (skip existing so re-runs are fast)
    for i, c in enumerate(cells):
        f = FRAMES / f"f_{c['id']:04d}.jpg"
        if not f.exists():
            subprocess.run(
                ["ffmpeg", "-ss", str(c["t"]), "-i", c["src"],
                 "-frames:v", "1", "-vf", "scale=320:180", "-q:v", "4",
                 "-y", str(f)],
                capture_output=True, timeout=60)
        if (i + 1) % 50 == 0:
            print(f"    [{i + 1}/{len(cells)}] frames")

    # tile into labeled sheets
    per_sheet = COLS * ROWS
    n_sheets = (len(cells) + per_sheet - 1) // per_sheet
    for s in range(n_sheets):
        sheet = Image.new("RGB", (COLS * CELL_W, ROWS * CELL_H), "black")
        drw = ImageDraw.Draw(sheet)
        for k in range(per_sheet):
            idx = s * per_sheet + k
            if idx >= len(cells):
                break
            c = cells[idx]
            fp = FRAMES / f"f_{c['id']:04d}.jpg"
            x, y = (k % COLS) * CELL_W, (k // COLS) * CELL_H
            if fp.exists():
                try:
                    img = Image.open(fp).resize((320, 180))
                    sheet.paste(img, (x, y))
                except Exception:
                    pass
            label = f"#{c['id']}  {c['source'][:28]} s{c['scene']}"
            drw.rectangle([x, y + 180, x + CELL_W, y + CELL_H], fill="black")
            drw.text((x + 4, y + 183), label, fill="white")
        sheet.save(SHEETS / f"sheet_{s:02d}.jpg", quality=85)

    MAP_FILE.write_text(json.dumps(cells, indent=0))
    print(f"[OK] {len(cells)} scenes -> {n_sheets} sheets in vision_sheets/")
    print("[OK] map saved: sheets_map.json")


if __name__ == "__main__":
    main()
