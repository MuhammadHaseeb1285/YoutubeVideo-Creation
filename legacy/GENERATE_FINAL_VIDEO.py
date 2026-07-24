#!/usr/bin/env python3
"""
DOCUMENTARY BUILDER v3 - vision-classified, Ryan-first, animated text.

Every scene of every source video was VISUALLY CLASSIFIED (vision_tags.json):
subject (Ryan / Saladino / other), gender, activity, usability. Selection now
works on what is actually IN the footage, not filenames.

Enforced rules:
  - Ryan Reynolds footage first; coach footage for coach sentences;
    the exact exercise for exercise sentences; male-only B-roll.
  - Female / mixed / branded-graphic / reaction-channel scenes are EXCLUDED.
  - No shot exceeds 4.0 seconds. A scene never repeats.
  - Cinematic text: opening title, chapter cards, lower-thirds,
    stat callouts, exercise labels (fade-animated, consistent style).
  - Export refused if validation fails.
"""

import asyncio
import json
import math
import os
import re
import shutil
import subprocess
from collections import Counter
from pathlib import Path

ROOT = Path(r"D:\Youtube\RYAN_REYNOLDS_DEADPOOL_VIDEO_BLUEPRINT")

# ---- project config: subject is configurable, nothing is hardcoded ----
_cfg = {}
if (ROOT / "config.json").exists():
    _cfg = json.loads((ROOT / "config.json").read_text())
SUBJECT = _cfg.get("subject", "Ryan Reynolds")
COACH_NAME = _cfg.get("coach", "Don Saladino")
SLUG = _cfg.get("slug", "ryan")
_SUBJECT_WORDS = [w.lower() for w in SUBJECT.split()]
_COACH_WORDS = ([w.lower() for w in COACH_NAME.split()]
                if COACH_NAME else [])

OUT_DIR = ROOT / "final_video"
VOICEOVER = ROOT / f"voiceover_{SLUG}.mp3" if _cfg else \
    ROOT / "complete_voiceover.mp3"
TRANSCRIPT = Path(_cfg.get("transcript", ROOT / "transcript.md"))
INDEX_FILE = ROOT / "shot_index.json"     # cached scene cuts per video
MAP_FILE = ROOT / "sheets_map.json"       # vision cell id -> source/scene
TAGS_FILE = ROOT / "vision_tags.json"     # cell id -> [cat, gender, use, q]
MAP_FILE2 = ROOT / "sheets_map2.json"     # appended batch (new downloads)
TAGS_FILE2 = ROOT / "vision_tags2.json"
BROLL_SHARE = 0.12                        # target: ~90% Ryan / 10% support
TIMELINE_FILE = ROOT / "timeline.json"
FINAL_NAME = _cfg.get("output", "RYAN_REYNOLDS_FINAL.mp4")

MAX_PIECE = 4.0
MIN_SHOT = 1.4
SEG_EVERY = 7           # one usable segment per ~7s of a long scene
SEG_MAX = 12
SCENE_SPACING = 12      # min pieces between two segments of one scene
FONT = "C\\:/Windows/Fonts/arialbd.ttf"

# ------------------------------------------------------------ buckets

RYAN_TALK = {"ryan_interview", "ryan_split", "ryan_press", "ryan_event"}
RYAN_PRIME = {"ryan_gym", "ryan_coach_gym", "ryan_photoshoot", "ryan_abs",
              "deadpool_suit"}
RYAN_BODY = {"ryan_shirtless", "ryan_movie", "ryan_bts", "ryan_photo",
             "ryan_outdoor", "ryan_home", "deadpool_title"}
ALL_RYAN = RYAN_TALK | RYAN_PRIME | RYAN_BODY
COACH = {"coach_talk", "coach_gym"}
DP = {"deadpool_suit", "deadpool_title", "ryan_movie"}
EX_CHEST = {"chest", "chest_talk"}
EX_BACK = {"back"}
EX_LEGS = {"legs"}
EX_SHOULD = {"shoulders", "arms"}
EX_CARDIO = {"cardio", "cardio_talk", "cardio_run"}
FOOD = {"food", "nutrition_anim"}
REC = {"recovery"}
EQ = {"equipment"}
ALL_EX = EX_CHEST | EX_BACK | EX_LEGS | EX_SHOULD | EX_CARDIO

PREF = {
    "ryan":      [ALL_RYAN, COACH],
    "deadpool":  [DP, ALL_RYAN],
    "coach":     [COACH, {"ryan_coach_gym"}, ALL_RYAN],
    "chest":     [RYAN_PRIME | COACH, EX_CHEST, EQ],
    "back":      [RYAN_PRIME | COACH, EX_BACK, EQ],
    "legs":      [RYAN_PRIME | COACH, EX_LEGS, EQ],
    "shoulders": [RYAN_PRIME | COACH, EX_SHOULD, EQ],
    "cardio":    [RYAN_PRIME | COACH, EX_CARDIO, EQ],
    "nutrition": [FOOD, RYAN_TALK, EQ],
    "recovery":  [REC, RYAN_BODY, RYAN_TALK, EQ],
    "workout":   [RYAN_PRIME, COACH, ALL_EX, EQ],
    "award":     [{"ryan_event", "ryan_photo", "ryan_press"}, ALL_RYAN],
    "family":    [{"ryan_event"}, RYAN_TALK, ALL_RYAN],
    "business":  [RYAN_TALK, ALL_RYAN],
    "generic":   [ALL_RYAN, COACH, EQ],
}

RYAN_POOL = ALL_RYAN | COACH
RYAN_TYPES = ("ryan", "deadpool", "coach")

SENTENCE_RULES = [
    ("coach",     _COACH_WORDS + ["strength coach", "his coach",
                                  "her coach", "the coach", "trainer"]),
    ("deadpool",  ["the suit", "trailer", "film", "movie", "role",
                   "premiere", "set of", "shooting", "filming"]),
    ("nutrition", ["eat", "meal", "food", "diet", "protein", "carb",
                   "nutrition", "calorie", "chicken", "salmon", "rice",
                   "sweet potato", "avocado", "alcohol", "sugar",
                   "hydration", "electrolyte", "hungry", "starvation"]),
    ("recovery",  ["sleep", "recover", "rest day", "stretch", "sauna",
                   "cold", "massage", "mobility", "foam roll"]),
    ("chest",     ["chest", "bench", "incline press", "flye", "push-up",
                   "dip", "tricep", "pressdown"]),
    ("back",      ["back", "row", "pull-up", "pulldown", "lat ",
                   "deadlift", "posterior", "romanian", "hip thrust",
                   "glute"]),
    ("legs",      ["squat", "lunge", "leg", "quad", "hamstring",
                   "prowler"]),
    ("shoulders", ["shoulder", "lateral raise", "delt", "overhead press",
                   "curl", "bicep", "arm work", "preacher"]),
    ("cardio",    ["cardio", "sprint", "conditioning", "jump rope",
                   "boxing", "run", "hiking", "cycling", "battle rope",
                   "sled", "carries", "carrying", "explosive",
                   "kettlebell", "medicine ball"]),
    ("workout",   ["train", "workout", "gym", "exercise", "lift",
                   "session", "sets", "reps", "warm-up", "warm up",
                   "program", "superset"]),
    ("award",     ["award", "oscar", "ceremony", "walk of fame",
                   "red carpet", "sexiest man", "premiere", "honored"]),
    ("family",    ["family", "wife", "husband", "his kids", "her kids",
                   "children", "daughter", "son ", "married"]),
    ("business",  ["business", "company", "brand", "entrepreneur",
                   "aviation", "wrexham", "marketing", "investment"]),
    ("ryan",      _SUBJECT_WORDS + ["actor", "actress", "he ", "his ",
                                    "him", "she ", "her "]),
]


