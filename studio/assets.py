"""assets - acquire and account for source media. Downloads footage with a
retry engine, and reports an inventory the dashboard shows: totals per
type, how many are indexed, duplicates, and missing (indexed but the file
is gone).
"""

import hashlib
import json
import os
import subprocess

from . import settings, logs


# ------------------------------------------------------------ download
# Prefer real HD (up to 1080p), merged to mp4. Avoids the old 720p cap so
# footage is sharp, not blurry/upscaled.
_HD_FMT = ("bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/"
           "best[height<=1080][ext=mp4]/best[height>=360][ext=mp4]/best")


def download_from_urls(urls: list, slug: str = "manual") -> int:
    """Download videos from user-provided YouTube/video URLs directly.
    Skips searching, face verification, goes straight to download.
    Fast because you're providing the exact links.
    Accepts Shorts and clips (lower file size requirement since user trusts them)."""
    settings.ASSETS_VIDEO.mkdir(parents=True, exist_ok=True)
    got = 0

    for i, url in enumerate(urls):
        url = url.strip()
        if not url:
            continue

        out = settings.ASSETS_VIDEO / f"{slug}_{i}.mp4"

        # Skip if already downloaded
        if out.exists() and out.stat().st_size > 50_000:  # 50KB for Shorts
            got += 1
            logs.log(f"  [=] {slug}_{i} exists")
            continue

        logs.log(f"  [*] {slug}_{i}: {url[:60]}...")
        args = ["yt-dlp", "-f", _HD_FMT, "--no-playlist",
                "--merge-output-format", "mp4", "-o", str(out),
                url]
        try:
            r = subprocess.run(args, capture_output=True, text=True, timeout=360)
            if r.returncode != 0:
                logs.log(f"      yt-dlp error: {r.stderr[:100]}")
        except Exception as e:
            logs.log(f"      exception: {e}")

        if not out.exists():
            logs.log(f"      failed: file not created")
            continue

        sz = out.stat().st_size
        if sz < 50_000:
            logs.log(f"      rejected: {sz/1000:.0f}KB too small")
            try:
                out.unlink()
            except OSError:
                pass
            continue

        h = _probe_height(out)
        if h > 0 and h < 360:
            logs.log(f"      rejected: {h}p too low (Shorts acceptable but must stream)")
            try:
                out.unlink()
            except OSError:
                pass
            continue

        logs.log(f"      OK {slug}_{i} ({sz/1000:.0f}KB {h}p)")
        got += 1

    logs.log(f"[OK] {got}/{len(urls)} manual videos downloaded")
    return got


def _search_ids(query: str, n: int = 6) -> list:
    """IDs of the top n YouTube results for a query (fast, no download)."""
    try:
        # Increase timeout to 240s (yt-dlp can be slow on first run or with network delays)
        r = subprocess.run(
            ["yt-dlp", "--flat-playlist", "--print", "id",
             f"ytsearch{n}:{query}"],
            capture_output=True, text=True, timeout=240)
        return [l.strip() for l in (r.stdout or "").splitlines()
                if l.strip()]
    except subprocess.TimeoutExpired:
        logs.log(f"  search timeout for: {query}", "warn")
        return []
    except Exception as e:
        logs.log(f"  search error: {e}", "warn")
        return []


def _probe_height(path) -> int:
    """Get video height in pixels using ffprobe."""
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=height", "-of", "csv=p=0", str(path)],
            capture_output=True, text=True, timeout=30)
        return int(r.stdout.strip().split("\n")[0])
    except Exception:
        return 0


def _verify_subject_in_video(video_path, subject_name: str, ref_image_path=None):
    """Use Gemini Vision to verify the celebrity is actually in the video.
    Samples 3 frames and checks if the subject appears. Returns True if
    subject is detected, False if it's a reaction/commentary video."""
    try:
        from PIL import Image
        import tempfile
        import time
        from google import genai
    except ImportError:
        return True  # if vision unavailable, accept it

    ref_img = None
    if ref_image_path and ref_image_path.exists():
        try:
            ref_img = Image.open(ref_image_path)
        except Exception:
            pass

    # Get video duration
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(video_path)],
        capture_output=True, text=True, timeout=30)
    try:
        duration = float(r.stdout.strip())
    except Exception:
        return True

    # Sample 3 frames: start, middle, end
    times = [duration * 0.1, duration * 0.5, duration * 0.9]
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        kf = settings.ROOT / "gemini_key.txt"
        if kf.exists():
            key = kf.read_text(encoding="utf-8").strip()

    if not key:
        return True  # no vision key, accept it

    client = genai.Client(api_key=key)
    found_subject = False

    with tempfile.TemporaryDirectory() as tmpdir:
        for i, t in enumerate(times):
            frame_path = f"{tmpdir}/frame_{i}.jpg"
            subprocess.run(
                ["ffmpeg", "-ss", f"{t:.1f}", "-i", str(video_path),
                 "-frames:v", "1", "-q:v", "2", "-y", frame_path],
                capture_output=True, timeout=30)

            if not os.path.exists(frame_path):
                continue

            try:
                frame = Image.open(frame_path)
                prompt = f"""Look at this video frame. Is {subject_name} (the celebrity/person
we're looking for) clearly visible and appears to be the main person in this frame?
Answer only YES or NO.

If this is a reaction video where someone else is talking about {subject_name},
or if {subject_name} is absent or tiny in background, answer NO."""

                contents = [prompt]
                if ref_img:
                    contents.append(ref_img)
                contents.append(frame)

                resp = client.models.generate_content(
                    model="gemini-2.0-flash",
                    contents=contents)
                answer = (resp.text or "").upper()

                if "YES" in answer:
                    found_subject = True
                    break

                time.sleep(1.0)
            except Exception as e:
                logs.log(f"      vision check failed: {e}", "error")
                continue

    return found_subject


