"""selection_v2 - Intelligent clip selection using Gemini for real decision-making.

Key differences from v1:
- Gemini analyzes EVERY candidate scene deeply (not just tagging)
- Relevance scores are based on narration matching, not just category
- Aggressive filtering: rejects vertical, text overlays, low quality, non-subject
- Smart Pexels: supplements celebrity footage, doesn't replace it
- Sentence-level matching: each narration segment gets best matching scene
"""

import json
import re
from collections import defaultdict
from pathlib import Path

from . import settings, semantic, logs


class SmartSelector:
    """Intelligent clip selection engine with Gemini-powered ranking."""

    def __init__(self, shots, subject_name="", pexels_shots=None):
        """
        Args:
            shots: Video scenes/clips with metadata
            subject_name: Celebrity name (for Gemini subject verification)
            pexels_shots: Generic Pexels footage for supplementary use
        """
        self.all_shots = {s["id"]: s for s in shots}
        self.unused_celebrity = dict(self.all_shots)  # Primary pool
        self.pexels_shots = {s["id"]: s for s in (pexels_shots or [])}
        self.unused_pexels = dict(self.pexels_shots)

        self.subject_name = subject_name
        self.used_shots = []
        self.rejected_shots = []
        self.scene_used = defaultdict(int)
        self.last_used_time = {}

    def pick_for_sentence(self, sentence, max_candidates=5):
        """
        Pick the BEST clip for a specific narration sentence.

        Process:
        1. Extract what sentence is about
        2. Find candidate clips (celebrity first, then Pexels)
        3. Deep-analyze each with Gemini
        4. Rank by relevance
        5. Filter (quality, text overlay, subject presence)
        6. Return best match
        """

        # Extract sentence topic/keywords
        topic = self._extract_topic(sentence["text"])

        # Get candidates (celebrity primary, Pexels secondary)
        celebrity_candidates = self._find_candidates(
            self.unused_celebrity, topic, max_candidates
        )
        pexels_candidates = self._find_candidates(
            self.unused_pexels, topic, max_candidates // 2
        )

        # Analyze each candidate with Gemini
        scored_candidates = []

        # Analyze celebrity footage
        for shot in celebrity_candidates:
            if self._should_reject(shot):
                self.rejected_shots.append(shot["id"])
                continue

            score = self._gemini_score_shot(shot, sentence, is_celebrity=True)
            if score is not None and score["relevance"] >= 0.6:
                scored_candidates.append((shot, score, "celebrity"))

        # Analyze Pexels as supplement (lower threshold)
        if not scored_candidates:  # Only if no celebrity footage
            for shot in pexels_candidates:
                if self._should_reject(shot):
                    continue

                score = self._gemini_score_shot(shot, sentence, is_celebrity=False)
                if score is not None and score["relevance"] >= 0.5:
                    scored_candidates.append((shot, score, "pexels"))

        if not scored_candidates:
            logs.log(f"    no good clips for: {sentence['text'][:50]}")
            return None

        # Sort by relevance
        scored_candidates.sort(key=lambda x: x[1]["relevance"], reverse=True)
        best_shot, best_score, source = scored_candidates[0]

        # Log selection
        logs.log(f"    picked {source}: {best_score['action']} "
                f"(relevance: {best_score['relevance']:.2f})")

        # Mark as used
        self.used_shots.append(best_shot["id"])
        self.scene_used[best_shot["scene"]] += 1
        self.last_used_time[best_shot["id"]] = len(self.used_shots)

        # Remove from unused pool (for variety)
        if source == "celebrity" and best_shot["id"] in self.unused_celebrity:
            del self.unused_celebrity[best_shot["id"]]
        elif source == "pexels" and best_shot["id"] in self.unused_pexels:
            del self.unused_pexels[best_shot["id"]]

        return best_shot

    def _extract_topic(self, text):
        """Extract keywords about what the sentence describes."""
        keywords = set()

        # Exercise keywords
        exercises = [
            "bench press", "squat", "deadlift", "row", "pull", "curl",
            "press", "dip", "lunge", "calf", "cardio", "run", "bike",
            "stretch", "foam roll", "recovery", "gym", "train", "lift"
        ]

        # Action keywords
        actions = [
            "eating", "meal", "cook", "prepare", "diet", "nutrition",
            "interview", "talk", "speak", "compete", "perform", "show",
            "transformation", "before", "after", "progress", "physique"
        ]

        text_lower = text.lower()
        for keyword in exercises + actions:
            if keyword in text_lower:
                keywords.add(keyword)

        return keywords

    def _find_candidates(self, shot_pool, topic, max_count):
        """Find candidate clips that might match the topic."""
        candidates = []

        for shot in shot_pool.values():
            # Match by category/tags
            shot_category = shot.get("cat", "").lower()

            # Basic matching
            if any(word in shot_category for word in topic):
                candidates.append(shot)
            elif not topic:  # Generic sentences get any footage
                candidates.append(shot)

        # Return top candidates
        return candidates[:max_count]

    def _should_reject(self, shot):
        """Quick rejection check before expensive Gemini analysis."""

        # Reject vertical videos (aspect ratio check)
        if shot.get("aspect_ratio") == "vertical":
            return True

        # Reject if recently used (spacing)
        scene = shot.get("scene")
        if scene in self.scene_used and self.scene_used[scene] > 2:
            return True

        # Reject super low quality
        if shot.get("resolution", 0) < 480:
            return True

        return False

    def _gemini_score_shot(self, shot, sentence, is_celebrity=True):
        """
        Use Gemini to deeply analyze if this shot matches the sentence.

        Returns: {
            "relevance": 0.0-1.0,
            "action": "bench press",
            "subject": "rajab_butt" or "unknown",
            "quality": "HD" or "480p",
            "has_text": True/False,
            "recommendation": "select" or "reject"
        }
        """

        try:
            key = self._get_gemini_key()
            if not key:
                return None

            from google import genai
            client = genai.Client(api_key=key)

            # Get frame from shot (if video, sample middle)
            frame_path = shot.get("frame_path")
            if not frame_path or not Path(frame_path).exists():
                return self._estimate_relevance(shot, sentence)

            # Build prompt
            prompt = f"""Analyze this video frame in the context of the narration:

NARRATION: "{sentence['text']}"
SUBJECT: {self.subject_name}

Answer these questions:
1. Is {self.subject_name} the PRIMARY subject in this frame? (yes/no/unclear)
2. What action is happening? (e.g., "bench press", "eating", "interview", "none")
3. Does this frame match the narration topic? Rate 0-100 (0=wrong, 50=generic, 100=perfect match)
4. Video quality (HD/720p/480p/low)
5. Is there significant text/captions/watermarks on screen? (yes/no)
6. Should this be used? (yes/no/maybe)

Be brief. Prioritize accuracy over detail."""

            from PIL import Image

            response = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=[prompt, Image.open(frame_path)]
            )

            # Parse response
            result = self._parse_gemini_response(response.text, shot)
            return result

        except Exception as e:
            logs.log(f"  gemini error: {e}", "error")
            return self._estimate_relevance(shot, sentence)

    def _parse_gemini_response(self, text, shot):
        """Parse Gemini's analysis into a scoring dict."""
        text_lower = text.lower()

        # Extract relevance score (0-100)
        match = re.search(r"(\d+)\s*(?:/100|%)?", text)
        relevance = int(match.group(1)) / 100 if match else 0.5

        # Subject verification
        is_subject = "yes" in text_lower[:200]
        subject = self.subject_name if is_subject else "unknown"

        # Has text overlay?
        has_text = "yes" in text_lower[text_lower.find("text"):text_lower.find("text")+100] if "text" in text_lower else False

        # Quality
        quality = "HD" if "hd" in text_lower else "720p" if "720" in text_lower else "480p"

        # Extract action (first verb-like word)
        words = text.split()
        action = "unknown"
        for i, word in enumerate(words):
            if any(ex in word.lower() for ex in ["bench", "squat", "row", "eat", "interview"]):
                action = word.lower()
                break

        # Recommendation
        should_use = (
            is_subject and
            relevance >= 0.6 and
            not has_text and
            quality != "low"
        )

        return {
            "relevance": relevance if should_use else relevance * 0.5,
            "action": action,
            "subject": subject,
            "quality": quality,
            "has_text": has_text,
            "recommendation": "select" if should_use else "reject"
        }

    def _estimate_relevance(self, shot, sentence):
        """Fallback scoring when Gemini unavailable."""
        topic = self._extract_topic(sentence["text"])
        shot_cat = shot.get("cat", "").lower()

        # Basic relevance
        match_count = sum(1 for t in topic if t in shot_cat)
        relevance = min(1.0, match_count / max(1, len(topic)))

        return {
            "relevance": relevance,
            "action": shot_cat,
            "subject": "unknown",
            "quality": "unknown",
            "has_text": False,
            "recommendation": "maybe"
        }

    def _get_gemini_key(self):
        """Get Gemini API key from env or file."""
        import os
        key = os.environ.get("GEMINI_API_KEY", "").strip()
        if not key:
            kf = settings.ROOT / "gemini_key.txt"
            if kf.exists():
                key = kf.read_text(encoding="utf-8").strip()
        return key

    def refill_celebrity(self):
        """Refill celebrity pool for reuse (with spacing penalty)."""
        self.unused_celebrity = dict(self.all_shots)

    def refill_pexels(self):
        """Refill Pexels pool for reuse."""
        self.unused_pexels = dict(self.pexels_shots)

    def report(self):
        """Summary of what was selected."""
        return {
            "used": len(self.used_shots),
            "rejected": len(self.rejected_shots),
            "acceptance_rate": len(self.used_shots) / max(1, len(self.used_shots) + len(self.rejected_shots))
        }


def _get_gemini_key():
    """Helper to fetch Gemini key."""
    import os
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        kf = settings.ROOT / "gemini_key.txt"
        if kf.exists():
            key = kf.read_text(encoding="utf-8").strip()
    return key
