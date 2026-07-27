"""timeline - assemble the edit using smart sentence-level clip matching.

Key differences from v1:
- Sentence-by-sentence clip selection (not pool-based)
- Gemini-powered relevance scoring
- Aggressive filtering for quality
- Smart Pexels integration (supplement, not primary)
- Better sync between narration and visuals
"""

import json

from . import settings, logs
from .selection_v2 import SmartSelector

# Try to use enhanced filtering (with Gemini Vision verification)
# Fall back to basic filtering if enhanced unavailable
try:
    from .clip_filter_enhanced import filter_for_documentary_enhanced as filter_for_documentary
    USING_ENHANCED_FILTER = True
except ImportError:
    from .clip_filter import filter_for_documentary
    USING_ENHANCED_FILTER = False

# Try to use clip processor (for transforming problematic clips)
try:
    from .clip_processor import process_and_fix_clips
    USING_PROCESSOR = True
except ImportError:
    USING_PROCESSOR = False


def _cap(cat, max_clip):
    """Pacing by content type: interviews breathe, workouts cut fast."""
    cat_lower = (cat or "").lower()

    if any(x in cat_lower for x in ["interview", "talk", "speak"]):
        return max_clip  # 3-4 seconds

    if any(x in cat_lower for x in ["gym", "workout", "training", "press", "squat"]):
        return min(2.2, max_clip)  # 1.5-2.2 seconds (energetic)

    if any(x in cat_lower for x in ["diet", "food", "meal", "nutrition"]):
        return min(3.0, max_clip)  # 2-3 seconds (show the food)

    return min(3.0, max_clip)  # default


def build(sentences, shots, pexels_shots=None, subject_name="", progress_cb=None, max_clip=None):
    """
    Build timeline using smart sentence-level clip selection.

    Args:
        sentences: Narration sentences with timing
        shots: Video clips/scenes (celebrity footage)
        pexels_shots: Generic Pexels footage (optional, supplementary)
        subject_name: Celebrity name (for Gemini verification)
        progress_cb: Progress callback
        max_clip: Maximum clip duration

    Returns:
        List of timeline pieces (clips with timing/placement)
    """
    max_clip = float(max_clip or settings.MAX_PIECE)

    logs.log("[TIMELINE] Starting smart clip selection...")
    logs.log(f"  {len(shots)} celebrity clips, {len(pexels_shots or [])} Pexels clips")

    # 1. FILTER all footage (quality checks)
    logs.log("[TIMELINE] Filtering footage for quality...")
    celebrity_filtered, pexels_filtered = filter_for_documentary(
        shots, subject_name, pexels_shots
    )

    if not celebrity_filtered:
        logs.log("ERROR: No footage passed quality filters", "error")
        return []

    # 2. PROCESS problematic clips (transform vertical, remove text, etc.)
    if USING_PROCESSOR:
        logs.log("[TIMELINE] Processing and fixing problematic clips...")
        celebrity_filtered = process_and_fix_clips(celebrity_filtered, subject_name)
        if pexels_filtered:
            pexels_filtered = process_and_fix_clips(pexels_filtered, "")

    # 3. CREATE SMART SELECTOR
    selector = SmartSelector(celebrity_filtered, subject_name, pexels_filtered)

    # 4. BUILD TIMELINE - SENTENCE BY SENTENCE
    timeline = []
    n = len(sentences)

    for si, sent in enumerate(sentences):
        # Pick the BEST clip for this specific sentence
        shot = selector.pick_for_sentence(sent, max_candidates=5)

        if shot is None:
            # No good clip found, try to refill and retry
            selector.refill_celebrity()
            shot = selector.pick_for_sentence(sent, max_candidates=5)

            if shot is None:
                # Still nothing, skip this sentence
                logs.log(f"  [SKIP] {sent['text'][:40]}")
                continue

        # Determine clip duration based on content type
        cap = _cap(shot.get("cat", ""), max_clip)

        # Use full sentence duration (clips should match narration timing)
        duration = min(cap, shot.get("len", 3.0), sent["dur"])
        duration = max(duration, min(0.8, sent["dur"]))  # minimum 0.8s

        # Add to timeline
        timeline.append({
            "slot": len(timeline),
            "shot_id": shot["id"],
            "src": shot["src"],
            "source": shot["source"],
            "scene": shot["scene"],
            "cat": shot["cat"],
            "in": shot.get("start", 0),
            "dur": round(duration, 2),
            "at": round(sent["start"], 2),
            "stype": sent.get("type", "generic"),
            "section": sent.get("section", ""),
            "sentence_text": sent["text"],  # For debugging
            "matched": True
        })

        if progress_cb and si % 10 == 0:
            progress_cb(100 * si / max(1, n), f"{len(timeline)} clips placed")

    logs.log(f"[TIMELINE] Built timeline: {len(timeline)} clips")
    report = selector.report()
    logs.log(f"  Selection rate: {report['acceptance_rate']*100:.1f}% "
            f"({report['used']} selected, {report['rejected']} rejected)")

    settings.TIMELINE.parent.mkdir(parents=True, exist_ok=True)
    settings.TIMELINE.write_text(json.dumps(timeline, indent=0))
    return timeline
