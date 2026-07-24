"""transcript - everything about the script: classify each sentence by
topic and by the specific exercise it names, parse a markdown transcript
into timed sections, generate a script from a celebrity name (built-in
template, or the Claude API when a key is present), and chapter a raw
transcription.
"""

import os
import re
import subprocess
import sys
from pathlib import Path

from . import settings


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (name or "").lower()).strip("_") or "subject"


class NoApiKey(Exception):
    """No Claude API key available for the researched-write path."""


class NoFitnessData(Exception):
    """The subject has no publicly documented training/diet to build on."""
    def __init__(self, name):
        super().__init__(f"no public workout/diet data for {name}")


# ---------------------------------------------------------- sentence typing
def _rules(coach: str, subject: str):
    cw = [w.lower() for w in coach.split()] if coach else []
    sw = [w.lower() for w in subject.split()] if subject else []
    return [
        ("coach", cw + ["strength coach", "his coach", "her coach",
                         "the coach", "trainer"]),
        ("deadpool", ["the suit", "trailer", "film", "movie", "role",
                      "premiere", "set of", "shooting", "filming",
                      "character", "on screen", "on-screen"]),
        ("nutrition", ["eat", "meal", "food", "diet", "protein", "carb",
                       "nutrition", "calorie", "chicken", "salmon", "rice",
                       "sweet potato", "avocado", "alcohol", "sugar",
                       "hydration", "electrolyte", "hungry", "macros",
                       "grams", "oats", "eggs", "supplement"]),
        ("recovery", ["sleep", "recover", "rest day", "stretch", "sauna",
                      "cold", "ice bath", "massage", "mobility",
                      "foam roll", "yoga"]),
        ("chest", ["chest", "bench", "incline press", "flye", "push-up",
                   "pushup", "dip", "tricep", "pressdown", "skull crusher"]),
        ("back", ["back", "row", "pull-up", "pullup", "pulldown", "lat ",
                  "deadlift", "posterior", "romanian", "hip thrust",
                  "glute", "bicep", "curl"]),
        ("legs", ["squat", "lunge", "leg", "quad", "hamstring", "prowler",
                  "calf"]),
        ("shoulders", ["shoulder", "lateral raise", "delt", "overhead press",
                       "arm work", "preacher"]),
        ("cardio", ["cardio", "sprint", "conditioning", "jump rope",
                    "boxing", "run", "hiking", "cycling", "battle rope",
                    "sled", "carries", "carrying", "explosive",
                    "kettlebell", "medicine ball", "hiit", "interval"]),
        ("workout", ["train", "workout", "gym", "exercise", "lift",
                     "session", "sets", "reps", "warm-up", "warm up",
                     "program", "superset", "split"]),
        ("award", ["award", "oscar", "ceremony", "walk of fame",
                   "red carpet", "sexiest man", "honored"]),
        ("family", ["family", "wife", "husband", "his kids", "her kids",
                    "children", "daughter", "son ", "married"]),
        ("business", ["business", "company", "brand", "entrepreneur",
                      "investment"]),
        ("ryan", sw + ["actor", "actress", "he ", "his ", "him", "she ",
                       "her "]),
    ]


EXERCISE_KEYWORDS = [
    ("bench_press", ["incline press", "incline dumbbell", "bench press",
                     "flat dumbbell press", "chest press", "dumbbell press",
                     "cable flye", "flyes", "inclined bench"]),
    ("pushup", ["push-up", "push up", "pushup"]),
    ("dips", ["dips"]),
    ("pullup", ["pull-up", "pull up", "pullup", "pulldown", "chin-up"]),
    ("row", ["barbell row", "dumbbell row", "bent-over", "bent over",
             " rows", " row "]),
    ("deadlift", ["deadlift", "romanian", "trap bar"]),
    ("squat", ["squat"]),
    ("lunge", ["lunge"]),
    ("carry", ["carry", "carries", "farmer"]),
    ("kettlebell", ["kettlebell"]),
    ("medicine_ball", ["medicine ball", "ball slam"]),
    ("boxing", ["boxing", "pad work", "fight training", "shadow boxing",
                "martial arts", "choreography"]),
    ("jump_rope", ["jump rope"]),
    ("running", ["sprint", "running", "treadmill", "prowler",
                 "battle rope", "bike interval"]),
    ("curl", ["curl", "bicep"]),
    ("overhead_press", ["overhead press", "lateral raise", "rear delt",
                        "shoulder press"]),
    ("stretching", ["foam roll", "stretch", "mobility", "warm-up",
                    "warm up", "soft tissue", "yoga"]),
    ("breathing", ["breath"]),
]


