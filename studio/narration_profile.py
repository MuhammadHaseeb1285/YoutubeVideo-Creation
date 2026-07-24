"""narration_profile - decide HOW the documentary should be narrated from
WHAT it is about. Instead of a fixed voice list, the transcript is analysed
for genre, energy, pacing and tone, and that analysis chooses a narration
profile (voice + prosody). The delivery fits the film rather than being the
same for every project.

We never imitate a real person's voice - we adapt a documentary narrator's
energy, pace and emphasis to the content.
"""

import re

from . import transcript as T

# ---------------------------------------------------------- lexicons
_FITNESS = ["workout", "training", "gym", "muscle", "protein", "reps",
            "sets", "physique", "shredded", "lift", "cardio", "diet",
            "exercise", "squat", "deadlift", "bench"]
_INSPIRE = ["journey", "overcome", "transformation", "discipline", "dream",
            "comeback", "struggle", "believe", "relentless", "grind",
            "dedication", "prove"]
_INVESTIGATE = ["allegedly", "investigation", "evidence", "claims",
                "controversy", "scandal", "reportedly", "uncovered",
                "the truth", "questions"]
_HISTORY = ["century", "history", "ancient", "era", "decade", "dynasty",
            "historic", "in the year", "generations"]
_ENERGY = ["shredded", "explosive", "insane", "incredible", "crush",
           "power", "intense", "beast", "unstoppable", "elite", "extreme",
           "massive", "brutal", "savage", "hardcore", "next level"]
_WARM = [" you ", " your ", "together", "let's", "imagine", "remember",
         "we all", "your body"]
_SERIOUS = ["however", "reported", "research", "study", "evidence", "fact",
            "data", "according", "context", "estimated"]


def _freq(text, words):
    n = sum(text.count(w) for w in words)
    return n / max(1, len(text.split()) / 100)      # per 100 words


def _clamp(x):
    return max(0.0, min(1.0, x))


# ---------------------------------------------------------- profiles
# Each profile is a documentary delivery, tuned by prosody. Voices are
# generic TTS narrators (no real-person cloning). Trait scores drive the
# on-screen radar in the dashboard.
PROFILES = {
    "energetic": {
        "label": "Confident & Energetic",
        "blurb": "Punchy, high-drive delivery for training and action.",
        "voice": "en-US-GuyNeural", "rate": "+9%", "pitch": "+0Hz",
        "traits": {"energy": 0.95, "confidence": 0.9, "warmth": 0.5,
                   "pace": 0.85, "drama": 0.8, "seriousness": 0.4},
    },
    "motivational": {
        "label": "Motivational & Uplifting",
        "blurb": "Warm, rising delivery for transformation stories.",
        "voice": "en-US-BrianNeural", "rate": "+5%", "pitch": "+1Hz",
        "traits": {"energy": 0.75, "confidence": 0.8, "warmth": 0.85,
                   "pace": 0.6, "drama": 0.7, "seriousness": 0.5},
    },
    "authoritative": {
        "label": "Calm & Authoritative",
        "blurb": "Measured, credible delivery with weight and control.",
        "voice": "en-US-ChristopherNeural", "rate": "-2%", "pitch": "-2Hz",
        "traits": {"energy": 0.45, "confidence": 0.9, "warmth": 0.45,
                   "pace": 0.4, "drama": 0.5, "seriousness": 0.9},
    },
    "measured": {
        "label": "Measured & Informative",
        "blurb": "Even, unhurried delivery for history and analysis.",
        "voice": "en-GB-RyanNeural", "rate": "-5%", "pitch": "+0Hz",
        "traits": {"energy": 0.35, "confidence": 0.7, "warmth": 0.55,
                   "pace": 0.3, "drama": 0.35, "seriousness": 0.85},
    },
    "conversational": {
        "label": "Natural & Conversational",
        "blurb": "Relaxed, personable delivery that feels one-to-one.",
        "voice": "en-US-AndrewNeural", "rate": "+2%", "pitch": "+0Hz",
        "traits": {"energy": 0.6, "confidence": 0.7, "warmth": 0.9,
                   "pace": 0.55, "drama": 0.45, "seriousness": 0.4},
    },
}
DEFAULT_PROFILE = "authoritative"


def analyze(transcript_path=None, text=None) -> dict:
    """Return a tone analysis + the recommended profile key."""
    if text is None and transcript_path is not None:
        secs = T.parse_sections(transcript_path)
        text = " ".join(s for _, sents in secs for s in sents)
    text = (text or "").strip()
    low = " " + text.lower() + " "
    sents = re.split(r"(?<=[.!?])\s+", text) or [""]
    words = max(1, len(text.split()))

    genre_scores = {
        "fitness": _freq(low, _FITNESS), "inspirational": _freq(low, _INSPIRE),
        "investigative": _freq(low, _INVESTIGATE),
        "historical": _freq(low, _HISTORY),
    }
    genre = max(genre_scores, key=genre_scores.get)
    if genre_scores[genre] < 0.15:
        genre = "fitness"                       # this studio's default domain

    exclaim = low.count("!") / max(1, len(sents))
    avg_len = words / max(1, len(sents))
    energy = _clamp(_freq(low, _ENERGY) * 0.5 + exclaim * 1.5)
    warmth = _clamp(_freq(low, _WARM) * 0.4)
    seriousness = _clamp(_freq(low, _SERIOUS) * 0.5)
    pace = _clamp(1.2 - avg_len / 28.0)         # short sentences -> faster
    confidence = _clamp(0.55 + energy * 0.35 - seriousness * 0.1)
    drama = _clamp(energy * 0.7 + exclaim)

    if genre == "historical":
        key = "measured"
    elif genre == "investigative":
        key = "authoritative"
    elif genre == "inspirational":
        key = "motivational"
    elif genre == "fitness":
        key = "energetic" if energy >= 0.4 else "motivational"
    else:
        key = DEFAULT_PROFILE

    return {
        "genre": genre,
        "traits": {"energy": round(energy, 2), "confidence": round(confidence, 2),
                   "warmth": round(warmth, 2), "pace": round(pace, 2),
                   "drama": round(drama, 2), "seriousness": round(seriousness, 2)},
        "recommended": key,
        "summary": _summary(genre, key, energy),
        "profiles": {k: {"label": v["label"], "blurb": v["blurb"],
                         "voice": v["voice"], "traits": v["traits"]}
                     for k, v in PROFILES.items()},
    }


def _summary(genre, key, energy):
    g = {"fitness": "high-energy fitness documentary",
         "inspirational": "inspirational transformation story",
         "investigative": "investigative documentary",
         "historical": "historical documentary"}.get(genre, "documentary")
    return (f"Detected a {g}. Recommended a "
            f"{PROFILES[key]['label'].lower()} delivery.")


def resolve(profile_key: str, pace_adj: int = 0, energy_adj: int = 0):
    """Return (voice, rate, pitch) for a profile with optional user nudges
    (pace_adj / energy_adj are -3..+3 slider steps)."""
    p = PROFILES.get(profile_key, PROFILES[DEFAULT_PROFILE])
    base_rate = int(re.sub(r"[^\-0-9]", "", p["rate"]) or 0)
    base_pitch = int(re.sub(r"[^\-0-9]", "", p["pitch"]) or 0)
    rate = base_rate + pace_adj * 4
    pitch = base_pitch + energy_adj * 1
    return p["voice"], f"{rate:+d}%", f"{pitch:+d}Hz"


PREVIEW_TEXT = ("This is how the narration will sound. The story of a "
                "physical transformation, told with the energy the footage "
                "deserves.")
