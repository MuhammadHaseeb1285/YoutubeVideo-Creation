"""vision - classify what is ACTUALLY IN each detected scene, so the editor
matches footage to the narration by real content instead of filenames.

For every scene we grab a representative frame, tile the frames into labeled
contact sheets, and send each sheet to Gemini Vision. Gemini returns a
category per scene (subject-talking, subject-gym, chest, food, ...), plus a
usability flag that drops graphics / text slides / subscribe screens /
watermarked junk. The result is written to vision_tags.json + sheets_map.json,
which the shot database already reads.

This mirrors the reference project's AUTO_TAGS step and is what lifts
audio-visual sync from "filename-approximate" to content-accurate.

Needs a Google Gemini API key (free tier at aistudio.google.com/apikey),
read from GEMINI_API_KEY or gemini_key.txt.
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

from . import settings, logs

MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash")
COLS, ROWS = 4, 5
CELL_W, CELL_H = 320, 180
PER_SHEET = COLS * ROWS


class NoVisionKey(Exception):
    """No Gemini API key available for content classification."""


def _key():
    k = os.environ.get("GEMINI_API_KEY", "").strip()
    if not k:
        kf = settings.ROOT / "gemini_key.txt"
        if kf.exists():
            k = kf.read_text(encoding="utf-8").strip()
    return k


def _scenes_from_index():
    """[(cell_id, source_stem, scene_index, src_path, mid_time)] for every
    usable detected scene."""
    if not settings.SHOT_INDEX.exists():
        return []
    cache = json.loads(settings.SHOT_INDEX.read_text())
    out, cid = [], 0
    for src_path, meta in cache.items():
        src = Path(src_path)
        if not src.exists():
            continue
        dur = meta["duration"]
        cuts = [c for c in meta["cuts"] if 0.5 < c < dur - 0.5]
        bounds = [0.0] + cuts + [dur]
        for si in range(len(bounds) - 1):
            a, b = bounds[si], bounds[si + 1]
            if b - a < settings.MIN_SHOT:
                continue
            out.append((cid, src.stem, si, src, (a + b) / 2))
            cid += 1
    return out


def _grab(src, t, out):
    subprocess.run(
        ["ffmpeg", "-ss", f"{t:.2f}", "-i", str(src), "-frames:v", "1",
         "-vf", f"scale={CELL_W}:{CELL_H}:force_original_aspect_ratio="
         f"increase,crop={CELL_W}:{CELL_H}", "-y", str(out)],
        capture_output=True, timeout=30)


def build_contact_sheets(progress_cb=None):
    """Extract one frame per scene, tile into labeled 4x5 sheets, and write
    sheets_map.json. Returns (sheet_paths, cells)."""
    from PIL import Image, ImageDraw, ImageFont
    scenes = _scenes_from_index()
    sheets_dir = settings.CACHE / "sheets"
    frames_dir = settings.CACHE / "frames"
    sheets_dir.mkdir(parents=True, exist_ok=True)
    frames_dir.mkdir(parents=True, exist_ok=True)

    try:
        font = ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", 20)
    except Exception:
        font = ImageFont.load_default()

    frames, cells = [], []
    for i, (cid, stem, si, src, mid) in enumerate(scenes):
        fp = frames_dir / f"f_{cid}.jpg"
        _grab(src, mid, fp)
        if fp.exists() and fp.stat().st_size > 500:
            frames.append((cid, fp))
            cells.append({"id": cid, "source": stem, "scene": si})
        if progress_cb and i % 20 == 0:
            progress_cb(40 * i / max(1, len(scenes)), f"frames {i}/{len(scenes)}")

    sheet_paths = []
    for s in range(0, len(frames), PER_SHEET):
        batch = frames[s:s + PER_SHEET]
        sheet = Image.new("RGB", (COLS * CELL_W, ROWS * CELL_H), (12, 12, 16))
        d = ImageDraw.Draw(sheet)
        for i, (cid, fp) in enumerate(batch):
            try:
                cell = Image.open(fp).convert("RGB").resize((CELL_W, CELL_H))
            except Exception:
                continue
            x, y = (i % COLS) * CELL_W, (i // COLS) * CELL_H
            sheet.paste(cell, (x, y))
            d.rectangle([x, y, x + 70, y + 26], fill=(210, 0, 20))
            d.text((x + 6, y + 3), f"#{cid}", fill="white", font=font)
        sp = sheets_dir / f"sheet_{s // PER_SHEET}.jpg"
        sheet.save(sp, quality=85)
        sheet_paths.append((sp, [c for c, _ in batch]))

    settings.SHEETS_MAP.write_text(json.dumps(cells))
    return sheet_paths, cells


def _prompt(subject, coach, ids):
    coach_line = (f"COACH/TRAINER (the actual trainer of {subject}, a "
                  f"different specific person):\n  coach_gym, coach_talk\n"
                  ) if coach else ""
    return f"""You are labeling frames from a documentary about {subject}.
