"""clip_filter - Aggressive filtering to reject low-quality, irrelevant, or problematic clips.

Filters out:
- Vertical videos (9:16 mobile format)
- YouTube Shorts
- Clips with text overlays/captions/watermarks
- Reaction/commentary videos
- Low resolution (< 720p)
- Where celebrity is not the primary subject
- Heavily compressed or low-quality footage
"""

import re
from pathlib import Path
from . import logs


class ClipFilter:
    """Aggressive quality and relevance filtering."""

    # Reject patterns in video titles/descriptions
    REJECT_KEYWORDS = [
        "reaction", "reacts", "responds", "responds to", "reaction video",
        "commentary", "analysis", "opinion", "discussion", "talks about",
        "news", "gossip", "rumor", "drama", "leaked", "scandal",
        "fan-made", "edited by", "tribute", "compilation",
        "motivation", "motivational edits", "gym motivation",
        "edit", "trailer", "promo", "advertisement", "ad",
        "fails", "funny", "cringe", "awkward moments",
        "vs", "challenge", "dare", "prank"
    ]

    # Prefer keywords (indicates authentic content)
    PREFER_KEYWORDS = [
        "official", "interview", "behind the scenes", "bts",
        "training", "workout", "gym session", "diet", "meal prep",
        "vlog", "channel", "instagram", "tiktok", "youtube",
        "transformation", "physique", "body update", "progress"
    ]

    def __init__(self):
        self.filtered_count = 0
        self.reasons = {}

    def filter_shots(self, shots, subject_name=""):
        """
        Filter a list of shots, return only high-quality ones.

        Args:
            shots: List of shot dicts
            subject_name: Celebrity name (for relevance checking)

        Returns:
            List of filtered shots
        """
        filtered = []

        for shot in shots:
            reason = self._get_reject_reason(shot, subject_name)

            if reason:
                self.filtered_count += 1
                self.reasons[reason] = self.reasons.get(reason, 0) + 1
                continue

            filtered.append(shot)

        logs.log(f"[FILTER] {len(filtered)}/{len(shots)} shots passed quality checks")
        if self.reasons:
            for reason, count in sorted(self.reasons.items(), key=lambda x: -x[1]):
                logs.log(f"  rejected {count}: {reason}")

        return filtered

    def _get_reject_reason(self, shot, subject_name=""):
        """
        Check if shot should be rejected. Return reason if yes, None if keep.
        """

        # 1. Aspect ratio check (reject vertical videos)
        aspect = self._check_aspect_ratio(shot)
        if aspect == "vertical":
            return "vertical_video (mobile format)"
        if aspect == "short":
            return "youtube_short"

        # 2. Resolution check
        resolution = shot.get("resolution", 0)
        if resolution < 720:
            return f"low_resolution ({resolution}p)"

        # 3. Source check
        source = shot.get("source", "").lower()
        if self._is_reaction_video(source):
            return f"reaction_video ({source})"

        # 4. Title/description analysis
        title = shot.get("title", "").lower()
        description = shot.get("description", "").lower()
        if self._is_bad_content(title, description):
            return "content_type (reaction/commentary/gossip)"

        # 5. Text overlay detection
        if self._has_text_overlay(shot):
            return "text_overlay (captions/watermarks)"

        # 6. Subject presence
        if subject_name and not self._is_celebrity_primary(shot, subject_name):
            return "subject_not_primary (celebrity is background/absent)"

        # 7. Quality metrics
        if self._is_heavily_compressed(shot):
            return "heavily_compressed (low bitrate)"

        return None

    def _check_aspect_ratio(self, shot):
        """Detect video aspect ratio from metadata or estimation."""
        # From metadata
        if "aspect_ratio" in shot:
            return shot["aspect_ratio"]

        # Estimate from resolution
        width = shot.get("width", 0)
        height = shot.get("height", 0)

        if width and height:
            ratio = width / height
            if ratio < 1:  # Taller than wide
                return "vertical"
            if ratio < 1.2:  # Close to square (Shorts often 9:16)
                return "short"
            if ratio > 2:  # Ultra wide (unlikely)
                return "unusual"

        return "landscape"

    def _is_reaction_video(self, source):
        """Check if source is known reaction channel."""
        reaction_channels = [
            "reaction", "reacts", "responds", "reacted", "reaction video",
            "the comment" "comment" "commentator", "analysis channel",
        ]
        return any(pattern in source for pattern in reaction_channels)

    def _is_bad_content(self, title, description):
        """Check if title/description indicates bad content type."""
        full_text = f"{title} {description}".lower()

        # Check for reject keywords
        for keyword in self.REJECT_KEYWORDS:
            if keyword in full_text:
                return True

        # If has many prefer keywords, probably good
        prefer_count = sum(1 for k in self.PREFER_KEYWORDS if k in full_text)
        if prefer_count >= 2:
            return False

        return False

    def _has_text_overlay(self, shot):
        """Detect if shot has text overlays, captions, watermarks."""
        # From metadata if available
        if shot.get("has_text_overlay"):
            return True

        if shot.get("has_watermark"):
            return True

        if shot.get("has_captions"):
            return True

        # Check description for indicators
        description = shot.get("description", "").lower()
        if any(word in description for word in ["subtitle", "caption", "cc", "watermark", "logo"]):
            return True

        return False

    def _is_celebrity_primary(self, shot, subject_name):
        """
        Check if celebrity is the primary subject.
        Uses metadata from Gemini vision tagging if available.
        """
        # From Gemini vision tagging
        tags = shot.get("vision_tags", {})
        if tags:
            # If has celebrity-specific tag, it's primary
            if any(tag.startswith("subject_") for tag in tags):
                return True
            # If has only generic/broll tags, not primary
            if any(tag.startswith("broll_") or tag.startswith("generic_") for tag in tags):
                return False

        # Conservative: if we don't know, accept it
        # (Gemini will filter in detail during selection)
        return True

    def _is_heavily_compressed(self, shot):
        """Detect heavily compressed/low-bitrate footage."""
        bitrate = shot.get("bitrate_kbps", 0)
        if bitrate < 500:  # Very low bitrate
            return True

        # File size vs duration check
        file_size_mb = shot.get("file_size_mb", 0)
        duration_sec = shot.get("duration", 1)

        if file_size_mb and duration_sec:
            # Rough estimate: HD video ~1-3 MB per second
            expected_mb = (duration_sec / 60) * 2.0  # 2 MB per minute average
            actual_ratio = file_size_mb / expected_mb

            if actual_ratio < 0.3:  # Much smaller than expected
                return True

        return False

    def smart_filter_for_pexels(self, pexels_shots):
        """
        Special filtering for Pexels footage.
        Less strict than celebrity footage (generic is OK).
        """
        filtered = []

        for shot in pexels_shots:
            # Resolution minimum
            if shot.get("resolution", 0) < 480:
                continue

            # Aspect ratio (vertical bad for Pexels too)
            if self._check_aspect_ratio(shot) == "vertical":
                continue

            # For Pexels, generic is acceptable
            filtered.append(shot)

        return filtered


def filter_for_documentary(all_shots, subject_name="", pexels_shots=None):
    """
    Main entry point: filter all footage for documentary use.

    Returns: (celebrity_shots, pexels_shots_filtered)
    """
    f = ClipFilter()

    # Filter celebrity footage (strict)
    celebrity_filtered = f.filter_shots(all_shots, subject_name)
    logs.log(f"[QUALITY] {len(celebrity_filtered)} celebrity clips passed filters")

    # Filter Pexels footage (lenient)
    pexels_filtered = []
    if pexels_shots:
        pexels_filtered = f.smart_filter_for_pexels(pexels_shots)
        logs.log(f"[QUALITY] {len(pexels_filtered)} Pexels clips passed filters")

    return celebrity_filtered, pexels_filtered
