"""assets - acquire and account for source media. Downloads footage with a
retry engine, and reports an inventory the dashboard shows: totals per
type, how many are indexed, duplicates, and missing (indexed but the file
is gone).
"""

import hashlib
import json
import subprocess

from . import settings, logs


# ------------------------------------------------------------ download
# Prefer real HD (up to 1080p), merged to mp4. Avoids the old 720p cap so
# footage is sharp, not blurry/upscaled.
_HD_FMT = ("bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/"
           "best[height<=1080][ext=mp4]/best[ext=mp4]/best")


def _search_ids(query: str, n: int = 6) -> list:
    """IDs of the top n YouTube results for a query (fast, no download)."""
    try:
        r = subprocess.run(
            ["yt-dlp", "--flat-playlist", "--print", "id",
             f"ytsearch{n}:{query}"],
            capture_output=True, text=True, timeout=90)
        return [l.strip() for l in (r.stdout or "").splitlines()
                if l.strip()]
    except Exception:
        return []


def _download_id(vid: str, out) -> bool:
    args = ["yt-dlp", "-f", _HD_FMT, "--no-playlist",
            "--merge-output-format", "mp4", "-o", str(out),
            "--match-filter", "duration>=40 & duration<=2400",
            f"https://www.youtube.com/watch?v={vid}"]
    try:
        subprocess.run(args, capture_output=True, text=True, timeout=360)
    except Exception:
        pass
    ok = out.exists() and out.stat().st_size > 500_000
    if not ok:
        for part in out.parent.glob(out.stem + "*"):
            try:
                part.unlink()
            except OSError:
                pass
    return ok


def _dedupe_videos() -> int:
    """Delete byte-identical video files (same content downloaded under two
    different search stems)."""
    seen, removed = {}, 0
    for p in sorted(settings.ASSETS_VIDEO.glob("*.mp4")):
        h = _quick_hash(p)
        if h is None:
            continue
        if h in seen:
            try:
                p.unlink()
                removed += 1
            except OSError:
                pass
        else:
            seen[h] = p
    return removed


def download(queries: list, per_query: int = 2):
    """Grab several HD clips per search. A registry of YouTube video IDs
    guarantees the same video is never downloaded twice across different
    searches; a content-hash pass cleans any remaining duplicates."""
    import json as _json
    settings.ASSETS_VIDEO.mkdir(parents=True, exist_ok=True)
    settings.CACHE.mkdir(parents=True, exist_ok=True)
    reg_file = settings.CACHE / "yt_ids.json"
    reg = set()
    if reg_file.exists():
        try:
            reg = set(_json.loads(reg_file.read_text()))
        except Exception:
            reg = set()

    got, total = 0, max(1, len(queries) * per_query)
    for qi, (query, stem) in enumerate(queries):
        logs.progress(100 * qi * per_query / total, f"searching: {query}")
        # count clips already on disk for this stem
        have = [p for p in settings.ASSETS_VIDEO.glob(f"{stem}_*.mp4")
                if p.stat().st_size > 500_000]
        if len(have) >= per_query:
            got += len(have)
            continue
        logs.log(f"  [*] {query}")
        ids = [v for v in _search_ids(query) if v not in reg]
        picked = len(have)
        for vid in ids:
            if picked >= per_query:
                break
            out = settings.ASSETS_VIDEO / f"{stem}_{picked}.mp4"
            logs.progress(100 * (qi * per_query + picked) / total,
                          f"downloading {stem}_{picked}")
            reg.add(vid)                # claim the id even if it fails
            if _download_id(vid, out):
                logs.log(f"      OK {stem}_{picked} "
                         f"({out.stat().st_size/1e6:.0f} MB HD)")
                picked += 1
                got += 1
                reg_file.write_text(_json.dumps(sorted(reg)))
        if picked == len(have):
            logs.log("      no new unique clip for this search")
    reg_file.write_text(_json.dumps(sorted(reg)))
    removed = _dedupe_videos()
    if removed:
        logs.log(f"  removed {removed} duplicate download(s)")
    logs.log(f"[OK] {got} unique HD clips ready")
    return got


# ------------------------------------------------------------ inventory
def _quick_hash(p):
    h = hashlib.md5()
    try:
        with open(p, "rb") as f:
            h.update(f.read(262144))
        h.update(str(p.stat().st_size).encode())
    except OSError:
        return None
    return h.hexdigest()


def _list(folder, exts):
    if not folder.exists():
        return []
    return [p for p in folder.rglob("*")
            if p.is_file() and p.suffix.lower() in exts]


def inventory() -> dict:
    videos = _list(settings.ASSETS_VIDEO, settings.VIDEO_EXTS)
    images = _list(settings.ASSETS_IMAGE, settings.IMAGE_EXTS)
    audio = _list(settings.ASSETS_AUDIO, settings.AUDIO_EXTS)

    # duplicates by quick content hash
    seen, dupes = {}, 0
    for p in videos + images:
        h = _quick_hash(p)
        if h is None:
            continue
        if h in seen:
            dupes += 1
        else:
            seen[h] = p

    indexed, missing = 0, 0
    if settings.SHOT_INDEX.exists():
        try:
            idx = json.loads(settings.SHOT_INDEX.read_text())
            for k in idx:
                from pathlib import Path
                if Path(k).exists():
                    indexed += 1
                else:
                    missing += 1
        except Exception:
            pass

    return {
        "videos": len(videos), "images": len(images), "audio": len(audio),
        "indexed": indexed, "duplicates": dupes, "missing": missing,
        "video_mb": round(sum(p.stat().st_size for p in videos) / 1e6),
    }


def import_files(paths: list) -> int:
    """Copy user-supplied media into the right asset folder."""
    import shutil
    n = 0
    for src in paths:
        from pathlib import Path
        p = Path(src)
        if not p.exists():
            continue
        ext = p.suffix.lower()
        if ext in settings.VIDEO_EXTS:
            dst = settings.ASSETS_VIDEO
        elif ext in settings.IMAGE_EXTS:
            dst = settings.ASSETS_IMAGE
        elif ext in settings.AUDIO_EXTS:
            dst = settings.ASSETS_AUDIO
        else:
            continue
        dst.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, dst / p.name)
        n += 1
    return n