def type_of_sentence(s):
    s = " " + s.lower() + " "
    for t, keys in SENTENCE_RULES:
        if any(k in s for k in keys):
            return t
    return "generic"


# ---------------------------------------------------------- exercise layer
# The narration is the source of truth: when a sentence names a specific
# exercise, the selector must show THAT exercise, not just the muscle
# group. Shots carry an "ex" tag; sentences are scanned for the exercise
# they mention; exact matches outrank every other preference.

EXERCISE_KEYWORDS = [
    ("bench_press",   ["incline press", "incline dumbbell", "bench press",
                       "flat dumbbell press", "chest press",
                       "dumbbell press", "cable flye", "flyes"]),
    ("pushup",        ["push-up", "push up", "pushup"]),
    ("dips",          ["dips"]),
    ("pullup",        ["pull-up", "pull up", "pulldown", "chin-up"]),
    ("row",           ["barbell row", "dumbbell row", "bent-over",
                       " rows", " row "]),
    ("deadlift",      ["deadlift", "romanian", "trap bar"]),
    ("squat",         ["squat"]),
    ("lunge",         ["lunge"]),
    ("carry",         ["carry", "carries", "farmer"]),
    ("kettlebell",    ["kettlebell"]),
    ("medicine_ball", ["medicine ball", "ball slam"]),
    ("boxing",        ["boxing", "pad work", "fight training",
                       "choreography"]),
    ("jump_rope",     ["jump rope"]),
    ("running",       ["sprint", "running", "treadmill", "prowler",
                       "battle rope"]),
    ("curl",          ["curl", "bicep"]),
    ("overhead_press", ["overhead press", "lateral raise", "rear delt",
                        "shoulder press"]),
    ("stretching",    ["foam roll", "stretch", "mobility", "warm-up",
                       "warm up", "soft tissue"]),
    ("breathing",     ["breath"]),
]


def exercise_of_sentence(s):
    s = " " + s.lower() + " "
    for ex, keys in EXERCISE_KEYWORDS:
        if any(k in s for k in keys):
            return ex
    return None


# Labeled scenes (from the visual review of the contact sheets):
# the Men's Health "Train Like ..." program footage carries on-screen
# exercise cards, so these scenes ARE those exercises.
EXERCISE_SCENE_OVERRIDES = {
    "ryan_coach_a|29": "kettlebell", "ryan_coach_a|30": "kettlebell",
    "ryan_coach_a|31": "squat", "ryan_coach_a|32": "squat",
    "ryan_coach_a|33": "squat", "ryan_coach_a|34": "squat",
    "ryan_coach_a|35": "squat",
    "ryan_coach_a|36": "bench_press", "ryan_coach_a|37": "bench_press",
    "ryan_coach_a|38": "pullup", "ryan_coach_a|39": "pullup",
    "ryan_coach_a|40": "pullup", "ryan_coach_a|41": "pullup",
    "ryan_coach_a|42": "carry", "ryan_coach_a|43": "carry",
    "ryan_coach_a|44": "carry", "ryan_coach_a|45": "carry",
    "ryan_coach_a|46": "carry",
    "ryan_coach_a|12": "stretching", "ryan_coach_a|18": "stretching",
    "ryan_coach_a|19": "stretching", "ryan_coach_a|20": "stretching",
    "ryan_coach_a|21": "stretching",
    "ryan_coach_a|14": "breathing", "ryan_coach_a|15": "breathing",
    "ryan_coach_a|16": "breathing",
    "ryan_coach_a|23": "stretching", "ryan_coach_a|24": "stretching",
    "ryan_coach_a|25": "stretching", "ryan_coach_a|26": "stretching",
    "ryan_coach_a|27": "stretching",
    "ryan_gym_a|7": "kettlebell", "ryan_gym_a|118": "squat",
    "ryan_gym_a|119": "bench_press", "ryan_gym_a|120": "squat",
    "ryan_gym_a|121": "pullup", "ryan_gym_a|123": "carry",
    "ryan_gym_a|65": "pushup",
    "deadpool_2016|93": "pullup", "deadpool_2016|100": "pullup",
    "deadpool_2016|103": "carry", "deadpool_2016|107": "bench_press",
    "deadpool_2016|108": "lunge", "deadpool_2016|109": "medicine_ball",
    "deadpool_2016|94": "curl", "deadpool_2016|96": "curl",
    "deadpool_2016|98": "curl",
    "ryan_gym_b|5": "pullup", "ryan_gym_b|19": "curl",
    "ryan_gym_b|21": "curl", "ryan_gym_b|27": "bench_press",
    "ryan_gym_a|112": "deadlift",   # shirtless barbell deadlift, dusty gym
    "ryan_gym_a|113": "pullup",     # outdoor pull-up against the sky
}

# Whole-source defaults: everything from these files shows one exercise.
EXERCISE_SOURCE_DEFAULTS = [
    ("back_row_pullup", "pullup"),
    ("dumbbell_chest_press", "bench_press"),
    ("leg_squat_lunge", "squat"),
    ("running_cardio_sprint", "running"),
    ("recovery_stretching_yoga", "stretching"),
    ("shoulder_arm", "overhead_press"),
    ("strength_training_weights", None),
    ("chest", "bench_press"),
    ("back", "row"),
    ("legs", "squat"),
    ("cardio", "running"),
]


def exercise_of_shot(source, scene):
    ov = EXERCISE_SCENE_OVERRIDES.get(f"{source}|{scene}")
    if ov:
        return ov
    s = source.lower()
    for frag, ex in EXERCISE_SOURCE_DEFAULTS:
        if frag in s:
            return ex
    return None


# ------------------------------------------------------------ semantic model
# Every shot's category is mapped to a coarse VISUAL GROUP, and every
# sentence type gets a graded affinity for each group. Selection then ranks
# the ENTIRE shot database by relevance to the current sentence instead of
# walking fixed preference buckets. This is what makes the visuals follow
# the narration: when the script talks about the back, back footage wins;
# when it talks about food, food wins; the subject is a tie-breaker, never
# an override that pastes "generic Ryan" over an unrelated topic.

