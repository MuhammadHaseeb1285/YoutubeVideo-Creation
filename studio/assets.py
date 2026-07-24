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
def download_one(query: str, out, attempts: int = 4) -> bool:
    if out.exists() and out.stat().st_size > 500_000:
        return True
    filters = ["duration<720", "duration<1500", "duration<2400", None]
    for i in range(1, attempts + 1):
        flt = filters[min(i - 1, len(filters) - 1)]
        args = ["yt-dlp", "-f", "best[ext=mp4][height<=720]/best[ext=mp4]",
                "--no-playlist", "-o", str(out), "--playlist-items", str(i)]
        if flt:
            args += ["--match-filter", flt]
        args.append(f"ytsearch{attempts}:{query}")
        try:
            subprocess.run(args, capture_output=True, text=True,
                           timeout=240 + i * 60)
        except Exception:
            pass
        if out.exists() and out.stat().st_size > 500_000:
            return True
        for part in out.parent.glob(out.stem + "*"):
            try:
                part.unlink()
            except OSError:
                pass
        logs.log(f"  {out.stem}: attempt {i} failed, trying next result")
    return False


def download(queries: list):
    settings.ASSETS_VIDEO.mkdir(parents=True, exist_ok=True)
    got = 0
    for i, (query, stem) in enumerate(queries):
        out = settings.ASSETS_VIDEO / f"{stem}.mp4"
        logs.progress(100 * i / max(1, len(queries)),
                      f"downloading {stem}")
        if out.exists() and out.stat().st_size > 500_000:
            logs.log(f"  [=] {stem} already present")
            got += 1
            continue
        logs.log(f"  [*] {stem}: {query}")
        if download_one(query, out):
            logs.log(f"      OK ({out.stat().st_size/1e6:.0f} MB)")
            got += 1
        else:
            logs.log(f"      FAILED after retries - continuing")
    logs.log(f"[OK] {got}/{len(queries)} videos ready")
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
