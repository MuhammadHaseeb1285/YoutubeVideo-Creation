"""indexer - turn raw videos into a searchable shot database. Detects real
scene cuts (ffmpeg), caches them, and joins them with any visual tags (or a
filename-derived fallback) into per-shot records the selector ranks.
"""

import json
import subprocess
from pathlib import Path

from . import settings, logs


# ------------------------------------------------------------ scene cuts
def _probe_duration(p):
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(p)],
        capture_output=True, text=True, timeout=30)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def _detect_cuts(p, threshold=0.30):
    """Return scene-cut timestamps via ffmpeg scene detection."""
    r = subprocess.run(
        ["ffmpeg", "-i", str(p), "-filter:v",
         f"select='gt(scene,{threshold})',showinfo", "-f", "null", "-"],
        capture_output=True, text=True, timeout=600)
    cuts = []
    for line in (r.stderr or "").splitlines():
        if "pts_time:" in line:
            try:
                cuts.append(float(line.split("pts_time:")[1].split()[0]))
            except (IndexError, ValueError):
                pass
    return sorted(cuts)


def index_videos(progress_cb=None):
    """Scene-detect any video not already cached. Returns the cache."""
    settings.CACHE.mkdir(parents=True, exist_ok=True)
    cache = {}
    if settings.SHOT_INDEX.exists():
        try:
            cache = json.loads(settings.SHOT_INDEX.read_text())
        except Exception:
            cache = {}
    vids = [p for p in settings.ASSETS_VIDEO.rglob("*")
            if p.is_file() and p.suffix.lower() in settings.VIDEO_EXTS]
    todo = [p for p in vids if str(p) not in cache or not Path(str(p)).exists()]
    logs.log(f"indexing: {len(vids)} videos, {len(todo)} new")
    for i, p in enumerate(todo):
        dur = _probe_duration(p)
        if dur <= 0:
            continue
        cuts = _detect_cuts(p)
        cache[str(p)] = {"duration": dur, "cuts": cuts}
        if progress_cb:
            progress_cb(100 * (i + 1) / max(1, len(todo)), p.name)
        logs.log(f"  scenes: {p.name} ({len(cuts)} cuts)")
    # drop entries whose files vanished
    cache = {k: v for k, v in cache.items() if Path(k).exists()}
    settings.SHOT_INDEX.write_text(json.dumps(cache))
    return cache


# ------------------------------------------------------------ fallback tags
def fallback_tag(stem: str):
    """Category for footage without a visual classification, from the
    search intent encoded in the filename by the downloader."""
    s = stem.lower()
    if "reference" in s:
        return ["ryan_bts", "m", 1, 2]
    if "_coach" in s:
        return ["coach_talk", "m", 1, 1]
    if "_gym" in s or "_tr" in s:
        return ["ryan_gym", "m", 1, 1]
    # talking-head style footage (interviews, podcasts, talk shows, press)
    if any(k in s for k in ("_int", "_pod", "_talk", "_ts", "_pg", "_st",
                            "_biz", "_key", "_conf", "_sp", "_rc", "_aw")):
        return ["ryan_interview", "m", 1, 1]
    # clip / montage / performance style footage -> subject-movie group
    if any(k in s for k in ("_bts", "_yt", "_vlog", "_mom", "_hl", "_doc",
                            "_bio", "_live", "_mv", "_con", "_film", "_play",
                            "_act", "_car", "_app", "_co", "_fun")):
        return ["ryan_bts", "m", 1, 1]
    if "_diet" in s:
        return ["food", "n", 1, 1]
    # generic exercise B-roll named by category
    for key, cat in (("chest", "chest"), ("back", "back"), ("leg", "legs"),
                     ("shoulder", "shoulders"), ("cardio", "cardio"),
                     ("run", "cardio_run"), ("nutrition", "food"),
                     ("recovery", "recovery"), ("equipment", "equipment")):
        if key in s:
            return [cat, "m", 1, 1]
    return ["ryan_gym", "m", 1, 1]


EXERCISE_SOURCE_DEFAULTS = [
    ("back_row_pullup", "pullup"), ("dumbbell_chest_press", "bench_press"),
    ("leg_squat_lunge", "squat"), ("running_cardio_sprint", "running"),
    ("recovery_stretching_yoga", "stretching"),
    ("shoulder_arm", "overhead_press"), ("chest", "bench_press"),
    ("back", "row"), ("legs", "squat"), ("cardio", "running"),
]


def exercise_of_shot(source):
    s = source.lower()
    for frag, ex in EXERCISE_SOURCE_DEFAULTS:
        if frag in s:
            return ex
    return None


# ------------------------------------------------------------ shot database
def build_shot_db():
    """Join cached scene cuts with tags (or fallback) into shot records."""
    if not settings.SHOT_INDEX.exists():
        return [], 0
    cuts_cache = json.loads(settings.SHOT_INDEX.read_text())

    scene_tag = {}
    if settings.SHEETS_MAP.exists() and settings.VISION_TAGS.exists():
        try:
            cells = json.loads(settings.SHEETS_MAP.read_text())
            tags = json.loads(settings.VISION_TAGS.read_text())
            for c in cells:
                t = tags.get(str(c["id"]))
                if t:
                    scene_tag[(c["source"], c["scene"])] = t
        except Exception:
            pass

    shots, dropped = [], 0
    for src_path, meta in cuts_cache.items():
        src = Path(src_path)
        if not src.exists():
            continue
        dur = meta["duration"]
        cuts = [c for c in meta["cuts"] if 0.5 < c < dur - 0.5]
        bounds = [0.0] + cuts + [dur]
        for si in range(len(bounds) - 1):
            a, b = bounds[si], bounds[si + 1]
            length = b - a
            if length < settings.MIN_SHOT:
                continue
            tag = scene_tag.get((src.stem, si)) or fallback_tag(src.stem)
            if not tag or not tag[2]:
                dropped += 1
                continue
            cat, gender, _, q = tag
            n_seg = min(settings.SEG_MAX,
                        max(1, int(length // settings.SEG_EVERY) + 1))
            for gi in range(n_seg):
                st = a + (length / n_seg) * gi + 0.1
                ln = min(7.0, (length / n_seg) - 0.2)
                if ln < settings.MIN_SHOT:
                    continue
                shots.append({"id": f"{src.stem}|{si}|{gi}",
                              "src": str(src), "source": src.stem,
                              "scene": f"{src.stem}|{si}",
                              "start": round(st, 2), "len": round(ln, 2),
                              "cat": cat, "g": gender, "q": q,
                              "ex": exercise_of_shot(src.stem)})
    return shots, dropped