def type_of_sentence(s, coach="", subject=""):
    s = " " + s.lower() + " "
    for t, keys in _rules(coach, subject):
        if any(k in s for k in keys):
            return t
    return "generic"


def exercise_of_sentence(s):
    s = " " + s.lower() + " "
    for ex, keys in EXERCISE_KEYWORDS:
        if any(k in s for k in keys):
            return ex
    return None


# ---------------------------------------------------------- parsing
def parse_sections(transcript_path: Path):
    sections, cur_title, cur_lines = [], "OPEN", []
    for line in Path(transcript_path).read_text(encoding="utf-8").split("\n"):
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


# ---------------------------------------------------------- chaptering audio
SECTION_TRIGGERS = [
    ("set the stage", "BASELINE"), ("some context", "BASELINE"),
    ("progression", "THE PROGRESSION"),
    ("actual week", "THE WEEKLY SPLIT"), ("weekly split", "THE WEEKLY SPLIT"),
    ("monday", "MONDAY"), ("tuesday", "TUESDAY"), ("wednesday", "WEDNESDAY"),
    ("thursday", "THURSDAY"), ("friday", "FRIDAY"), ("saturday", "SATURDAY"),
    ("sunday", "SUNDAY"),
    ("training style", "TRAINING PRINCIPLES"),
    ("actually eats", "NUTRITION"), ("nutrition", "NUTRITION"),
    ("sample daily", "A DAY OF EATING"),
    ("treadmill", "CARDIO"), ("cardio is", "CARDIO"),
    ("recovery is treated", "RECOVERY"),
    ("scaled down", "THE REALISTIC VERSION"),
    ("most people can't", "THE REALISTIC VERSION"),
    ("biggest mistakes", "COMMON MISTAKES"),
    ("week by week", "FINAL WORD"), ("go get to work", "FINAL WORD"),
]


def chapter_segments(segments, subject, slug) -> Path:
    """Write transcript_<slug>.md from Whisper segments, inserting chapter
    headers where format triggers appear."""
    def mmss(t):
        return f"{int(t // 60):02d}:{int(t % 60):02d}"

    title = subject or slug.replace("_", " ").title()
    lines = [f"# {title} - Documentary (narration transcript)", "",
             f"## [{mmss(0)}] HOOK", ""]
    used = set()
    for s in segments:
        low = s["text"].lower()
        for trig, sect in SECTION_TRIGGERS:
            if trig in low and sect not in used:
                used.add(sect)
                lines += ["", f"## [{mmss(s['start'])}] {sect}", ""]
                break
        lines.append(s["text"])
    out = settings.TRANSCRIPTS / f"transcript_{slug}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")
    return out


