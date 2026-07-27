"""assets_enhanced - Intelligent media sourcing with auto-search + Pexels images.

Features:
- Auto-search YouTube for celebrity fitness videos (no manual links needed)
- Download Pexels videos (already done)
- Download Pexels IMAGES for supplementary content
- Smart search queries based on celebrity type
- Duplicate detection and deduplication
"""

import os
import json
from pathlib import Path
from . import settings, logs, research


def _get_pexels_key() -> str:
    """Get Pexels API key from env or file."""
    key = os.environ.get("PEXELS_API_KEY", "").strip()
    if not key:
        kf = settings.ROOT / "pexels_key.txt"
        if kf.exists():
            key = kf.read_text(encoding="utf-8").strip()
    return key


def fetch_pexels_images(query: str, count: int = 5) -> int:
    """Download high-quality images from Pexels (gym, diet, fitness, etc.)."""
    try:
        import requests
    except ImportError:
        logs.log("  pexels images: requests not available", "error")
        return 0

    key = _get_pexels_key()
    if not key:
        logs.log("  pexels: no API key, skipping images")
        return 0

    got = 0
    try:
        headers = {"Authorization": key, "User-Agent": "DocumentaryStudio/1.0"}
        url = "https://api.pexels.com/v1/search"
        resp = requests.get(url, headers=headers,
                           params={"query": query, "per_page": count, "size": "large"},
                           timeout=30)
        data = resp.json()
        photos = data.get("photos", [])

        for i, photo in enumerate(photos[:count]):
            try:
                # Get largest available image
                dl_url = photo.get("src", {}).get("large") or photo.get("src", {}).get("original")
                if not dl_url:
                    continue

                ext = ".jpg" if "jpg" in dl_url.lower() else ".png"
                name = f"pexels_{query.replace(' ', '_')}_{i}{ext}"
                out = settings.ASSETS_IMAGE / name

                if out.exists() and out.stat().st_size > 100_000:
                    got += 1
                    continue

                logs.progress(0, f"pexels images: {query} {i+1}/{count}")
                r = requests.get(dl_url, headers=headers, timeout=120)
                out.write_bytes(r.content)
                sz = out.stat().st_size

                if sz > 100_000:
                    logs.log(f"  pexels image: {name} ({sz/1e6:.1f} MB)")
                    got += 1
                else:
                    out.unlink()
            except Exception as e:
                pass

    except Exception as e:
        logs.log(f"  pexels images search failed: {e}", "error")

    return got


def auto_search_youtube(subject_name: str, coach: str = "", ctype: str = "public figure") -> int:
    """
    Auto-search YouTube for celebrity fitness videos.

    Uses intelligent queries based on celebrity type and coach info.
    Downloads 5-8 high-quality videos automatically.
    """
    from . import assets  # Use existing downloader

    logs.log(f"[AUTO-SEARCH] Searching YouTube for {subject_name} fitness videos...")

    # Build smart search queries
    queries = []

    if coach:
        # If coach known, search for coach + celebrity combination
        queries.extend([
            f"{subject_name} {coach} workout",
            f"{subject_name} training with {coach}",
            f"{subject_name} fitness routine",
        ])

    # Base queries for any celebrity
    queries.extend([
        f"{subject_name} gym workout",
        f"{subject_name} transformation",
        f"{subject_name} training routine",
        f"{subject_name} diet nutrition",
        f"{subject_name} fitness interview",
        f"{subject_name} body transformation",
        f"{subject_name} behind the scenes training",
    ])

    # If it's an actor/public figure, add movie-prep queries
    if ctype.lower() in ["actor", "movie", "public figure"]:
        queries.extend([
            f"{subject_name} movie role preparation training",
            f"{subject_name} film prep workout",
        ])

    # If it's a fitness creator, add specific queries
    if ctype.lower() in ["fitness creator", "bodybuilder", "athlete"]:
        queries.extend([
            f"{subject_name} official channel workout",
            f"{subject_name} training split",
            f"{subject_name} IFBB prep",
        ])

    # Download from all queries
    total_downloaded = 0
    for q in queries:
        try:
            got = assets.download([q], per_query=2, subject=subject_name)
            if got > 0:
                total_downloaded += got
                logs.log(f"  ✓ {q}: {got} videos")
        except Exception as e:
            logs.log(f"  ✗ {q}: {e}")

    return total_downloaded


