"""clip_processor - Transform and fix problem clips instead of rejecting them.

Features:
- Transform vertical videos to 16:9 (stretch, crop, or pillarbox)
- Remove text overlays (crop bottom/top where captions are)
- Detect and avoid clips with too many characters/people
- Keep clips that fit but need adjustment
"""

import subprocess
from pathlib import Path
from . import settings, logs, vision


class ClipProcessor:
    """Fix and transform problematic clips instead of rejecting them."""

    def __init__(self, work_dir: Path = None):
        self.work_dir = work_dir or settings.CACHE / "_clip_processing"
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self.processed_count = 0

    def _get_video_info(self, video_path: str) -> dict:
        """Get video dimensions and duration."""
        try:
            result = subprocess.run(
                ["ffprobe", "-v", "error", "-select_streams", "v:0",
                 "-show_entries", "stream=width,height,duration",
                 "-of", "json", video_path],
                capture_output=True, text=True, timeout=10
            )
            data = __import__('json').loads(result.stdout)
            stream = data['streams'][0]
            return {
                "width": stream.get("width", 1920),
                "height": stream.get("height", 1080),
                "duration": float(stream.get("duration", 0)),
            }
        except Exception as e:
            logs.log(f"  info error: {e}")
            return {"width": 1920, "height": 1080, "duration": 0}

    def transform_vertical_video(self, video_path: str, output_path: str,
                                 strategy: str = "stretch") -> bool:
        """
        Transform vertical video to 16:9 format.

        Strategies:
        - stretch: Scale to 1920×1080 (fills screen, slight distortion)
        - crop: Center crop to 16:9 (loses top/bottom)
        - pillarbox: Black bars on sides (no distortion, smaller content)
        """
        try:
            info = self._get_video_info(video_path)
            w, h = info["width"], info["height"]

            if h / w < 0.8:  # Not vertical, don't transform
                return False

            if strategy == "stretch":
                # Scale to fill 16:9 (slight distortion acceptable for vertical content)
                vf = "scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080"
            elif strategy == "crop":
                # Center crop to 16:9 (keeps original quality, loses edges)
                new_h = int(w * 9 / 16)
                vf = f"crop=iw:{new_h}:(0):(ih-{new_h})/2,scale=1920:1080"
            else:  # pillarbox
                # Keep aspect ratio, add black bars
                vf = "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2:black"

            subprocess.run(
                ["ffmpeg", "-i", video_path, "-vf", vf, "-c:v", "libx264",
                 "-preset", "veryfast", "-c:a", "aac", "-b:a", "128k",
                 "-y", str(output_path)],
                capture_output=True, timeout=300
            )

            if output_path.exists():
                logs.log(f"  ✓ transformed vertical video (strategy: {strategy})")
                return True
            return False

        except Exception as e:
            logs.log(f"  transform error: {e}")
            return False

    def remove_text_overlay(self, video_path: str, output_path: str,
                           remove_bottom: bool = True, remove_top: bool = False) -> bool:
        """
        Remove text overlays by cropping caption areas.

        remove_bottom: Crop bottom 15% (where captions usually are)
        remove_top: Crop top 10% (where channel logos are)
        """
        try:
            info = self._get_video_info(video_path)
            h = info["height"]

            vf = "scale=1920:1080"  # Normalize first
            crop_top = int(h * 0.10) if remove_top else 0
            crop_bottom = int(h * 0.15) if remove_bottom else 0
            new_h = h - crop_top - crop_bottom

            if new_h < 400:  # Too much cropped, keep original
                return False

            vf += f",crop=iw:{new_h}:0:{crop_top}"

            subprocess.run(
                ["ffmpeg", "-i", video_path, "-vf", vf, "-c:v", "libx264",
                 "-preset", "veryfast", "-c:a", "aac", "-b:a", "128k",
                 "-y", str(output_path)],
                capture_output=True, timeout=300
            )

            if output_path.exists():
                logs.log(f"  ✓ removed text overlay (cropped {crop_top + crop_bottom}px)")
                return True
            return False

        except Exception as e:
            logs.log(f"  text removal error: {e}")
            return False

    def check_subject_isolation(self, video_path: str, celebrity_name: str) -> float:
        """
        Check how isolated the celebrity is (0-1 score).
        High = celebrity alone, Low = many people in frame

        Returns: isolation_score (0.0-1.0)
        """
        try:
            from pathlib import Path

            # Extract frame for analysis
            frame_path = self.work_dir / "_isolation_check.jpg"
            subprocess.run(
                ["ffmpeg", "-i", video_path, "-vf", "select=eq(n\\,30)",
                 "-q:v", "2", "-y", str(frame_path)],
                capture_output=True, timeout=10
            )

            if not frame_path.exists():
                return 0.5  # Unknown, neutral score

            # Gemini Vision: Count people and assess isolation
            prompt = f"""Analyze this video frame carefully.

            Questions:
            1. How many distinct people are visible in the frame?
            2. Is {celebrity_name} the only person or main focus?
            3. How much of the frame does {celebrity_name} occupy (percentage)?
            4. Rate isolation: 1=many people, 5=celebrity alone

            Answer format ONLY:
            PEOPLE_COUNT: [number]
            ISOLATION: [1-5]
            FOCUS_PERCENT: [percentage]"""

            result = vision._analyze_with_gemini(str(frame_path), prompt)
            frame_path.unlink(missing_ok=True)

            # Parse result to get isolation score
            if "ISOLATION: 5" in result or "ISOLATION:5" in result:
                return 0.9  # Celebrity alone/main focus
            elif "ISOLATION: 4" in result or "ISOLATION:4" in result:
                return 0.7  # Mostly isolated
            elif "ISOLATION: 3" in result or "ISOLATION:3" in result:
                return 0.5  # Mixed
            elif "ISOLATION: 2" in result or "ISOLATION:2" in result:
                return 0.3  # Some other people
            else:
                return 0.1  # Many people visible

        except Exception as e:
            logs.log(f"  isolation check error: {e}")
            return 0.5  # Unknown, neutral

    def process_clip(self, video_path: str, celebrity_name: str = "",
                     fix_vertical: bool = True, fix_text: bool = True) -> dict:
        """
        Process a problematic clip: transform and fix issues.

        Returns: {
            "success": bool,
            "original": str,
            "processed": str,  # If modified
            "reason": str,     # Why kept/rejected
            "isolation": float, # 0-1, higher = better
        }
        """
        result = {
            "success": False,
            "original": video_path,
            "processed": None,
            "reason": "",
            "isolation": 0.5,
        }

        info = self._get_video_info(video_path)
        w, h = info["width"], info["height"]
        is_vertical = h / w > 0.8

        # Check subject isolation
        if celebrity_name:
            result["isolation"] = self.check_subject_isolation(video_path, celebrity_name)
            if result["isolation"] < 0.3:
                result["reason"] = "too_many_people_in_frame"
                return result

        # Fix vertical video
        if is_vertical and fix_vertical:
            processed = self.work_dir / f"vertical_fixed_{Path(video_path).stem}.mp4"
            if self.transform_vertical_video(video_path, str(processed)):
                result["processed"] = str(processed)
                result["reason"] = "vertical_transformed_to_16_9"

        # Fix text overlay
        if fix_text and result["processed"]:
            detext = self.work_dir / f"text_removed_{Path(video_path).stem}.mp4"
            if self.remove_text_overlay(result["processed"], str(detext)):
                result["processed"] = str(detext)
                result["reason"] += "_and_text_removed"

        result["success"] = result["processed"] is not None or result["isolation"] >= 0.3
        return result


def process_and_fix_clips(shots: list, celebrity_name: str = "") -> list:
    """
    Process all clips: transform and fix issues instead of rejecting.

    Returns: List of clips (original or processed)
    """
    logs.log("[PROCESSOR] Starting clip transformation and fixing...")

    processor = ClipProcessor()
    processed_clips = []
    fixed_count = 0
    rejected_count = 0

    for shot in shots:
        src = shot.get("src", "")
        if not src or not Path(src).exists():
            processed_clips.append(shot)
            continue

        # Process the clip
        result = processor.process_clip(src, celebrity_name,
                                       fix_vertical=True, fix_text=True)

        if result["success"]:
            fixed_count += 1
            # Use processed version if available
            if result["processed"]:
                shot["src"] = result["processed"]
                shot["processed"] = True
                shot["fix_reason"] = result["reason"]
                logs.log(f"  ✓ FIXED: {result['reason']}")
            processed_clips.append(shot)
        else:
            rejected_count += 1
            logs.log(f"  ✗ REJECTED: {result['reason']}")

    logs.log(f"[PROCESSOR] Complete: {fixed_count} fixed, {rejected_count} rejected")
    return processed_clips
