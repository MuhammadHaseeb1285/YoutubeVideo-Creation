"""clip_filter_enhanced - Smart filtering with corrections.

Philosophy: Fix problems instead of rejecting

Strategy:
- Vertical videos → Transform to 16:9 (don't reject)
- Text overlays → Crop them out (don't reject)
- Subject isolation → Check and prefer isolated shots
- Reaction/commentary → Still reject (can't fix)
- Low quality → Still reject (can't improve)
"""

import re
from pathlib import Path
from . import logs, vision, settings


class EnhancedClipFilter:
    """Intelligent filtering with Gemini Vision verification."""

    REJECT_KEYWORDS = [
        "reaction", "reacts", "responds to", "commentary", "analysis",
        "opinion", "discussion", "talks about", "news", "gossip",
        "rumor", "drama", "leaked", "scandal", "fan-made", "edited",
        "tribute", "compilation", "motivation", "motivational", "edit",
        "trailer", "promo", "advertisement", "fails", "funny", "cringe",
        "vs", "challenge", "dare", "prank", "review", "breakdown"
    ]

    def __init__(self, subject_name: str = ""):
        self.subject_name = subject_name
        self.rejected_count = 0
        self.rejected_reasons = {}

    def _has_text_overlay(self, shot_path: str) -> bool:
        """Use Gemini Vision to detect text overlays on screen."""
        try:
            from . import vision
            from pathlib import Path

            # Extract frame from video
            import subprocess
            frame_path = Path(shot_path).parent / "_frame_check.jpg"

            subprocess.run(
                ["ffmpeg", "-i", shot_path, "-vf", "select=eq(n\\,0)",
                 "-q:v", "2", "-y", str(frame_path)],
                capture_output=True, timeout=10
            )

            if not frame_path.exists():
                return False

            # Analyze with Gemini
            prompt = """Analyze this video frame carefully.

            Questions:
            1. Are there ANY text overlays, captions, watermarks, or subtitles visible on screen?
            2. Is there channel branding, copyright notices, or sponsor logos?
            3. Any editing artifacts or graphics overlaid on the video?

            Answer with ONLY: "YES_HAS_TEXT" or "NO_CLEAN"
            If unsure, assume YES_HAS_TEXT (reject questionable ones)."""

            result = vision._analyze_with_gemini(str(frame_path), prompt)
            frame_path.unlink(missing_ok=True)

            has_text = "YES_HAS_TEXT" in result.upper()
            return has_text

        except Exception as e:
            logs.log(f"  text detection failed: {e}, assuming clean")
            return False

    def _is_celebrity_primary(self, shot_path: str, celebrity_name: str) -> bool:
        """Verify celebrity is PRIMARY subject using Gemini Vision."""
        if not celebrity_name:
            return True  # If no name given, assume OK

        try:
            from . import vision
            from pathlib import Path
            import subprocess

            frame_path = Path(shot_path).parent / "_frame_subject.jpg"

            subprocess.run(
                ["ffmpeg", "-i", shot_path, "-vf", "select=eq(n\\,10)",
                 "-q:v", "2", "-y", str(frame_path)],
                capture_output=True, timeout=10
            )

            if not frame_path.exists():
                return True  # If can't extract, don't reject

            prompt = f"""Analyze who is the PRIMARY subject of this video frame.

            Questions:
            1. Is {celebrity_name} clearly visible and the main focus?
            2. Is {celebrity_name} doing an activity (workout, interview, etc.) or just sitting?
            3. Is this a reaction video where someone else is talking about {celebrity_name}?
            4. Is {celebrity_name} the PRIMARY subject or secondary/background?

            Answer with ONLY: "YES_PRIMARY" or "NO_NOT_PRIMARY"
            If unsure or {celebrity_name} is not clearly visible, answer "NO_NOT_PRIMARY"."""

            result = vision._analyze_with_gemini(str(frame_path), prompt)
            frame_path.unlink(missing_ok=True)

            is_primary = "YES_PRIMARY" in result.upper()
            return is_primary

        except Exception as e:
            logs.log(f"  subject verification failed: {e}, allowing anyway")
            return True  # Fallback: don't reject if Gemini fails

    def filter_shots(self, shots: list, subject_name: str = "") -> list:
        """
        Ultra-intelligent filtering with Gemini Vision verification.

        Returns list of high-quality shots only.
        Rejects:
        - Text overlays (captions, watermarks, graphics)
        - Where celebrity is not primary subject
        - Vertical/low-res/reaction videos
        - Low quality/compressed footage
        """
        filtered = []
        rejected_reasons = {}

        for shot in shots:
            reason = None
            src = shot.get("src", "")
            title = src.split("/")[-1].lower() if src else ""

            # 1. Aspect ratio check (reject vertical)
            w, h = shot.get("w", 1920), shot.get("h", 1080)
            if w < 100 or h < 100:  # Sanity check
                reason = "invalid_resolution"
            elif h / w > 0.8:  # More height than width = vertical
                reason = "vertical_video"

            # 2. Resolution check (reject < 720p)
            if not reason and (w < 1280 or h < 720):
                reason = "low_resolution"

            # 3. File size check (reject tiny files = bad quality)
            if not reason:
                size = shot.get("size", 0)
                if size < 500_000:  # Less than 500KB = probably compressed
                    reason = "compressed_or_tiny"

            # 4. Keyword rejection (reactions, commentary, etc.)
            if not reason:
                for kw in self.REJECT_KEYWORDS:
                    if kw in title:
                        reason = f"keyword_reject:{kw}"
                        break

            # 5. Gemini Vision: Check for text overlays
            if not reason and src and Path(src).exists():
                try:
                    if self._has_text_overlay(src):
                        reason = "text_overlay_detected"
                except Exception as e:
                    logs.log(f"    text check error: {e}")
                    # Don't reject on error

            # 6. Gemini Vision: Verify celebrity is primary subject
            if not reason and src and Path(src).exists() and subject_name:
                try:
                    if not self._is_celebrity_primary(src, subject_name):
                        reason = "celebrity_not_primary"
                except Exception as e:
                    logs.log(f"    subject check error: {e}")
                    # Don't reject on error

            if reason:
                self.rejected_count += 1
                rejected_reasons[reason] = rejected_reasons.get(reason, 0) + 1
                logs.log(f"  ✗ {reason:30} {title[:50]}")
            else:
                filtered.append(shot)
                logs.log(f"  ✓ PASS {title[:50]}")

        logs.log(f"\n[FILTER] {len(filtered)}/{len(shots)} shots passed (rejected {self.rejected_count})")
        for reason, count in sorted(rejected_reasons.items(), key=lambda x: -x[1]):
            logs.log(f"  - {reason}: {count}")

        return filtered


def filter_for_documentary_enhanced(shots: list, subject_name: str = "",
                                    pexels_shots: list = None) -> tuple:
    """
    Ultra-intelligent filtering.

    Returns (celebrity_filtered, pexels_filtered)
    """
    logs.log("[FILTER] Starting enhanced intelligent filtering...")

    # Filter celebrity footage aggressively
    cf = EnhancedClipFilter(subject_name)
    celebrity_filtered = cf.filter_shots(shots, subject_name)

    # Filter Pexels more leniently (it's generic)
    if pexels_shots:
        logs.log("[FILTER] Filtering Pexels footage (lenient)...")
        cf_pexels = EnhancedClipFilter()
        pexels_filtered = cf_pexels.filter_shots(pexels_shots, "")
    else:
        pexels_filtered = []

    logs.log(f"[FILTER] Final: {len(celebrity_filtered)} celebrity + "
            f"{len(pexels_filtered)} Pexels = {len(celebrity_filtered) + len(pexels_filtered)} total")

    return celebrity_filtered, pexels_filtered