def fetch_supplementary_media(subject_name: str, coach: str = "") -> int:
    """Fetch both Pexels videos AND images for supplementary content."""
    logs.log("[PEXELS] Fetching supplementary media...")

    got = 0

    # Pexels VIDEOS (existing)
    pexels_video_queries = [
        ("fitness training gym", 2),
        ("strength training weights", 2),
        ("running cardio sprint", 1),
        ("healthy eating nutrition meal", 1),
        ("recovery stretching yoga", 1),
    ]

    for query, count in pexels_video_queries:
        try:
            from . import assets
            result = assets._fetch_pexels(query, count)
            if result > 0:
                got += result
                logs.log(f"  ✓ Pexels videos: {query} ({result})")
        except Exception as e:
            logs.log(f"  ✗ Pexels videos {query}: {e}")

    # Pexels IMAGES (new)
    pexels_image_queries = [
        ("gym fitness training", 3),
        ("healthy diet nutrition", 3),
        ("protein meal prep", 2),
        ("gym equipment weights", 2),
        ("cardio running", 2),
        ("fitness transformation before after", 2),
        ("strength training", 2),
    ]

    for query, count in pexels_image_queries:
        try:
            result = fetch_pexels_images(query, count)
            if result > 0:
                got += result
                logs.log(f"  ✓ Pexels images: {query} ({result})")
        except Exception as e:
            logs.log(f"  ✗ Pexels images {query}: {e}")

    return got


def intelligent_download(subject_name: str, coach: str = "", ctype: str = "public figure") -> int:
    """
    Complete intelligent media sourcing:
    1. Auto-search YouTube for celebrity videos (no manual links needed)
    2. Fetch Pexels videos
    3. Fetch Pexels images
    4. Return total count
    """
    logs.log("[DOWNLOAD] Starting intelligent media sourcing...")
    logs.log(f"  Subject: {subject_name}")
    if coach:
        logs.log(f"  Coach: {coach}")
    logs.log(f"  Type: {ctype}")

    total = 0

    # 1. Auto-search YouTube
    try:
        yt_count = auto_search_youtube(subject_name, coach, ctype)
        total += yt_count
        logs.log(f"[DOWNLOAD] YouTube auto-search: {yt_count} videos")
    except Exception as e:
        logs.log(f"[DOWNLOAD] YouTube auto-search failed: {e}", "error")

    # 2. Fetch Pexels media (videos + images)
    try:
        px_count = fetch_supplementary_media(subject_name, coach)
        total += px_count
        logs.log(f"[DOWNLOAD] Pexels media: {px_count} items")
    except Exception as e:
        logs.log(f"[DOWNLOAD] Pexels fetch failed: {e}", "error")

    logs.log(f"[DOWNLOAD] TOTAL MEDIA SOURCED: {total} items")
    return total


def get_media_inventory() -> dict:
    """Get current media inventory (videos + images)."""
    videos = list(settings.ASSETS_VIDEO.glob("*.mp4")) if settings.ASSETS_VIDEO.exists() else []
    images = list(settings.ASSETS_IMAGE.glob("*.{jpg,png,webp}")) if settings.ASSETS_IMAGE.exists() else []
    pexels_videos = list(settings.ASSETS_PEXELS.glob("*.mp4")) if settings.ASSETS_PEXELS.exists() else []

    return {
        "videos": len(videos),
        "images": len(images),
        "pexels_videos": len(pexels_videos),
        "total": len(videos) + len(images) + len(pexels_videos),
    }
