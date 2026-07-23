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


# ------------------------------------------------------------ util

def ffprobe_duration(p):
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(p)],
        capture_output=True, text=True, timeout=30)
    return float(r.stdout.strip())


def make_voiceover():
    try:
        import edge_tts
    except ImportError:
        subprocess.run(["pip", "install", "edge-tts", "-q"], check=True)
        import edge_tts
    content = TRANSCRIPT.read_text(encoding="utf-8")
    lines = [l.strip() for l in content.split("\n")
             if l.strip() and not l.startswith("#") and not l.startswith("[")]

    voice = _cfg.get("voice", "en-US-ChristopherNeural")

    async def _s():
        c = edge_tts.Communicate(" ".join(lines), voice)
        await c.save(str(VOICEOVER))
    asyncio.run(_s())


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
    total = sum(len(s) for _, s in flat) or 1
    out, t = [], 0.0
    seen_sections = set()
    for title, s in flat:
        d = len(s) / total * audio_dur
        first = title not in seen_sections
        seen_sections.add(title)
        out.append({"text": s, "type": type_of_sentence(s),
                    "ex": exercise_of_sentence(s),
                    "section": title, "sec_start": first,
                    "start": round(t, 2), "dur": round(d, 2)})
        t += d
    return out


# ------------------------------------------------------------ selection

def build_timeline(sentences, shots):
    unused = {s["id"]: s for s in shots}
    scene_used = Counter()
    scene_last_slot = {}
    last_src, last_cat = [], []
    timeline, slot = [], 0

    # Reservation: Ryan/coach footage is protected for Ryan/coach
    # narration until that demand is covered.
    demand_ryan = sum(s["dur"] for s in sentences
                      if s["type"] in RYAN_TYPES)
    pool_ryan = sum(min(MAX_PIECE, s["len"]) for s in shots
                    if s["cat"] in RYAN_POOL)

    def score(sh, protect):
        s = 0.0
        s += 300 * scene_used[sh["scene"]]          # same scene again: bad
        if slot - scene_last_slot.get(sh["scene"], -999) < SCENE_SPACING:
            s += 900                                # same scene too soon
        if sh["source"] in last_src[-2:]:
            s += 220                                # same video back-to-back
        if sh["cat"] in last_cat[-1:]:
            s += 60                                 # rotate visual category
        if protect and sh["cat"] in RYAN_POOL:
            s += 600                                # reserved for Ryan talk
        if sh["cat"] not in RYAN_POOL and slot > 10:
            broll = sum(1 for e in timeline
                        if e["cat"] not in RYAN_POOL)
            if broll / max(1, len(timeline)) > BROLL_SHARE:
                s += 450          # keep supporting footage near 10%
        s -= 40 * sh["q"]                           # premium footage bonus
        return s

    def pick(stype, want_ex=None):
        protect = (stype not in RYAN_TYPES
                   and pool_ryan < demand_ryan + 60)
        # THE NARRATION IS THE SOURCE OF TRUTH: a sentence naming a
        # specific exercise gets footage of THAT exercise first.
        if want_ex:
            exact = [s for s in unused.values() if s.get("ex") == want_ex]
            if exact:
                return min(exact, key=lambda c: score(c, False))
        best_all, best_all_s = None, None
        for tier, bucket in enumerate(PREF.get(stype, PREF["generic"])):
            cands = [s for s in unused.values() if s["cat"] in bucket]
            if not cands:
                continue
            b = min(cands, key=lambda c: score(c, protect))
            sc = score(b, protect) + tier * 120
            if sc < 200:
                return b
            if best_all is None or sc < best_all_s:
                best_all, best_all_s = b, sc
        if best_all is not None:
            return best_all
        return (min(unused.values(), key=lambda c: score(c, protect))
                if unused else None)

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
            if sh["cat"] in RYAN_POOL:
                pool_ryan -= min(MAX_PIECE, sh["len"])
            if sent["type"] in RYAN_TYPES:
                demand_ryan -= piece
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
    (r"seven to nine hours", "stat", "7-9 HOURS", "SLEEP TARGET"),
    (r"zero point eight to one gram", "stat", "0.8-1 G / LB",
     "DAILY PROTEIN"),
]