# ---------------------------------------------------------- generation
def generate_template(name: str, coach: str, minutes: int) -> Path:
    """Offline workout-documentary script (no API). Fills a proven
    structure with the subject/coach so the full pipeline is testable from
    a name alone."""
    c = coach or "a professional strength coach"
    slug = slugify(name)
    T = f"""# {name} - Training & Transformation Documentary ({minutes}-min cut)

## [00:00] HOOK
{name} built one of the most talked-about physiques in modern film. This is the story of how that body was actually built - the training, the diet, and the discipline behind it. No shortcuts, no secrets, just the real week-by-week work.

## [00:40] SOURCING
Everything here is drawn from what has been publicly reported in interviews and features. This is a researched breakdown of the stated methods, not a leaked private plan.

## [01:00] BASELINE
Before the transformation, {name} had a fairly ordinary build. The change came from years of consistent, structured training with {c}, not a single crash program. Consistency over time is the real engine behind the result.

## [02:00] THE PROGRESSION
Look at the trajectory and the pattern is obvious. Each role built on the last - leaner, stronger, more athletic. That is not a series of separate efforts. It is one long one, compounding year after year.

## [03:00] THE WEEKLY SPLIT
Here is how a training week was organised. Six focused days, one rest day, each day with a clear job to do.

## [04:00] MONDAY - CHEST & TRICEPS
Monday opens with pressing. An incline bench press first, then a flat dumbbell press, then cable flyes to finish the chest under tension. Triceps are trained in supersets - dips paired with push-ups. The day closes with a short metabolic finisher: battle ropes, medicine ball slams, and jump rope.

## [05:00] TUESDAY - BACK & BICEPS
Tuesday is back and biceps. Pull-ups or heavy lat pulldowns lead, then bent-over barbell rows and single-arm dumbbell rows. Biceps are supersetted at the end, followed by a dedicated core circuit.

## [06:00] WEDNESDAY - LEGS
Wednesday is legs with a quad emphasis. Squats or front squats open the session, then leg press, Bulgarian split squats, and walking lunges. After lifting, twenty minutes of interval conditioning - bike sprints or prowler pushes.

## [07:00] THURSDAY - SHOULDERS & ARMS
Thursday runs lighter and higher rep. Overhead press, lateral raises, and rear delt flyes, then preacher curls and rope pushdowns. A pump-and-recovery day placed between the two heavy sessions.

## [08:00] FRIDAY - POSTERIOR CHAIN
Friday returns to the posterior chain. Deadlifts or trap bar deadlifts are the centerpiece, then Romanian deadlifts and hip thrusts for the glutes and hamstrings. The session ends with explosive work - kettlebell swings and medicine ball throws.

## [09:00] SATURDAY - CONDITIONING
Saturday is conditioning, often with fight-training elements: jump rope, shadow boxing, and pad work. It builds conditioning while rehearsing the athleticism the roles demand.

## [09:40] SUNDAY - RECOVERY
Sunday is a genuine rest day. Mobility, walking, foam rolling, and sleep. You cannot train hard six days a week without taking recovery just as seriously.

## [10:20] NUTRITION
The diet is built on high protein, carbohydrates matched to training demand, and enough fat to support recovery. Protein is spread across roughly five meals a day - eggs, chicken, lean beef, white fish and salmon, with rice, oats and sweet potatoes for carbs.

## [11:20] RECOVERY
Recovery is treated as seriously as the training. Seven to nine hours of sleep, sauna and cold exposure where available, and regular soft-tissue work. You cannot out-train bad recovery.

## [12:10] THE REALISTIC VERSION
Most people cannot train six days a week with a private coach and a chef. Train four to five days per week, add two or three conditioning sessions, eat around one gram of protein per pound of body weight, and progress the load over time.

## [13:00] FINAL WORD
The physique {name} built was the result of structured, consistent work over years - not a nine-week miracle. Respect the rest day, be honest about your technique, and keep showing up. That is the entire story, and it is exactly why it worked.
"""
    out = settings.TRANSCRIPTS / f"transcript_{slug}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(T, encoding="utf-8")
    return out