The image is a grid of video frames, read left-to-right, top-to-bottom.
Each frame has a red "#<id>" label in its top-left corner.

THE MOST IMPORTANT RULE - SUBJECT DOMINANCE:
Use a SUBJECT category ONLY when {subject} is clearly the MAIN person in the
frame - recognisably {subject}, in focus, occupying most of the frame. If the
dominant person is SOMEONE ELSE (an interviewer, podcast host, another guest,
an audience member, a reporter, or an unrelated person), or if {subject} is
absent, tiny, in the background, or only barely visible, mark it "x". When in
doubt about whether it is really {subject} and whether they dominate the
frame, mark it "x". We only want shots that are clearly about {subject}.

Classify EACH labeled frame using exactly one category:

SUBJECT ({subject}) is the main person, talking / posing / in public:
  ryan_interview, ryan_press, ryan_event
SUBJECT ({subject}) training or showing physique:
  ryan_gym, ryan_photoshoot, ryan_abs, ryan_shirtless
SUBJECT ({subject}) other (film role, behind the scenes, candid):
  ryan_movie, ryan_bts, ryan_photo, ryan_outdoor, ryan_home
{coach_line}GENERIC EXERCISE B-ROLL (a non-famous person training, use only as backup):
  chest, back, legs, shoulders, arms, cardio, equipment, recovery
NUTRITION (food, meals, cooking, supplements):
  food
UNUSABLE - mark "x":
  graphics, text slides, titles, logos, channel watermarks, subscribe/like
  screens, social-media or Shorts/Reels UI, cartoons, OR any frame whose main
  person is NOT {subject} (interviewer/host/guest/audience/other), OR where
  {subject} is absent or barely visible.

For each id return a 4-item array: [category, gender, use, quality]
  - category: one exact string above, or "x"
  - gender: "m", "f", or "n"
  - use: 1 if usable AND {subject} clearly dominates (or it is pure B-roll/
         food); 0 for anything "x"
  - quality: 0 (poor/blurry/low-res/watermarked), 1 (ok), 2 (clean, sharp,
         cinematic, {subject} large and centred)

The ids on this sheet are: {ids}
Return ONLY a JSON object mapping each id (as a string) to its 4-item array."""


def auto_tag(subject, coach="", progress_cb=None):
    """Classify every scene's real content with Gemini. Writes
    vision_tags.json. Returns the number of scenes tagged."""
    key = _key()
    if not key:
        raise NoVisionKey("no GEMINI_API_KEY / gemini_key.txt")
    # reuse cached tags when this project's scenes are already classified
    scenes = _scenes_from_index()
    if settings.VISION_TAGS.exists() and settings.SHEETS_MAP.exists():
        try:
            existing = json.loads(settings.VISION_TAGS.read_text())
            if scenes and len(existing) >= len(scenes) * 0.9:
                logs.log(f"vision: using cached content tags for "
                         f"{len(existing)} scenes")
                return len(existing)
        except Exception:
            pass
    try:
        from google import genai
    except ImportError:
        subprocess.run([sys.executable, "-m", "pip", "install",
                        "google-genai", "-q"], check=True)
        from google import genai
    from PIL import Image

    sheet_paths, cells = build_contact_sheets(progress_cb)
    if not sheet_paths:
        raise RuntimeError("no scenes to classify")
    client = genai.Client(api_key=key)
    tags = {}
    for i, (sp, ids) in enumerate(sheet_paths):
        try:
            img = Image.open(sp)
            resp = client.models.generate_content(
                model=MODEL, contents=[_prompt(subject, coach, ids), img])
            raw = (resp.text or "").strip()
            m = re.search(r"\{.*\}", raw, re.S)
            if m:
                part = json.loads(m.group(0))
                for k, v in part.items():
                    if isinstance(v, list) and len(v) >= 4:
                        tags[str(k)] = [v[0], v[1], int(v[2]), int(v[3])]
        except Exception as e:
            logs.log(f"  vision sheet {i} failed: {e}", "error")
        if progress_cb:
            progress_cb(40 + 60 * (i + 1) / len(sheet_paths),
                        f"classified sheet {i + 1}/{len(sheet_paths)}")
    settings.VISION_TAGS.write_text(json.dumps(tags))
    usable = sum(1 for v in tags.values() if v[2])
    logs.log(f"vision: {len(tags)} scenes classified, {usable} usable "
             f"({len(tags) - usable} graphics/junk excluded)")
    return len(tags)