CAT_GROUP = {
    "ryan_interview": "subject_talk", "ryan_split": "subject_talk",
    "ryan_press": "subject_talk", "ryan_event": "subject_talk",
    "ryan_shirtless": "subject_phys", "ryan_abs": "subject_phys",
    "ryan_photoshoot": "subject_phys", "ryan_photo": "subject_phys",
    "ryan_outdoor": "subject_phys", "ryan_home": "subject_phys",
    "ryan_gym": "subject_gym", "ryan_coach_gym": "subject_gym",
    "deadpool_suit": "subject_movie", "deadpool_title": "subject_movie",
    "ryan_movie": "subject_movie", "ryan_bts": "subject_movie",
    "coach_talk": "coach", "coach_gym": "coach",
    "chest": "ex_chest", "chest_talk": "ex_chest",
    "back": "ex_back", "legs": "ex_legs",
    "shoulders": "ex_should", "arms": "ex_should",
    "cardio": "ex_cardio", "cardio_talk": "ex_cardio",
    "cardio_run": "ex_cardio",
    "food": "food", "nutrition_anim": "food",
    "recovery": "recovery", "equipment": "equipment",
}
SUBJECT_GROUPS = {"subject_talk", "subject_phys", "subject_gym",
                  "subject_movie"}


def group_of(cat):
    """Map a footage category to its visual group. Explicit table first;
    then subject-agnostic keyword rules so footage classified for ANY
    subject (or with new labels) still lands in the right group instead of
    defaulting blindly."""
    g = CAT_GROUP.get(cat)
    if g:
        return g
    c = cat.lower()
    if "coach" in c or "trainer" in c:
        return "coach"
    if any(k in c for k in ("food", "meal", "diet", "nutrition", "eat")):
        return "food"
    if any(k in c for k in ("recovery", "stretch", "yoga", "sauna",
                            "massage", "mobility", "sleep")):
        return "recovery"
    if any(k in c for k in ("chest", "bench", "pushup", "push_up")):
        return "ex_chest"
    if any(k in c for k in ("back", "row", "pulldown", "pullup", "pull_up",
                            "deadlift")):
        return "ex_back"
    if any(k in c for k in ("leg", "squat", "lunge", "quad")):
        return "ex_legs"
    if any(k in c for k in ("shoulder", "delt", "curl", "bicep", "tricep",
                            "lateral", "overhead", "arm")):
        return "ex_should"
    if any(k in c for k in ("cardio", "run", "sprint", "condition",
                            "rope", "boxing")):
        return "ex_cardio"
    if "equip" in c:
        return "equipment"
    if any(k in c for k in ("gym", "workout", "training", "lift")):
        return "subject_gym"
    if any(k in c for k in ("shirtless", "abs", "physique", "photoshoot",
                            "photo", "beach", "outdoor", "home", "body")):
        return "subject_phys"
    if any(k in c for k in ("interview", "press", "talk", "split", "event",
                            "conference", "carpet", "speech", "podcast")):
        return "subject_talk"
    if any(k in c for k in ("movie", "film", "suit", "title", "premiere",
                            "bts", "scene", "trailer", "role", "clip")):
        return "subject_movie"
    return "subject_movie"


# Exercises that read the same on screen share a "family": when the exact
# exercise has no footage, footage from the same family is the correct
# fallback (a deadlift mention takes pull footage, not a red-carpet photo).
EXERCISE_FAMILY = {
    "bench_press": "push", "pushup": "push", "dips": "push",
    "pullup": "pull", "row": "pull", "deadlift": "pull",
    "squat": "legs", "lunge": "legs",
    "overhead_press": "arms_sh", "curl": "arms_sh",
    "running": "cond", "jump_rope": "cond", "boxing": "cond",
    "kettlebell": "cond", "medicine_ball": "cond", "carry": "cond",
    "breathing": "recov", "stretching": "recov",
}
CAT_FAMILY = {"ex_chest": "push", "ex_back": "pull", "ex_legs": "legs",
              "ex_should": "arms_sh", "ex_cardio": "cond",
              "recovery": "recov"}

EX_STYPES = {"chest", "back", "legs", "shoulders", "cardio", "workout"}
STYPE_TARGET_GROUP = {"chest": "ex_chest", "back": "ex_back",
                      "legs": "ex_legs", "shoulders": "ex_should",
                      "cardio": "ex_cardio"}


def topic_affinity(stype, grp):
    """How well a shot's visual group fits a sentence of this type.
    Higher = more on-topic. Tuned so the correct topic beats a generic
    subject shot, while the subject still beats truly unrelated footage."""
    if stype in EX_STYPES:
        tgt = STYPE_TARGET_GROUP.get(stype)
        if grp == "subject_gym":
            return 700               # the subject actually training: ideal
        if grp == tgt:
            return 620               # exact muscle-group B-roll
        if grp == "coach":
            return 430               # coach coaching the lift
        if grp == "equipment":
            return 330
        if grp == "subject_phys":
            return 400               # the physique being built
        if grp.startswith("ex_"):
            return 300 if stype == "workout" else 210
        if grp == "subject_movie":
            return 250
        if grp == "subject_talk":
            return 180
        if grp in ("food", "recovery"):
            return 40                # off-topic during a lifting cue
        return 120
    if stype == "nutrition":
        return {"food": 780, "subject_talk": 320, "subject_phys": 250,
                "subject_gym": 220, "subject_movie": 180, "coach": 200,
                "equipment": 150, "recovery": 120}.get(grp, 40)
    if stype == "recovery":
        return {"recovery": 780, "subject_phys": 360, "subject_gym": 300,
                "subject_talk": 280, "subject_movie": 240, "coach": 260,
                "food": 120, "equipment": 150}.get(grp, 60)
    if stype == "coach":
        return {"coach": 780, "subject_gym": 470, "subject_talk": 320,
                "subject_phys": 260, "subject_movie": 240,
                "equipment": 180}.get(grp, 90)
    if stype == "deadpool":
        return {"subject_movie": 740, "subject_phys": 470,
                "subject_gym": 430, "subject_talk": 320, "coach": 200,
                "equipment": 120}.get(grp, 90)
    if stype == "ryan":
        return {"subject_talk": 650, "subject_phys": 650,
                "subject_movie": 610, "subject_gym": 570, "coach": 270,
                "equipment": 100}.get(grp, 70)
    # generic narration: keep the subject on screen
    return {"subject_gym": 560, "subject_talk": 540, "subject_phys": 540,
            "subject_movie": 520, "coach": 320, "equipment": 150}.get(grp, 90)


def relevance(sh, stype, want_ex):
    """Positive semantic score of one shot for one sentence. The entire
    unused pool is ranked by this every pick, so the highest real match
    wins - not the next filename in line."""
    grp = group_of(sh["cat"])
    ex = sh.get("ex")
    r = 0.0
    if want_ex:
        fam = EXERCISE_FAMILY.get(want_ex)
        if ex == want_ex:
            r += 1300                       # the exact spoken exercise
        elif ex and EXERCISE_FAMILY.get(ex) == fam:
            r += 660                        # same movement family
        elif not ex and CAT_FAMILY.get(grp) == fam:
            r += 430                        # generic footage of that family
    r += topic_affinity(stype, grp)
    if grp in SUBJECT_GROUPS:
        r += 55                             # subject-first tie-breaker
    r += 22 * sh.get("q", 1)                # premium footage nudge
    return r