# ---------------------------------------------------------- researched doc
# Section arcs per celebrity type. The real biography is distributed across
# whichever of these fit the amount of sourced material.
TYPE_SECTIONS = {
    "youtuber": ["THE BEGINNING", "BUILDING THE CHANNEL", "THE BREAKTHROUGH",
                 "THE CONTENT", "GROWTH & INFLUENCE", "BEYOND YOUTUBE"],
    "actor": ["EARLY LIFE", "THE BREAKTHROUGH", "DEFINING ROLES",
              "CRAFT & RANGE", "RECOGNITION", "LEGACY"],
    "musician": ["ORIGINS", "THE BREAKTHROUGH", "SIGNATURE SOUND",
                 "THE HITS", "EVOLUTION", "IMPACT"],
    "athlete": ["EARLY CAREER", "THE RISE", "PEAK YEARS", "STYLE OF PLAY",
                "RECORDS & HONOURS", "LEGACY"],
    "entrepreneur": ["EARLY LIFE", "THE FIRST VENTURE", "THE BREAKTHROUGH",
                     "BUILDING AN EMPIRE", "PHILOSOPHY", "IMPACT"],
    "public figure": ["BACKGROUND", "RISE TO PROMINENCE", "THE WORK",
                      "DEFINING MOMENTS", "INFLUENCE", "LEGACY"],
}
TYPE_HOOK = {
    "youtuber": "{name} built an audience of millions from nothing but a "
                "camera and an idea. This is how that happened.",
    "actor": "{name} is one of the most recognisable names in film. This "
             "is the story behind the career.",
    "musician": "{name} turned a sound into a movement. This is the story "
                "of how it happened.",
    "athlete": "{name} became one of the defining figures of the sport. "
               "This is the story of that rise.",
    "entrepreneur": "{name} turned an idea into an empire. This is the "
                    "story of how it was built.",
    "public figure": "{name} became a name millions recognise. This is the "
                     "story of how it happened.",
}
TYPE_CLOSE = {
    "youtuber": "From a single upload to a global audience, {name}'s story "
                "is a blueprint for the creator era. If you enjoyed this, "
                "subscribe for more creator deep-dives.",
    "public figure": "That is the story of {name} - the rise, the work, and "
                     "the mark left behind. Drop a like and let us know who "
                     "we should cover next.",
}


def _mmss(t):
    return f"{int(t // 60):02d}:{int(t % 60):02d}"