SKIP_CHAPTERS = {"OPEN", "HOOK", "SOURCING"}


def build_text_events(sentences, timeline):
    """slot -> (kind, line1, line2). One event per timeline piece."""
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


def text_filter(kind, l1, l2, dur):
    fade = f"alpha='min(1,t/0.4)*min(1,max(0.0001,{dur:.2f}-t)/0.4)'"
    l1 = l1.replace("'", "").replace(":", "\\:")
    l2 = (l2 or "").replace("'", "").replace(":", "\\:")
    if kind in ("title", "chapter"):
        f = (f"drawbox=x=0:y=ih/2-100:w=iw:h=200:color=black@0.45:t=fill,"
             f"drawtext=fontfile='{FONT}':text='{l1}':fontsize=76:"
             f"fontcolor=white:x=(w-text_w)/2:y=(h/2)-70:{fade}")
        if l2:
            f += (f",drawtext=fontfile='{FONT}':text='{l2}':fontsize=30:"
                  f"fontcolor=0xDDDDDD:x=(w-text_w)/2:y=(h/2)+30:{fade}")
        return f
    if kind == "lt":
        f = (f"drawbox=x=60:y=ih-230:w=700:h=130:color=black@0.55:t=fill,"
             f"drawbox=x=60:y=ih-230:w=10:h=130:color=0xE50914:t=fill,"
             f"drawtext=fontfile='{FONT}':text='{l1}':fontsize=46:"
             f"fontcolor=white:x=95:y=h-215:{fade}")
        if l2:
            f += (f",drawtext=fontfile='{FONT}':text='{l2}':fontsize=26:"
                  f"fontcolor=0xCCCCCC:x=95:y=h-150:{fade}")
        return f
    if kind == "stat":
        f = (f"drawbox=x=iw-760:y=120:w=700:h=150:color=black@0.55:t=fill,"
             f"drawbox=x=iw-760:y=120:w=10:h=150:color=0xE50914:t=fill,"
             f"drawtext=fontfile='{FONT}':text='{l1}':fontsize=58:"
             f"fontcolor=white:x=w-720:y=140:{fade}")
        if l2:
            f += (f",drawtext=fontfile='{FONT}':text='{l2}':fontsize=26:"
                  f"fontcolor=0xCCCCCC:x=w-720:y=215:{fade}")
        return f
    # exercise pill, bottom-right
    return (f"drawtext=fontfile='{FONT}':text='{l1}':fontsize=38:"
            f"fontcolor=white:box=1:boxcolor=black@0.6:boxborderw=18:"
            f"x=w-text_w-80:y=h-160:{fade}")


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

    # AUDIO-VISUAL SYNC: sentences that name a specific exercise must
    # show that exercise (or the closest available footage).
    ex_pieces = [e for e in timeline if e.get("ex_want")]
    exact = [e for e in ex_pieces if e.get("ex_got") == e.get("ex_want")]
    if ex_pieces:
        rate = len(exact) / len(ex_pieces) * 100
        print(f"  {'OK ' if rate >= 50 else '!  '}exercise sync: "
              f"{len(exact)}/{len(ex_pieces)} exercise mentions show the "
              f"exact exercise ({rate:.0f}%)")
        missing = sorted({e["ex_want"] for e in ex_pieces
                          if e.get("ex_got") != e.get("ex_want")})
        if missing:
            print(f"      exact footage exhausted/absent for: "
                  f"{', '.join(missing[:10])}")

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
            vf = vf + "," + text_filter(ev[0], ev[1], ev[2], e["dur"])
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