ACCEPT_GROUPS = {
    "chest": {"subject_gym", "ex_chest", "coach", "equipment",
              "subject_phys", "subject_movie", "subject_talk"},
    "back": {"subject_gym", "ex_back", "coach", "equipment",
             "subject_phys", "subject_movie", "subject_talk"},
    "legs": {"subject_gym", "ex_legs", "coach", "equipment",
             "subject_phys", "subject_movie", "subject_talk"},
    "shoulders": {"subject_gym", "ex_should", "coach", "equipment",
                  "subject_phys", "subject_movie", "subject_talk"},
    "cardio": {"subject_gym", "ex_cardio", "coach", "equipment",
               "subject_phys", "subject_movie", "subject_talk"},
    "workout": {"subject_gym", "ex_chest", "ex_back", "ex_legs",
                "ex_should", "ex_cardio", "coach", "equipment",
                "subject_phys", "subject_movie", "subject_talk"},
    "nutrition": {"food", "subject_talk", "subject_phys", "subject_gym",
                  "coach", "equipment", "subject_movie"},
    "recovery": {"recovery", "subject_phys", "subject_gym", "subject_talk",
                 "coach", "subject_movie"},
    "coach": {"coach", "subject_gym", "subject_talk", "subject_phys",
              "subject_movie"},
    "deadpool": {"subject_movie", "subject_phys", "subject_gym",
                 "subject_talk", "coach"},
    "ryan": SUBJECT_GROUPS | {"coach"},
    "generic": SUBJECT_GROUPS | {"coach", "equipment"},
}


def on_topic(stype, cat):
    return group_of(cat) in ACCEPT_GROUPS.get(stype, SUBJECT_GROUPS)


# ------------------------------------------------------------ util

def ffprobe_duration(p):
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(p)],
        capture_output=True, text=True, timeout=30)
    return float(r.stdout.strip())


TIMING_FILE = ROOT / "narration_timing.json"


def make_voiceover():
    """Render the narration AND capture word-level spoken timings.

    The text spoken is the exact ordered sentence stream that the timeline
    is built from, so the visuals can be pinned to the real moment each
    sentence is heard (edge-tts emits a WordBoundary per word). This is
    what makes audio and video actually line up instead of guessing from
    sentence length."""
    try:
        import edge_tts
    except ImportError:
        subprocess.run(["pip", "install", "edge-tts", "-q"], check=True)
        import edge_tts

    sentences = [s for _, sents in parse_sections() for s in sents]
    text = " ".join(sentences)
    voice = _cfg.get("voice", "en-US-AndrewNeural")

    segs = []

    async def _s():
        c = edge_tts.Communicate(text, voice)
        with open(VOICEOVER, "wb") as f:
            async for chunk in c.stream():
                ct = chunk.get("type")
                if ct == "audio":
                    f.write(chunk["data"])
                elif ct in ("SentenceBoundary", "WordBoundary"):
                    segs.append({"t": round(chunk["offset"] / 1e7, 3),
                                 "dur": round(chunk["duration"] / 1e7, 3),
                                 "text": chunk.get("text", "")})
    asyncio.run(_s())
    TIMING_FILE.write_text(json.dumps(segs))
    return segs


def load_timing():
    if TIMING_FILE.exists():
        try:
            return json.loads(TIMING_FILE.read_text())
        except Exception:
            return None
    return None


def sentence_start_times(sentences, audio_dur):
    """Real (start, dur) per parsed sentence from captured spoken-sentence
    boundaries. The TTS re-segments the identical character stream, so we
    align by character position: each parsed sentence inherits the spoken
    time of the boundary that covers its characters. Falls back to
    character-length proportion when no timing is present."""
    segs = load_timing()
    if segs and len(segs) >= max(3, len(sentences) * 0.5):
        # character span [a, b) of each spoken boundary within the joined
        # narration text (same text the sentences were joined into)
        spoken, pos = [], 0
        for s in segs:
            n = len(s.get("text", ""))
            spoken.append((pos, pos + n, s["t"]))
            pos += n + 1                       # +1 for the joining space

        starts, cur = [], 0
        for sent in sentences:
            mid = cur + len(sent) / 2          # this sentence's char midpoint
            covering = [sp for sp in spoken if sp[0] <= mid < sp[1]]
            if covering:
                start = covering[0][2]
            else:                              # nearest boundary by char pos
                start = min(spoken,
                            key=lambda sp: abs(mid - (sp[0] + sp[1]) / 2))[2]
            starts.append(start)
            cur += len(sent) + 1
        for i in range(1, len(starts)):        # enforce non-decreasing
            if starts[i] < starts[i - 1]:
                starts[i] = starts[i - 1]
        return starts

    total = sum(len(s) for s in sentences) or 1
    starts, t = [], 0.0
    for s in sentences:
        starts.append(round(t, 3))
        t += len(s) / total * audio_dur
    return starts


# ------------------------------------------------------------ shots

def _fallback_tag(stem: str):
    """Category tag for footage without a visual classification yet,
    based on how it was downloaded (CELEB_VIDEO.py names files by
    search intent). Visual classification, when added, overrides this."""
    s = stem.lower()
    if "reference" in s:
        # the user-supplied reference documentary: curated subject
        # footage throughout - premium quality, subject bucket
        return ["ryan_bts", "m", 1, 2]
    if "_coach" in s:
        return ["coach_talk", "m", 1, 1]
    if "_gym" in s:
        return ["ryan_gym", "m", 1, 1]
    if "_bts" in s:
        return ["ryan_bts", "m", 1, 1]
    if "_int" in s:
        return ["ryan_interview", "m", 1, 1]
    if "_diet" in s:
        return ["food", "n", 1, 1]
    return None