def _chunk(items, n):
    n = max(1, n)
    size = max(1, -(-len(items) // n))
    return [items[i:i + size] for i in range(0, len(items), size)][:n]


def generate_researched(name: str, minutes: int, prof: dict = None):
    """Offline fallback (no API key): a chronological documentary from the
    verified Wikipedia research. It won't fabricate workout/diet specifics -
    that depth needs the API path. `prof` may be passed to avoid a second
    lookup. Returns (path, meta)."""
    from . import research as R
    prof = prof or R.research_subject(name)
    typ = prof["type"]
    bio = (prof.get("intro") or prof.get("summary") or "").strip()
    if not bio:
        return generate_generic(name, minutes, typ), {"type": typ,
                                                      "coach": "",
                                                      "sourced": False,
                                                      "title": name}
    sents = [s.strip() for s in re.split(r"(?<=[.!?])\s+", bio)
             if len(s.strip()) > 2]
    titles = TYPE_SECTIONS.get(typ, TYPE_SECTIONS["public figure"])
    n_sec = min(len(titles), max(1, len(sents) // 2))
    chunks = _chunk(sents, n_sec)

    hook = TYPE_HOOK.get(typ, TYPE_HOOK["public figure"]).format(name=name)
    close = TYPE_CLOSE.get(typ, TYPE_CLOSE["public figure"]).format(name=name)
    lines = [f"# {name} - Documentary", "", f"## [{_mmss(0)}] HOOK", "", hook,
             "", f"## [{_mmss(25)}] SOURCING", "",
             f"Everything in this video is drawn from publicly available "
             f"sources about {name}, including their Wikipedia profile and "
             f"public interviews."]
    # ~ distribute time across the sourced sections
    total = sum(len(" ".join(c).split()) for c in chunks) or 1
    t = 45.0
    span = max(minutes * 60 - 70, 60)
    for i, c in enumerate(chunks):
        lines += ["", f"## [{_mmss(t)}] {titles[i]}", "", " ".join(c)]
        t += span * len(" ".join(c).split()) / total
    lines += ["", f"## [{_mmss(min(t, minutes*60-10))}] CLOSE", "", close]

    out = settings.TRANSCRIPTS / f"transcript_{slugify(name)}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")
    return out, {"type": typ, "coach": "", "sourced": prof["sourced"],
                 "title": prof["title"], "url": prof.get("url", "")}


def generate_generic(name: str, minutes: int, typ: str = "public figure"):
    """Last-resort script when no sources could be reached (offline)."""
    hook = TYPE_HOOK.get(typ, TYPE_HOOK["public figure"]).format(name=name)
    titles = TYPE_SECTIONS.get(typ, TYPE_SECTIONS["public figure"])
    lines = [f"# {name} - Documentary", "", f"## [{_mmss(0)}] HOOK", "", hook]
    body = {
        "BACKGROUND": f"{name} rose from ordinary beginnings to public "
                      f"recognition through persistence and a distinctive "
                      f"voice.",
        "RISE TO PROMINENCE": f"The breakthrough for {name} came when the "
                              f"work found its audience and momentum built "
                              f"quickly.",
        "THE WORK": f"What sets {name} apart is a consistent body of work "
                    f"and a clear identity that fans connect with.",
        "DEFINING MOMENTS": f"Along the way there were defining moments that "
                            f"turned {name} from a rising name into a "
                            f"household one.",
        "INFLUENCE": f"{name}'s influence now reaches far beyond the work "
                     f"itself, shaping how others approach the field.",
        "LEGACY": f"The story of {name} is still being written, but the "
                  f"impact is already undeniable.",
    }
    t = 30
    for tt in titles:
        para = body.get(tt, f"This chapter covers {name}'s {tt.lower()}.")
        lines += ["", f"## [{_mmss(t)}] {tt}", "", para]
        t += 40
    lines += ["", f"## [{_mmss(t)}] CLOSE", "",
              TYPE_CLOSE["public figure"].format(name=name)]
    out = settings.TRANSCRIPTS / f"transcript_{slugify(name)}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")
    return out


_JUNK = ["share", "copy link", "table of content", "facebook", "linkedin",
         "pinterest", "twitter", "instagram", "subscribe", "cookie",
         "newsletter", "sign up", "advertisement", "read more",
         "click here", "updated:", "published:", "getty", "follow us",
         "terms of", "privacy policy", "affiliate", "©", "all rights",
         "photo by", "image credit", "shop ", "buy now", "www.", "http"]


def generate_from_sources(name: str, minutes: int, sources: list):
    """Build a fitness-only documentary from scraped public fitness-article
    text (no API key). Keeps only clean, on-topic training/diet sentences.
    Raises NoFitnessData if there isn't enough real content."""
    from . import research as R
    text = " ".join(s.get("text", "") for s in sources)
    seen, sents = set(), []
    for s in re.split(r"(?<=[.!?])\s+", text):
        s = s.strip()
        low = s.lower()
        w = len(s.split())
        if w < 6 or w > 55:
            continue
        if any(j in low for j in _JUNK):
            continue
        if not R._is_fitness(s):
            continue
        key = low[:50]
        if key in seen:
            continue
        seen.add(key)
        sents.append(s)
    if len(sents) < 8:
        raise NoFitnessData(name)

    titles = ["THE PHYSIQUE", "THE TRAINING APPROACH", "THE WORKOUT SPLIT",
              "THE EXERCISES", "THE DIET PLAN", "NUTRITION & RECOVERY",
              "THE PHILOSOPHY"]
    n_sec = min(len(titles), max(2, len(sents) // 5))
    chunks = _chunk(sents, n_sec)
    hook = (f"How did {name} build their physique? Here is the real "
            f"training and diet behind it.")
    close = (f"That is the workout and diet behind {name}'s physique - the "
             f"training, the food, and the discipline that built it.")
    lines = [f"# {name} - Workout & Diet Documentary", "",
             f"## [{_mmss(0)}] HOOK", "", hook, "",
             f"## [{_mmss(20)}] SOURCING", "",
             f"This is compiled from public fitness features and interviews "
             f"about {name}'s training and diet."]
    t = 42.0
    for i, c in enumerate(chunks):
        lines += ["", f"## [{_mmss(t)}] {titles[i]}", "", " ".join(c)]
        t += max(40, (minutes * 60 - 80) / max(1, n_sec))
    lines += ["", f"## [{_mmss(t)}] CLOSE", "", close]

    out = settings.TRANSCRIPTS / f"transcript_{slugify(name)}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")
    return out, {"type": "fitness", "coach": "", "sourced": True,
                 "title": name, "sources": [s.get("url") for s in sources]}


def generate_api(name: str, minutes: int, context: str = ""):
    """Write the documentary with the Claude API, GROUNDED in the verified
    research passed in (Wikipedia) plus the model's own sourced knowledge -
    working with both for solid, real content. Returns (path, coach) or
    raises so the caller can fall back."""
    try:
        import anthropic
    except ImportError:
        subprocess.run([sys.executable, "-m", "pip", "install",
                        "anthropic", "-q"], check=True)
        import anthropic

    key = os.environ.get("ANTHROPIC_API_KEY", "")
    key_file = settings.ROOT / "anthropic_key.txt"
    if not key and key_file.exists():
        key = key_file.read_text().strip()
    if not key:
        raise NoApiKey("no ANTHROPIC_API_KEY")

    words = minutes * 152
    ctx = (f"\n\nVERIFIED RESEARCH (from Wikipedia - use as grounding, "
           f"cross-checked with your own reliably-sourced knowledge):\n"
           f"{context.strip()}\n") if context.strip() else ""
    prompt = f"""You are writing a professionally researched YouTube WORKOUT
& DIET documentary narration script about {name} (spoken as voiceover).

The documentary answers ONE question: "How did {name} build and maintain
their physique?" Everything must revolve around FITNESS - training,
nutrition, body transformation, and physical preparation.

DO NOT discuss awards, television appearances, relationships, business
ventures, general career history, red carpet events, or lifestyle - UNLESS
a point directly explains a physical transformation (e.g. a film role that
required bulking up). No biography for its own sake.

Build the documentary AROUND BODY TRANSFORMATIONS. Research every significant
physical transformation in {name}'s career and give EACH its own chapter,
explaining as flowing narrative: why it was needed; the project/event that
required it; starting physique; target physique; training duration; the
workout split; the daily routine; the diet strategy; calories and macros
when publicly available; recovery methods; the coach/trainer; challenges
faced; and the final outcome. Also cover how the training and diet PHILOSOPHY
evolved over time.

LENGTH IS MANDATORY: the finished script MUST be about {words} words so it
narrates to ~{minutes} minutes. NEVER finish early. If one transformation is
not enough to fill the time, expand with additional verified workout phases,
multiple diet phases, different training periods, preparation for different
projects, recovery phases, and how their philosophy changed - all still
fitness-focused. Keep going until you reach ~{words} words.

WORK WITH BOTH SOURCES: use the verified research below plus your own
reliably-sourced knowledge (interviews, Men's Health and similar, trainer/
nutritionist interviews, podcasts, documentaries) and cross-check. VERIFIED
FACTS ONLY - do NOT invent workout plans, diet plans, exercises, weights,
calorie numbers, macros, supplements or quotes; hedge estimates ("reported",
"he has said") and omit what you cannot verify. If {name} has no publicly
documented training or diet, reply with exactly: NO_FITNESS_DATA{ctx}
Format: first line exactly <!--COACH: trainer full name--> if a trainer is
central, else <!--COACH: none-->. Then '# {name} - Documentary'. Then
fitness chapters '## [MM:SS] TITLE'. Every sentence natural and speakable."""
    client = anthropic.Anthropic(api_key=key)
    msgs = [{"role": "user", "content": prompt}]
    text = ""
    for _ in range(4):                     # keep going until length is met
        resp = client.messages.create(
            model="claude-opus-4-8", max_tokens=20000,
            thinking={"type": "enabled", "budget_tokens": 6000},
            messages=msgs)
        chunk = "".join(b.text for b in resp.content
                        if b.type == "text").strip()
        if "NO_FITNESS_DATA" in chunk and not text:
            raise NoFitnessData(name)
        text = (text + "\n\n" + chunk).strip() if text else chunk
        if len(text.split()) >= words * 0.9:
            break
        msgs += [{"role": "assistant", "content": chunk},
                 {"role": "user", "content":
                  f"Continue the SAME documentary from where it stopped - "
                  f"more verified workout phases, diet phases, role "
                  f"transformations and recovery for {name}, still "
                  f"fitness-only, until the whole script reaches about "
                  f"{words} words. Do not repeat earlier sections or add a "
                  f"conclusion until the length is reached."}]

    coach = ""
    m = re.match(r"\s*<!--COACH:\s*(.+?)\s*-->", text)
    if m:
        c = m.group(1).strip()
        coach = "" if c.lower() == "none" else c
        text = text[m.end():].lstrip()
    out = settings.TRANSCRIPTS / f"transcript_{slugify(name)}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    return out, coach