def _download_id(vid: str, out, subject: str = "", ref_image_path=None) -> bool:
    # Exclude reaction videos, commentary, reviews with negative filters
    args = ["yt-dlp", "-f", _HD_FMT, "--no-playlist",
            "--merge-output-format", "mp4", "-o", str(out),
            "--match-filter", "duration>=40 & duration<=2400",
            "--match-filter", "!title ~= '(?i)(reaction|reacts|commentary|response|reviews?|responds)'",
            f"https://www.youtube.com/watch?v={vid}"]
    try:
        subprocess.run(args, capture_output=True, text=True, timeout=360)
    except Exception:
        pass
    if not out.exists():
        return False
    sz = out.stat().st_size
    if sz <= 500_000:
        return False
    h = _probe_height(out)
    if h < 360:
        logs.log(f"      rejected: {h}p < 360p minimum")
        return False

    # CRITICAL: Verify the subject is actually in this video
    # (not a reaction video with fake title)
    if subject and (ref_image_path and ref_image_path.exists()):
        if not _verify_subject_in_video(out, subject, ref_image_path):
            logs.log(f"      rejected: {subject} not found in video (reaction?)")
            try:
                out.unlink()
            except OSError:
                pass
            return False

    return True


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


def _fetch_pexels(query: str, count: int = 2) -> int:
    """Download high-quality generic footage from Pexels (gym, exercise, diet,
    cardio, etc.). Requires PEXELS_API_KEY env var or pexels_key.txt file."""
    try:
        import requests
    except ImportError:
        logs.log("  pexels: requests not available", "error")
        return 0

    key = os.environ.get("PEXELS_API_KEY", "").strip()
    if not key:
        kf = settings.ROOT / "pexels_key.txt"
        if kf.exists():
            key = kf.read_text(encoding="utf-8").strip()
    if not key:
        return 0

    got = 0
    try:
        headers = {"Authorization": key, "User-Agent": "DocumentaryStudio/1.0"}
        url = "https://api.pexels.com/v1/videos/search"
        resp = requests.get(url, headers=headers,
                           params={"query": query, "per_page": count},
                           timeout=30)
        data = resp.json()
        videos = data.get("videos", [])

        for i, video in enumerate(videos[:count]):
            try:
                dl_url = video["video_files"][0]["link"]
                name = f"pexels_{query.replace(' ', '_')}_{i}.mp4"
                out = settings.ASSETS_VIDEO / name

                if out.exists() and out.stat().st_size > 500_000:
                    got += 1
                    continue

                logs.progress(0, f"pexels: {query} {i+1}/{count}")
                r = requests.get(dl_url, headers=headers, timeout=120)
                out.write_bytes(r.content)
                sz = out.stat().st_size

                if sz > 500_000:
                    logs.log(f"  pexels: {name} ({sz/1e6:.1f} MB)")
                    got += 1
                else:
                    out.unlink()
            except Exception as e:
                pass
    except Exception as e:
        logs.log(f"  pexels search failed: {e}", "error")

    return got


def download(queries: list, per_query: int = 3, subject: str = ""):
    """Grab several HD clips per search from YouTube (celebrity-specific).
    Also fetch generic footage from Pexels (gym, exercise, diet, cardio).
    Videos are validated: 720p+, correct resolution, AND subject is in video."""
    import json as _json
    from pathlib import Path
    settings.ASSETS_VIDEO.mkdir(parents=True, exist_ok=True)
    settings.CACHE.mkdir(parents=True, exist_ok=True)
    reg_file = settings.CACHE / "yt_ids.json"
    reg = set()
    if reg_file.exists():
        try:
            reg = set(_json.loads(reg_file.read_text()))
        except Exception:
            reg = set()

    # Load reference image if available (for subject verification)
    ref_image = Path(settings.CACHE) / "subject_ref.jpg"
    if not ref_image.exists():
        ref_image = None

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
            if _download_id(vid, out, subject, ref_image):
                logs.log(f"      OK {stem}_{picked} "
                         f"({out.stat().st_size/1e6:.0f} MB HD)")
                picked += 1
                got += 1
                reg_file.write_text(_json.dumps(sorted(reg)))
        if picked == len(have):
            logs.log("      no new unique clip for this search")

    # Supplement with Pexels generic footage (gym, exercise, diet, cardio)
    logs.log("  [*] Pexels: generic fitness footage")
    pexels_queries = [
        ("fitness training gym", 3),
        ("strength training weights", 3),
        ("running cardio sprint", 2),
        ("healthy eating nutrition meal", 2),
        ("recovery stretching yoga", 2),
        ("bodybuilding workout exercise", 2),
    ]
    for pq, pcount in pexels_queries:
        p_got = _fetch_pexels(pq, pcount)
        got += p_got
        if p_got > 0:
            logs.log(f"      Pexels: {pq} ({p_got} videos)")

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