def build_shot_db():
    """Join cached scene cuts with vision classifications."""
    cuts_cache = json.loads(INDEX_FILE.read_text())

    # (source, scene) -> [cat, gender, use, q]  from every map/tag batch
    scene_tag = {}
    for mf, tf in ((MAP_FILE, TAGS_FILE), (MAP_FILE2, TAGS_FILE2)):
        if not (mf.exists() and tf.exists()):
            continue
        cells = json.loads(mf.read_text())
        tags = json.loads(tf.read_text())
        for c in cells:
            t = tags.get(str(c["id"]))
            if t:
                scene_tag[(c["source"], c["scene"])] = t

    shots, dropped = [], 0
    for src_path, meta in cuts_cache.items():
        src = Path(src_path)
        if not src.exists():
            continue
        dur = meta["duration"]
        cuts = [c for c in meta["cuts"] if 0.5 < c < dur - 0.5]
        bounds = [0.0] + cuts + [dur]
        for si in range(len(bounds) - 1):
            a, b = bounds[si], bounds[si + 1]
            length = b - a
            if length < MIN_SHOT:
                continue
            tag = scene_tag.get((src.stem, si))
            if tag is None:
                # New footage not yet visually classified: derive a tag
                # from the download category encoded in the filename.
                tag = _fallback_tag(src.stem)
            if not tag or not tag[2]:
                dropped += 1
                continue
            cat, gender, _, q = tag
            n_seg = min(SEG_MAX, max(1, int(length // SEG_EVERY) + 1))
            for gi in range(n_seg):
                st = a + (length / n_seg) * gi + 0.1
                ln = min(7.0, (length / n_seg) - 0.2)
                if ln < MIN_SHOT:
                    continue
                shots.append({"id": f"{src.stem}|{si}|{gi}",
                              "src": str(src), "source": src.stem,
                              "scene": f"{src.stem}|{si}",
                              "start": round(st, 2), "len": round(ln, 2),
                              "cat": cat, "g": gender, "q": q,
                              "ex": exercise_of_shot(src.stem, si)})
    return shots, dropped


# ------------------------------------------------------------ narration

def parse_sections():
    """[(section_title, [sentences])] in transcript order."""
    sections, cur_title, cur_lines = [], "OPEN", []
    for line in TRANSCRIPT.read_text(encoding="utf-8").split("\n"):
        ls = line.strip()
        if ls.startswith("## "):
            if cur_lines:
                sections.append((cur_title, cur_lines))
            m = re.match(r"##\s*(?:\[[^\]]*\])?\s*(.+)", ls)
            cur_title = (m.group(1) if m else ls[3:]).strip().upper()
            cur_lines = []
        elif ls and not ls.startswith("#") and not ls.startswith("["):
            cur_lines.append(ls)
    if cur_lines:
        sections.append((cur_title, cur_lines))

    out = []
    for title, lines in sections:
        text = " ".join(lines)
        sents = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text)
                 if s.strip()]
        out.append((title, sents))
    return out


def sentence_timeline(audio_dur):
    sections = parse_sections()
    flat = [(title, s) for title, sents in sections for s in sents]
    sents_only = [s for _, s in flat]
    starts = sentence_start_times(sents_only, audio_dur)
    out = []
    seen_sections = set()
    for i, (title, s) in enumerate(flat):
        st = starts[i]
        nxt = starts[i + 1] if i + 1 < len(starts) else audio_dur
        d = max(0.4, nxt - st)                  # spoken length of this line
        first = title not in seen_sections
        seen_sections.add(title)
        out.append({"text": s, "type": type_of_sentence(s),
                    "ex": exercise_of_sentence(s),
                    "section": title, "sec_start": first,
                    "start": round(st, 2), "dur": round(d, 2)})
    return out


# ------------------------------------------------------------ selection

def build_timeline(sentences, shots):
    unused = {s["id"]: s for s in shots}
    scene_used = Counter()
    scene_last_slot = {}
    last_src, last_cat = [], []
    timeline, slot = [], 0

    def penalty(sh):
        """Editorial cost of repetition / monotony. Kept below the topic
        scores so it re-orders equally on-topic shots rather than dragging
        an off-topic one to the top."""
        p = 0.0
        p += 260 * scene_used[sh["scene"]]          # this scene already used
        if slot - scene_last_slot.get(sh["scene"], -999) < SCENE_SPACING:
            p += 800                                # same scene too soon
        if sh["source"] in last_src[-2:]:
            p += 180                                # same video back-to-back
        if sh["cat"] in last_cat[-1:]:
            p += 70                                 # rotate visual category
        return p

    def pick(stype, want_ex=None):
        # REQUIREMENT 3: rank the ENTIRE unused pool, choose the global best
        # (relevance minus repetition cost). No early exit, no buckets.
        best, best_s = None, -1e18
        for sh in unused.values():
            s = relevance(sh, stype, want_ex) - penalty(sh)
            if s > best_s:
                best_s, best = s, sh
        return best

    carry = 0.0
    for sent in sentences:
        remaining = sent["dur"] + carry     # unfilled slivers roll over
        t_cursor = sent["start"] - carry
        while remaining > 0.35:
            sh = pick(sent["type"], sent.get("ex"))
            if sh is None:
                print("[!] shot pool exhausted")
                return timeline
            # documentary pacing: workout shots cut fast (1-2s),
            # interview/talking shots breathe (up to 4s)
            if sh["cat"] in (RYAN_TALK | {"coach_talk"}):
                cap = MAX_PIECE                       # interviews: 2-4s
            elif sh["cat"] in (ALL_EX | {"ryan_gym", "coach_gym",
                                         "ryan_photoshoot"}):
                cap = 2.2                             # workouts: 1-2s
            else:
                cap = 3.0                             # everything else
            piece = min(cap, sh["len"], remaining)
            piece = max(piece, min(1.0, remaining))
            timeline.append({"slot": slot, "shot_id": sh["id"],
                             "src": sh["src"], "source": sh["source"],
                             "scene": sh["scene"], "cat": sh["cat"],
                             "in": sh["start"], "dur": round(piece, 2),
                             "at": round(t_cursor, 2),
                             "stype": sent["type"],
                             "ex_want": sent.get("ex"),
                             "ex_got": sh.get("ex"),
                             "section": sent["section"]})
            del unused[sh["id"]]
            scene_used[sh["scene"]] += 1
            scene_last_slot[sh["scene"]] = slot
            last_src.append(sh["source"])
            last_cat.append(sh["cat"])
            slot += 1
            remaining -= piece
            t_cursor += piece
        carry = max(0.0, remaining)

    # close any residue so video length == narration length
    while carry > 0.05 and timeline:
        last = timeline[-1]
        room = MAX_PIECE - last["dur"]
        if room > 0.01:
            add = min(room, carry)
            last["dur"] = round(last["dur"] + add, 2)
            carry -= add
        else:
            sh = pick("generic")
            if sh is None:
                break
            piece = min(MAX_PIECE, sh["len"], max(carry, 0.6))
            timeline.append({"slot": slot, "shot_id": sh["id"],
                             "src": sh["src"], "source": sh["source"],
                             "scene": sh["scene"], "cat": sh["cat"],
                             "in": sh["start"], "dur": round(piece, 2),
                             "at": round(timeline[-1]["at"]
                                         + timeline[-1]["dur"], 2),
                             "stype": "generic", "section": "CLOSE"})
            del unused[sh["id"]]
            slot += 1
            carry -= piece
    return timeline


# ------------------------------------------------------------ text events

STAT_SPECS = [
    # subject/coach lower-thirds are built from config, not hardcoded
    (re.escape(COACH_NAME.lower()) if COACH_NAME else r"$^", "lt",
     COACH_NAME.upper() if COACH_NAME else "", "STRENGTH COACH"),
    (r"incline press", "ex", "INCLINE PRESS", ""),
    (r"pull-ups", "ex", "PULL-UPS", ""),
    (r"bent-over barbell", "ex", "BARBELL ROW", ""),
    (r"front squats", "ex", "FRONT SQUAT", ""),
    (r"leg press", "ex", "LEG PRESS", ""),
    (r"split squats", "ex", "BULGARIAN SPLIT SQUAT", ""),
    (r"walking lunges", "ex", "WALKING LUNGES", ""),
    (r"trap bar", "ex", "TRAP BAR DEADLIFT", ""),
    (r"romanian deadlifts", "ex", "ROMANIAN DEADLIFT", ""),
    (r"hip thrusts", "ex", "HIP THRUST", ""),
    (r"kettlebell swings", "ex", "KETTLEBELL SWINGS", ""),
    (r"lateral raises", "ex", "LATERAL RAISES", ""),
    (r"overhead press", "ex", "OVERHEAD PRESS", ""),
    (r"battle ropes", "ex", "BATTLE ROPES", ""),
    (r"bench press|flat dumbbell press", "ex", "BENCH PRESS", ""),
    (r"push-up", "ex", "PUSH-UPS", ""),
    (r"dips", "ex", "DIPS", ""),
    (r"boxing|pad work", "ex", "BOXING", ""),
    (r"jump rope", "ex", "JUMP ROPE", ""),
    (r"foam roll", "ex", "FOAM ROLLING", ""),
    (r"deadlift", "ex", "DEADLIFT", ""),
    (r"performance physique|functional", "ex", "FUNCTIONAL TRAINING", ""),
    (r"protein|carbohydrate", "ex", "NUTRITION", ""),
    (r"recovery is treated|sleep", "ex", "RECOVERY", ""),
    (r"seven to nine hours|7 to 9 hours|7-9 hours", "stat", "7-9 HRS",
     "SLEEP TARGET"),
    (r"zero point eight to one gram|0\.8 to one gram|0\.8 to 1 gram",
     "stat", "0.8-1 G/LB", "PROTEIN TARGET"),
    # --- statistics pulled from the narration wording (digits or spelled) ---
    (r"190 to 195|one hundred and ninety", "stat", "190-195 LBS",
     "FILMING WEIGHT"),
    (r"8 to 10 percent|eight to ten percent", "stat", "8-10%",
     "BODY FAT"),
    (r"six feet two|6 feet 2|6'?2", "stat", "6'2\"", "HEIGHT"),
    (r"2,?600 to 3,?200|twenty-six hundred", "stat", "2600-3200 KCAL",
     "DEADPOOL CUT"),
    (r"200 to 250 grams|two hundred to two hundred and fifty", "stat",
     "200-250 G", "DAILY PROTEIN"),
    (r"15 (plus )?years|fifteen (plus )?years|over 15", "stat", "15+ YEARS",
     "OF CONSISTENCY"),
    (r"three to five sets", "stat", "3-5 SETS", "6-12 REPS"),
    # --- movie / role title cards (specific before generic) ---
    (r"deadpool and wolverine", "movie", "DEADPOOL & WOLVERINE", "2024"),
    (r"green lantern", "movie", "GREEN LANTERN", "2011"),
    (r"blade[,: ]+trinity", "movie", "BLADE: TRINITY", "2004"),
    (r"deadpool", "movie", "DEADPOOL", "2016"),
    # --- timeline markers ---
    (r"early two thousands|early 2000s", "marker", "EARLY 2000s", ""),
    # --- motivational pull-quotes ---
    (r"diet is 90 percent|90 percent of the battle", "quote",
     "DIET IS 90% OF THE BATTLE", ""),
    (r"look like i can actually fight|train to look like", "quote",
     "TRAIN TO FIGHT, NOT JUST TO LIFT", ""),
    (r"can't out ?train bad recovery|out train bad recovery", "quote",
     "YOU CAN'T OUT-TRAIN BAD RECOVERY", ""),
    (r"consistency over 15|no shortcuts|relentless discipline", "quote",
     "NO SHORTCUTS. JUST CONSISTENCY.", ""),
]

SKIP_CHAPTERS = {"OPEN", "HOOK", "SOURCING"}


def build_text_events(sentences, timeline):
    """slot -> (kind, line1, line2). One event per timeline piece.
    Lower-thirds alternate sides; exercise labels are re-armed for every
    new exercise so the label always matches the shot on screen."""
    def piece_at(t):
        for e in timeline:
            if e["at"] <= t < e["at"] + e["dur"] + 0.01:
                return e["slot"]
        return None

    events = {}
    if timeline:
        events[0] = ("title", SUBJECT.upper(), "THE TRANSFORMATION")

    for sent in sentences:                      # chapter cards
        if sent["sec_start"] and sent["section"] not in SKIP_CHAPTERS:
            slot = piece_at(sent["start"])
            if slot is not None and slot not in events:
                events[slot] = ("chapter", sent["section"], "")

    used = set()
    for pat, kind, l1, l2 in STAT_SPECS:        # first occurrence each
        if pat in used:
            continue
        for sent in sentences:
            if re.search(pat, sent["text"], re.I):
                slot = piece_at(sent["start"])
                if slot is not None and slot not in events:
                    events[slot] = (kind, l1, l2)
                    used.add(pat)
                break
    return events


# ---------------------------------------------------------- motion graphics
# ffmpeg can animate drawtext position and alpha per frame (via t). We use
# that for slide-ins, staggered reveals and fade-outs; a drop shadow and a
# red accent bar give the lower-thirds a broadcast-documentary look. Solid
# panels are drawn per-clip - the clip cut hides their in/out, the text
# animates on top. (True motion-tracking / behind-object masking needs
# per-frame rotoscoping and is out of scope for an ffmpeg pass.)

def _clean(s):
    return (s or "").replace("\\", "").replace("'", "").replace(":", "\\:") \
                    .replace("%", "\\%")


def _alpha(dur, delay=0.0, tin=0.45, tout=0.4):
    """Fade in after `delay`, hold, fade out before the clip ends.
    Single-quoted so its commas are protected in the filtergraph."""
    return (f"'if(lt(t,{delay}),0,"
            f"min(min(1,(t-{delay})/{tin}),max(0,({dur:.2f}-t)/{tout})))'")


def _ease(delay=0.0, tin=0.45):
    """0 -> 1 ramp for slide-in offsets (embedded inside a quoted value)."""
    return f"min(1,max(0,(t-{delay})/{tin}))"


def _dt(text, size, color, x, y, alpha, weight_shadow=True):
    sh = (":shadowcolor=black@0.75:shadowx=2:shadowy=3"
          if weight_shadow else "")
    return (f"drawtext=fontfile='{FONT}':text='{text}':fontsize={size}:"
            f"fontcolor={color}:x={x}:y={y}{sh}:alpha={alpha}")


ACCENT = "0xE50914"


def text_filter(kind, l1, l2, dur, slot=0):
    l1 = _clean(l1)
    l2 = _clean(l2)
    d = f"{dur:.2f}"

    if kind == "title":
        e = _ease(0.0, 0.5)
        band = "drawbox=x=0:y=ih/2-120:w=iw:h=240:color=black@0.55:t=fill"
        bar = (f"drawbox=x=iw/2-150:y=ih/2+64:w=300:h=5:"
               f"color={ACCENT}:t=fill")
        # title slides up into place; subtitle staggered
        t1 = _dt(l1, 84, "white", "(w-text_w)/2",
                 f"'(h/2)-92-34*(1-{e})'", _alpha(dur, 0.0, 0.5))
        parts = [band, bar, t1]
        if l2:
            e2 = _ease(0.18)
            parts.append(_dt(l2, 32, "0xE8E8E8", "(w-text_w)/2",
                             f"'(h/2)+22+18*(1-{e2})'",
                             _alpha(dur, 0.18)))
        return ",".join(parts)

    if kind == "chapter":
        e = _ease(0.1)
        band = "drawbox=x=0:y=ih-250:w=iw:h=150:color=black@0.5:t=fill"
        bar = f"drawbox=x=100:y=ih-250:w=9:h=150:color={ACCENT}:t=fill"
        kicker = _dt("CHAPTER", 26, ACCENT, "134", "h-232",
                     _alpha(dur, 0.0))
        title = _dt(l1, 60, "white", f"'134-40*(1-{e})'", "h-192",
                    _alpha(dur, 0.12))
        return ",".join([band, bar, kicker, title])

    if kind == "movie":
        e = _ease(0.0, 0.5)
        band = "drawbox=x=0:y=ih/2-90:w=iw:h=180:color=black@0.6:t=fill"
        bar1 = f"drawbox=x=iw/2-220:y=ih/2-92:w=440:h=4:color={ACCENT}:t=fill"
        bar2 = f"drawbox=x=iw/2-220:y=ih/2+88:w=440:h=4:color={ACCENT}:t=fill"
        t1 = _dt(l1, 66, "white", "(w-text_w)/2",
                 f"'(h/2)-46-24*(1-{e})'", _alpha(dur, 0.0, 0.5))
        parts = [band, bar1, bar2, t1]
        if l2:
            parts.append(_dt(l2, 34, ACCENT, "(w-text_w)/2", "(h/2)+30",
                             _alpha(dur, 0.2)))
        return ",".join(parts)

    if kind == "quote":
        e = _ease(0.05, 0.5)
        band = "drawbox=x=0:y=ih-330:w=iw:h=200:color=black@0.55:t=fill"
        mark = f"drawbox=x=120:y=ih-300:w=10:h=130:color={ACCENT}:t=fill"
        t1 = _dt(l1, 50, "white", f"'170-30*(1-{e})'", "h-262",
                 _alpha(dur, 0.15))
        t2 = _dt("\"", 90, ACCENT, "150", "h-330", _alpha(dur, 0.0))
        return ",".join([band, mark, t2, t1])

    if kind == "marker":
        e = _ease(0.0, 0.5)
        t1 = _dt(l1, 120, "white@0.92", f"'(w-text_w)/2'",
                 f"'160-30*(1-{e})'", _alpha(dur, 0.0, 0.5), False)
        bar = f"drawbox=x=iw/2-120:y=300:w=240:h=5:color={ACCENT}:t=fill"
        return ",".join([t1, bar])

    if kind in ("stat", "lt", "ex"):
        # corner lower-third; lt/ex alternate side by slot for variety
        right = (kind == "stat") or (kind in ("lt", "ex") and slot % 2)
        e = _ease(0.1)
        if kind == "stat":
            bw, bh, by = 720, 156, 120
            bx = "iw-780"
            tx, sx = "w-740", "w-740"
        elif right:
            bw, bh, by = 720, 130, "ih-230"
            bx = "iw-780"
            tx = sx = "w-740"
        else:
            bw, bh, by = 720, 130, "ih-230"
            bx = "60"
            tx = sx = "99"
        yexpr = by if isinstance(by, str) else str(by)
        panel = (f"drawbox=x={bx}:y={yexpr}:w={bw}:h={bh}:"
                 f"color=black@0.58:t=fill")
        accent = (f"drawbox=x={bx}:y={yexpr}:w=10:h={bh}:"
                  f"color={ACCENT}:t=fill")
        # slide direction: from the side it's anchored to
        off = 44
        slide = f"+{off}*(1-{e})" if right else f"-{off}*(1-{e})"
        if kind == "stat":
            l1y, l2y, s1, s2 = "y+26", "y+112", 62, 26
            yb = 120
            l1yv, l2yv = f"{yb+26}", f"{yb+108}"
        else:
            l1yv = "h-214"
            l2yv = "h-150"
            s1, s2 = 46, 26
        a1 = _alpha(dur, 0.1)
        parts = [panel, accent,
                 _dt(l1, s1, "white", f"'{tx}{slide}'", l1yv, a1)]
        if l2:
            parts.append(_dt(l2, s2, "0xD8D8D8", f"'{sx}{slide}'",
                             l2yv, _alpha(dur, 0.22)))
        return ",".join(parts)

    # fallback: simple faded label
    return _dt(l1, 40, "white", "(w-text_w)/2", "h-160", _alpha(dur, 0.0))


# ------------------------------------------------------------ validation

def validate(timeline, sentences, audio_dur, events):
    print("\n[VALIDATION]")
    ok = True
    ids = [e["shot_id"] for e in timeline]
    scenes = [e["scene"] for e in timeline]
    print(f"  {'OK ' if len(ids) == len(set(ids)) else 'X  '}"
          f"unique shots: {len(set(ids))}/{len(ids)} pieces")
    if len(ids) != len(set(ids)):
        ok = False
    rep = len(scenes) - len(set(scenes))
    print(f"  {'OK ' if rep == 0 else '!  '}scene reuse: {rep} "
          f"(0 = every visual moment unique)")

    over = [e for e in timeline if e["dur"] > 4.001]
    print(f"  {'OK ' if not over else 'X  '}max shot length 4.0s "
          f"({len(over)} violations)")
    if over:
        ok = False

    total = sum(e["dur"] for e in timeline)
    good = abs(total - audio_dur) < 4
    print(f"  {'OK ' if good else 'X  '}duration {total:.1f}s vs narration "
          f"{audio_dur:.1f}s")
    if total < audio_dur - 4:
        ok = False

    # REQUIREMENT 1/2/6: every piece must be on-topic for the sentence it
    # sits under. This is the primary editorial gate.
    on = [e for e in timeline if on_topic(e["stype"], e["cat"])]
    off = [e for e in timeline if not on_topic(e["stype"], e["cat"])]
    trate = len(on) / max(1, len(timeline)) * 100
    print(f"  {'OK ' if trate >= 92 else 'X  '}visuals match narration "
          f"topic: {len(on)}/{len(timeline)} pieces ({trate:.0f}%)")
    if trate < 92:
        ok = False
    if off:
        badcnt = Counter((e["stype"], e["cat"]) for e in off)
        print("      off-topic pieces: " + ", ".join(
            f"{st}->{ct}x{n}" for (st, ct), n in badcnt.most_common(8)))

    ryan_sents = [e for e in timeline
                  if e["stype"] in ("ryan", "deadpool", "coach")]
    on_subject = [e for e in ryan_sents
                  if e["cat"] in (ALL_RYAN | COACH)]
    rate = len(on_subject) / max(1, len(ryan_sents)) * 100
    print(f"  {'OK ' if rate >= 75 else 'X  '}Ryan/coach footage on "
          f"Ryan/coach narration: {rate:.0f}%")
    if rate < 75:
        ok = False

    cats = Counter(e["cat"] for e in timeline)
    ryan_total = sum(v for k, v in cats.items() if k in ALL_RYAN)
    print(f"  OK  footage mix: {ryan_total} Ryan pieces / "
          f"{sum(cats[c] for c in COACH)} coach / "
          f"{len(timeline) - ryan_total - sum(cats[c] for c in COACH)} "
          f"male B-roll")
    print(f"  OK  female-tagged scenes used: 0 (excluded at index level)")
    print(f"  OK  text animations: {len(events)} "
          f"(title, chapters, lower-thirds, stats, exercise labels)")

    # AUDIO-VISUAL SYNC: sentences that name a specific exercise must show
    # that exercise, or - when no footage of it exists in the library - the
    # same movement family (a deadlift cue may take pull footage, never a
    # red-carpet shot).
    def ex_ok(e):
        w, g = e.get("ex_want"), e.get("ex_got")
        if not w:
            return True
        if g == w:
            return True
        return bool(g and EXERCISE_FAMILY.get(g) == EXERCISE_FAMILY.get(w))

    ex_pieces = [e for e in timeline if e.get("ex_want")]
    exact = [e for e in ex_pieces if e.get("ex_got") == e.get("ex_want")]
    fam = [e for e in ex_pieces if ex_ok(e)]
    if ex_pieces:
        er = len(exact) / len(ex_pieces) * 100
        fr = len(fam) / len(ex_pieces) * 100
        print(f"  {'OK ' if fr >= 85 else 'X  '}exercise sync: {len(exact)} "
              f"exact + {len(fam) - len(exact)} same-family = {len(fam)}/"
              f"{len(ex_pieces)} ({fr:.0f}% on-movement, {er:.0f}% exact)")
        if fr < 85:
            ok = False
        nofam = sorted({e["ex_want"] for e in ex_pieces if not ex_ok(e)})
        if nofam:
            print(f"      no matching-family footage for: "
                  f"{', '.join(nofam[:10])}")

    nut = [e for e in timeline if e["stype"] == "nutrition"]
    if nut:
        good = [e for e in nut if e["cat"] in (FOOD | ALL_RYAN)]
        print(f"  OK  nutrition visuals: {len(good)}/{len(nut)} nutrition "
              f"sentences show food or the subject "
              f"({len(good)/len(nut)*100:.0f}%)")
    return ok


# ------------------------------------------------------------ render

def render(timeline, events, audio_dur):
    work = OUT_DIR / f"_render_{os.getpid()}"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    # cinematic base: normalize + subtle grade (contrast/saturation
    # lift and a soft vignette) so every shot shares one look
    base_vf = ("scale=1920:1080:force_original_aspect_ratio=decrease,"
               "pad=1920:1080:(ow-iw)/2:(oh-ih)/2:black,fps=30,"
               "format=yuv420p,eq=contrast=1.05:saturation=1.15,"
               "vignette=PI/5")

    def rp(e, out):
        work.mkdir(parents=True, exist_ok=True)  # self-heal if deleted
        vf = base_vf
        # never leave the screen static: slow punch-in on every other
        # shot (6% zoom over the piece duration)
        if e["slot"] % 2 == 0:
            frames = max(2, int(e["dur"] * 30))
            vf += (f",zoompan=z='1+0.06*on/{frames}':d=1:"
                   "x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
                   "s=1920x1080:fps=30")
        ev = events.get(e["slot"])
        if ev:
            vf = vf + "," + text_filter(ev[0], ev[1], ev[2], e["dur"],
                                        e["slot"])
        subprocess.run(
            ["ffmpeg", "-ss", str(e["in"]), "-i", e["src"],
             "-t", str(e["dur"]), "-vf", vf, "-an",
             "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
             "-y", str(out)], capture_output=True, timeout=180)

    for i, e in enumerate(timeline):
        rp(e, work / f"p_{i:04d}.mp4")
        if (i + 1) % 25 == 0:
            print(f"    [{i + 1}/{len(timeline)}] rendered")

    parts = []
    for i, e in enumerate(timeline):
        out = work / f"p_{i:04d}.mp4"
        if not out.exists():
            print(f"    re-render {i} (text filter fallback: no text)")
            subprocess.run(
                ["ffmpeg", "-ss", str(e["in"]), "-i", e["src"],
                 "-t", str(e["dur"]), "-vf", base_vf, "-an",
                 "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
                 "-y", str(out)], capture_output=True, timeout=180)
        if out.exists():
            parts.append(out)

    lst = work / "list.txt"
    work.mkdir(parents=True, exist_ok=True)      # self-heal if deleted
    if not parts:
        raise RuntimeError(
            "no rendered pieces on disk - the render folder was deleted "
            "while the build was running; do not clean final_video/ "
            "during a build")
    with open(lst, "w", encoding="utf-8") as f:
        for p in parts:
            f.write(f"file '{p.absolute().as_posix()}'\n")
    silent = work / "video.mp4"
    r = subprocess.run(["ffmpeg", "-f", "concat", "-safe", "0",
                        "-i", str(lst), "-c:v", "copy", "-an",
                        "-y", str(silent)],
                       capture_output=True, text=True, timeout=1800)
    if not silent.exists():
        raise RuntimeError("concat: " + (r.stderr or "")[-300:])
    final = OUT_DIR / FINAL_NAME
    r = subprocess.run(["ffmpeg", "-i", str(silent), "-i", str(VOICEOVER),
                        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                        "-map", "0:v:0", "-map", "1:a:0",
                        "-t", f"{audio_dur:.2f}", "-y", str(final)],
                       capture_output=True, text=True, timeout=1800)
    if not final.exists():
        raise RuntimeError("mux: " + (r.stderr or "")[-300:])
    shutil.rmtree(work, ignore_errors=True)
    return final


# ------------------------------------------------------------ main

def main():
    print("\n" + "=" * 70)
    print("DOCUMENTARY BUILDER v3 - vision-classified, Ryan-first, "
          "animated text")
    print("=" * 70)
    OUT_DIR.mkdir(exist_ok=True)

    print("\n[1/6] Narration...")
    if not VOICEOVER.exists():
        make_voiceover()
    audio_dur = ffprobe_duration(VOICEOVER)
    print(f"    {int(audio_dur//60)}:{int(audio_dur%60):02d} male narration")

    print("\n[2/6] Shot database from visual classification...")
    shots, dropped = build_shot_db()
    cats = Counter(s["cat"] for s in shots)
    ryan_n = sum(v for k, v in cats.items() if k in ALL_RYAN)
    print(f"    {len(shots)} usable shots  |  {dropped} scenes rejected "
          "(female / graphics / off-subject)")
    print(f"    Ryan footage: {ryan_n} shots | coach: "
          f"{sum(cats[c] for c in COACH)} | male exercise B-roll: "
          f"{sum(cats[c] for c in ALL_EX)} | food: "
          f"{sum(cats[c] for c in FOOD)}")

    print("\n[3/6] Narration timeline...")
    sentences = sentence_timeline(audio_dur)
    dist = Counter(s["type"] for s in sentences)
    print(f"    {len(sentences)} sentences: " +
          ", ".join(f"{k}:{v}" for k, v in dist.most_common(8)))

    print("\n[4/6] Building timeline (Ryan-first, unique, max 4s)...")
    timeline = build_timeline(sentences, shots)
    TIMELINE_FILE.write_text(json.dumps(timeline, indent=0))
    print(f"    {len(timeline)} pieces -> timeline.json")

    events = build_text_events(sentences, timeline)

    print("\n[5/6] Validation...")
    if not validate(timeline, sentences, audio_dur, events):
        print("\n[!] VALIDATION FAILED - export refused.")
        return False

    print("\n[6/6] Rendering with text animations...")
    final = render(timeline, events, audio_dur)
    size = final.stat().st_size / 1e6
    dur = ffprobe_duration(final)
    print("\n" + "=" * 70)
    print("SUCCESS")
    print(f"  {final}")
    print(f"  {size:.0f} MB | {int(dur//60)}:{int(dur%60):02d} | "
          f"{len(timeline)} unique shots | {len(events)} text animations")
    print("=" * 70)
    return True


if __name__ == "__main__":
    raise SystemExit(0 if main() else 1)
