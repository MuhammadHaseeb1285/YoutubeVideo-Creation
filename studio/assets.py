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


def download_one(query: str, out, index: int = 1) -> bool:
    """Download the `index`-th search result for `query` to `out` in HD."""
    if out.exists() and out.stat().st_size > 500_000:
        return True
    args = ["yt-dlp", "-f", _HD_FMT, "--no-playlist",
            "--merge-output-format", "mp4", "-o", str(out),
            "--playlist-items", str(index),
            "--match-filter", "duration>=40 & duration<=2400",
            f"ytsearch{index + 3}:{query}"]
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


def download(queries: list, per_query: int = 2):
    """Grab several HD clips per search so there is enough unique footage to
    fill a full-length documentary without repeating shots."""
    settings.ASSETS_VIDEO.mkdir(parents=True, exist_ok=True)
    got, total = 0, max(1, len(queries) * per_query)
    for qi, (query, stem) in enumerate(queries):
        logs.log(f"  [*] {query}")
        for k in range(per_query):
            out = settings.ASSETS_VIDEO / f"{stem}_{k}.mp4"
            logs.progress(100 * (qi * per_query + k) / total,
                          f"downloading {stem}_{k}")
            if out.exists() and out.stat().st_size > 500_000:
                got += 1
                continue
            if download_one(query, out, index=k + 1):
                logs.log(f"      OK {stem}_{k} "
                         f"({out.stat().st_size/1e6:.0f} MB HD)")
                got += 1
            else:
                logs.log(f"      no clip {k + 1} for this search")
    logs.log(f"[OK] {got} HD clips downloaded")
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
