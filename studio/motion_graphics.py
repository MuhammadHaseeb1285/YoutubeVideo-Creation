"""motion_graphics - animated text events and the ffmpeg draw filters that
render them. Slide-ins, staggered reveals, drop shadows, dual-side
lower-thirds, chapter cards, movie title cards, stat callouts, timeline
markers, pull-quotes and exercise labels. Position and alpha are animated
per frame via ffmpeg expressions.
"""

import re

from . import settings

FONT = settings.FONT
ACCENT = settings.ACCENT
SKIP_CHAPTERS = {"OPEN", "HOOK", "SOURCING"}


def stat_specs(coach: str):
    """Text triggers -> (kind, line1, line2). Coach lower-third is built
    from config; the rest describe a fitness documentary in general."""
    specs = []
    if coach:
        specs.append((re.escape(coach.lower()), "lt", coach.upper(),
                      "STRENGTH COACH"))
    specs += [
        (r"incline (bench )?press", "ex", "INCLINE PRESS", ""),
        (r"bench press|flat dumbbell press", "ex", "BENCH PRESS", ""),
        (r"cable fly", "ex", "CABLE FLYES", ""),
        (r"push-?ups?", "ex", "PUSH-UPS", ""),
        (r"\bdips\b", "ex", "DIPS", ""),
        (r"pull-?ups?|lat pulldown", "ex", "PULL-UPS", ""),
        (r"bent-?over.*row|barbell row", "ex", "BARBELL ROW", ""),
        (r"dumbbell row", "ex", "DUMBBELL ROW", ""),
        (r"front squat", "ex", "FRONT SQUAT", ""),
        (r"\bsquat", "ex", "SQUATS", ""),
        (r"leg press", "ex", "LEG PRESS", ""),
        (r"bulgarian|split squat", "ex", "SPLIT SQUAT", ""),
        (r"walking lunge|lunge", "ex", "LUNGES", ""),
        (r"trap bar", "ex", "TRAP BAR DEADLIFT", ""),
        (r"romanian deadlift", "ex", "ROMANIAN DEADLIFT", ""),
        (r"\bdeadlift", "ex", "DEADLIFT", ""),
        (r"hip thrust", "ex", "HIP THRUST", ""),
        (r"kettlebell", "ex", "KETTLEBELL SWINGS", ""),
        (r"lateral raise", "ex", "LATERAL RAISES", ""),
        (r"overhead press", "ex", "OVERHEAD PRESS", ""),
        (r"preacher curl|concentration curl", "ex", "CURLS", ""),
        (r"battle rope", "ex", "BATTLE ROPES", ""),
        (r"jump rope", "ex", "JUMP ROPE", ""),
        (r"shadow boxing|pad work|boxing", "ex", "BOXING", ""),
        (r"foam roll", "ex", "FOAM ROLLING", ""),
        # statistics
        (r"190 to 195|one hundred and ninety", "stat", "190-195 LBS",
         "FILMING WEIGHT"),
        (r"8 to 10 percent|eight to ten percent", "stat", "8-10%",
         "BODY FAT"),
        (r"six feet two|6 feet 2|6'?2", "stat", "6'2\"", "HEIGHT"),
        (r"2,?600 to 3,?200", "stat", "2600-3200 KCAL", "DAILY INTAKE"),
        (r"200 to 250 grams", "stat", "200-250 G", "DAILY PROTEIN"),
        (r"seven to nine hours|7 to 9 hours", "stat", "7-9 HRS",
         "SLEEP TARGET"),
        (r"three to five sets", "stat", "3-5 SETS", "6-12 REPS"),
        (r"15 (plus )?years|fifteen (plus )?years|over 15", "stat",
         "15+ YEARS", "OF CONSISTENCY"),
        # movie / role cards
        (r"deadpool and wolverine", "movie", "DEADPOOL & WOLVERINE", "2024"),
        (r"green lantern", "movie", "GREEN LANTERN", "2011"),
        (r"blade[,: ]+trinity", "movie", "BLADE: TRINITY", "2004"),
        (r"deadpool", "movie", "DEADPOOL", "2016"),
        # markers + quotes
        (r"early two thousands|early 2000s", "marker", "EARLY 2000s", ""),
        (r"diet is 90 percent|90 percent of the battle", "quote",
         "DIET IS 90% OF THE BATTLE", ""),
        (r"look like i can actually fight|train to look", "quote",
         "TRAIN TO FIGHT, NOT JUST TO LIFT", ""),
        (r"out ?train bad recovery", "quote",
         "YOU CAN'T OUT-TRAIN BAD RECOVERY", ""),
        (r"no shortcuts|relentless discipline", "quote",
         "NO SHORTCUTS. JUST CONSISTENCY.", ""),
    ]
    return specs


DAYS = {"MONDAY": "Mon", "TUESDAY": "Tue", "WEDNESDAY": "Wed",
        "THURSDAY": "Thu", "FRIDAY": "Fri", "SATURDAY": "Sat",
        "SUNDAY": "Sun"}

# Keyword chips - short kinetic callouts that keep text on screen through the
# whole film, not just at section breaks. First match wins per sentence.
KEYWORDS = [
    (r"progressive overload", "PROGRESSIVE OVERLOAD"),
    (r"posterior chain", "POSTERIOR CHAIN"), (r"v-?taper", "V-TAPER"),
    (r"supersets?", "SUPERSETS"), (r"metabolic", "METABOLIC FINISHER"),
    (r"incline press", "INCLINE PRESS"), (r"bench press", "BENCH PRESS"),
    (r"pull-?ups?", "PULL-UPS"), (r"deadlift", "DEADLIFTS"),
    (r"squats?", "SQUATS"), (r"lunges?", "LUNGES"),
    (r"lateral raise", "LATERAL RAISES"), (r"hip thrust", "HIP THRUSTS"),
    (r"kettlebell", "KETTLEBELL"), (r"battle rope", "BATTLE ROPES"),
    (r"jump rope", "JUMP ROPE"), (r"shadow boxing|pad work", "FIGHT WORK"),
    (r"conditioning", "CONDITIONING"), (r"\bcardio\b", "CARDIO"),
    (r"\bH\.?I\.?I\.?T\b|interval", "HIIT"),
    (r"protein", "HIGH PROTEIN"), (r"carbs?|carbohydrate", "CARB CYCLING"),
    (r"calorie", "CALORIES"), (r"chicken|salmon|lean beef", "LEAN PROTEIN"),
    (r"sweet potato|rice|oats", "CLEAN CARBS"), (r"meal", "MEAL PREP"),
    (r"sleep", "SLEEP"), (r"recovery", "RECOVERY"),
    (r"mobility|stretch", "MOBILITY"), (r"sauna|ice bath", "RECOVERY"),
    (r"discipline", "DISCIPLINE"), (r"consistency|consistent", "CONSISTENCY"),
    (r"transformation", "TRANSFORMATION"), (r"physique", "PHYSIQUE"),
    (r"shredded|vascular", "SHREDDED"), (r"functional", "FUNCTIONAL"),
    (r"explosive|power", "EXPLOSIVE POWER"), (r"core\b", "CORE"),
    (r"glutes?", "GLUTES"), (r"shoulders?", "SHOULDERS"),
    (r"triceps?", "TRICEPS"), (r"biceps?", "BICEPS"),
    (r"strength", "STRENGTH"), (r"athletic", "ATHLETICISM"),
    (r"warm-?up", "WARM-UP"), (r"progression", "PROGRESSION"),
]


def _day_items(sentences):
    seen, items = set(), []
    for sent in sentences:
        sec = sent["section"] or ""
        first = sec.split()[0] if sec else ""
        if first in DAYS and sec not in seen:
            seen.add(sec)
            rest = sec
            for sep in ("—", "-"):
                if sep in sec:
                    rest = sec.split(sep, 1)[1]
                    break
            else:
                rest = " ".join(sec.split()[1:])
            rest = rest.strip().title().replace("&", "+")
            items.append(f"{DAYS[first]} — {rest}" if rest
                         else DAYS[first])
    return items


def build_events(sentences, timeline, subject, coach):
    def piece_at(t):
        for e in timeline:
            if e["at"] <= t < e["at"] + e["dur"] + 0.01:
                return e["slot"]
        return None

    events = {}
    n = len(timeline)
    if timeline:
        events[0] = ("title", (subject or "THE").upper(), "THE TRANSFORMATION")

    # chapter cards on every new section
    for sent in sentences:
        if sent["sec_start"] and sent["section"] not in SKIP_CHAPTERS:
            slot = piece_at(sent["start"])
            if slot is not None and slot not in events:
                events[slot] = ("chapter", sent["section"], "")

    # hero: a numbered "N-DAY SPLIT" list card at the weekly-split intro
    days = _day_items(sentences)
    if len(days) >= 3:
        split_slot = None
        for sent in sentences:
            if sent["sec_start"] and ("SPLIT" in sent["section"]
                                      or "WEEK" in sent["section"]):
                split_slot = piece_at(sent["start"])
                break
        if split_slot is None:                       # else first day section
            for sent in sentences:
                if (sent["section"].split() or [""])[0] in DAYS:
                    split_slot = piece_at(sent["start"])
                    break
        if split_slot is not None:
            events[split_slot] = ("list", f"THE {len(days)}-DAY SPLIT",
                                  "||".join(days[:4]))

    # stat / exercise / movie / quote / marker triggers
    used = set()
    for pat, kind, l1, l2 in stat_specs(coach):
        if pat in used:
            continue
        for sent in sentences:
            if re.search(pat, sent["text"], re.I):
                slot = piece_at(sent["start"])
                if slot is not None and slot not in events:
                    events[slot] = (kind, l1, l2)
                    used.add(pat)
                break

    # keyword chips - spread across the film for 45% coverage (enhanced from 40%)
    # This ensures rich, cinematic feel with text on almost half of shots
    target = int(n * 0.45)
    gap = max(2, n // max(1, target)) if target else 99
    last = -99
    for sent in sentences:
        if len([1 for _ in events]) >= target:
            break
        slot = piece_at(sent["start"])
        if slot is None or slot in events or slot < 3 or slot - last < gap:
            continue
        for pat, label in KEYWORDS:
            if re.search(pat, sent["text"], re.I):
                events[slot] = ("kw", label, "")
                last = slot
                break
    return events


# ---------------------------------------------------------- draw filters
def _clean(s):
    return (s or "").replace("\\", "").replace("'", "") \
                    .replace(":", "\\:").replace("%", "\\%")


def _alpha(dur, delay=0.0, tin=0.45, tout=0.4):
    return (f"'if(lt(t,{delay}),0,"
            f"min(min(1,(t-{delay})/{tin}),max(0,({dur:.2f}-t)/{tout})))'")


def _ease(delay=0.0, tin=0.45):
    return f"min(1,max(0,(t-{delay})/{tin}))"


def _dt(text, size, color, x, y, alpha, shadow=True):
    sh = ":shadowcolor=black@0.75:shadowx=2:shadowy=3" if shadow else ""
    return (f"drawtext=fontfile='{FONT}':text='{text}':fontsize={size}:"
            f"fontcolor={color}:x={x}:y={y}{sh}:alpha={alpha}")


STYLES = ["up", "left", "right", "down", "pop"]


def _enter(style, tx, ty, delay, tin=0.5, dist=58):
    """Return (x_expr, y_expr) that slide a drawtext into (tx, ty) from a
    direction. tx/ty may be ffmpeg expressions. Rotating the style per
    event stops every title animating the same way."""
    e = _ease(delay, tin)
    if style == "left":
        return f"'{tx}-{dist}*(1-{e})'", f"'{ty}'"
    if style == "right":
        return f"'{tx}+{dist}*(1-{e})'", f"'{ty}'"
    if style == "up":
        return f"'{tx}'", f"'{ty}+{dist}*(1-{e})'"
    if style == "down":
        return f"'{tx}'", f"'{ty}-{dist}*(1-{e})'"
    return f"'{tx}'", f"'{ty}+18*(1-{e})'"          # pop (subtle rise)


def text_filter(kind, l1, l2, dur, slot=0):
    l1, l2 = _clean(l1), _clean(l2)
    style = STYLES[slot % len(STYLES)]

    if kind == "title":
        band = "drawbox=x=0:y=ih/2-120:w=iw:h=240:color=black@0.55:t=fill"
        bar = f"drawbox=x=iw/2-150:y=ih/2+64:w=300:h=5:color={ACCENT}:t=fill"
        x, y = _enter(style, "(w-text_w)/2", "(h/2)-92", 0.0, 0.5)
        parts = [band, bar, _dt(l1, 84, "white", x, y, _alpha(dur, 0.0, 0.5))]
        if l2:
            x2, y2 = _enter("pop", "(w-text_w)/2", "(h/2)+22", 0.18)
            parts.append(_dt(l2, 32, "0xE8E8E8", x2, y2, _alpha(dur, 0.18)))
        return ",".join(parts)

    if kind == "chapter":
        band = "drawbox=x=0:y=ih-250:w=iw:h=150:color=black@0.5:t=fill"
        bar = f"drawbox=x=100:y=ih-250:w=9:h=150:color={ACCENT}:t=fill"
        kicker = _dt("CHAPTER", 26, ACCENT, "134", "h-232", _alpha(dur, 0.0))
        x, y = _enter(style if style in ("left", "up", "pop") else "left",
                      "134", "h-192", 0.12)
        return ",".join([band, bar, kicker,
                         _dt(l1, 60, "white", x, y, _alpha(dur, 0.12))])

    if kind == "movie":
        band = "drawbox=x=0:y=ih/2-90:w=iw:h=180:color=black@0.6:t=fill"
        b1 = f"drawbox=x=iw/2-220:y=ih/2-92:w=440:h=4:color={ACCENT}:t=fill"
        b2 = f"drawbox=x=iw/2-220:y=ih/2+88:w=440:h=4:color={ACCENT}:t=fill"
        x, y = _enter(style, "(w-text_w)/2", "(h/2)-46", 0.0, 0.5)
        parts = [band, b1, b2, _dt(l1, 66, "white", x, y,
                                   _alpha(dur, 0.0, 0.5))]
        if l2:
            parts.append(_dt(l2, 34, ACCENT, "(w-text_w)/2", "(h/2)+30",
                             _alpha(dur, 0.2)))
        return ",".join(parts)

    if kind == "quote":
        e = _ease(0.05, 0.5)
        band = "drawbox=x=0:y=ih-330:w=iw:h=200:color=black@0.55:t=fill"
        mark = f"drawbox=x=120:y=ih-300:w=10:h=130:color={ACCENT}:t=fill"
        t2 = _dt("\"", 90, ACCENT, "150", "h-330", _alpha(dur, 0.0))
        t1 = _dt(l1, 50, "white", f"'170-30*(1-{e})'", "h-262",
                 _alpha(dur, 0.15))
        return ",".join([band, mark, t2, t1])

    if kind == "marker":
        x, y = _enter("pop", "(w-text_w)/2", "160", 0.0, 0.5)
        t1 = _dt(l1, 120, "white@0.92", x, y, _alpha(dur, 0.0, 0.5), False)
        bar = f"drawbox=x=iw/2-120:y=300:w=240:h=5:color={ACCENT}:t=fill"
        return ",".join([t1, bar])

    if kind == "list":
        # full-screen dark SLATE with a centered numbered list that reveals
        # row by row (matches the reference's CORE CIRCUIT card)
        items = [_clean(x) for x in (l2 or "").split("||") if x.strip()][:5]
        cnt = max(1, len(items))
        scrim = "drawbox=x=0:y=0:w=iw:h=ih:color=black@0.9:t=fill"
        titley = 300 - cnt * 8
        e0 = _ease(0.05, 0.5)
        title = _dt(l1, 66, "white", "(w-text_w)/2",
                    f"'{titley}+22*(1-{e0})'", _alpha(dur, 0.05, 0.5))
        bar = (f"drawbox=x=iw/2-150:y={titley+86}:w=300:h=5:"
               f"color={ACCENT}:t=fill")
        parts = [scrim, title, bar]
        bx, ry0 = 650, titley + 160
        for i, it in enumerate(items):
            ry = ry0 + i * 98
            d = 0.4 + i * 0.28
            e = _ease(d, 0.4)
            sx = f"-46*(1-{e})"
            badge = _dt("●", 58, ACCENT, f"'{bx}{sx}'", f"'{ry-8}'",
                        _alpha(dur, d))
            num = _dt(str(i + 1), 26, "white", f"'{bx+19}{sx}'",
                      f"'{ry+8}'", _alpha(dur, d), False)
            txt = _dt(it, 36, "white", f"'{bx+86}{sx}'", f"'{ry+2}'",
                      _alpha(dur, d))
            parts += [badge, num, txt]
        return ",".join(parts)

    if kind == "kw":
        # compact kinetic keyword chip, rotating through the four corners
        c = slot % 4
        e = _ease(0.05)
        if c == 0:
            x, y = f"'90-46*(1-{e})'", "150"
        elif c == 1:
            x, y = f"'w-text_w-90+46*(1-{e})'", "150"
        elif c == 2:
            x, y = f"'90-46*(1-{e})'", "h-170"
        else:
            x, y = f"'w-text_w-90+46*(1-{e})'", "h-170"
        return (f"drawtext=fontfile='{FONT}':text='{l1}':fontsize=40:"
                f"fontcolor=white:box=1:boxcolor={ACCENT}@0.9:boxborderw=16:"
                f"shadowcolor=black@0.55:shadowx=2:shadowy=2:"
                f"x={x}:y={y}:alpha={_alpha(dur, 0.05)}")

    if kind in ("stat", "lt", "ex"):
        right = (kind == "stat") or (kind in ("lt", "ex") and slot % 2)
        e = _ease(0.1)
        if kind == "stat":
            bx, bw, bh, by = "iw-780", 720, 156, "120"
            l1yv, l2yv, s1, s2, tx = "146", "228", 62, 26, "w-740"
        elif right:
            bx, bw, bh, by = "iw-780", 720, 130, "ih-230"
            l1yv, l2yv, s1, s2, tx = "h-214", "h-150", 46, 26, "w-740"
        else:
            bx, bw, bh, by = "60", 720, 130, "ih-230"
            l1yv, l2yv, s1, s2, tx = "h-214", "h-150", 46, 26, "99"
        panel = f"drawbox=x={bx}:y={by}:w={bw}:h={bh}:color=black@0.58:t=fill"
        accent = f"drawbox=x={bx}:y={by}:w=10:h={bh}:color={ACCENT}:t=fill"
        off = 44
        slide = f"+{off}*(1-{e})" if right else f"-{off}*(1-{e})"
        parts = [panel, accent,
                 _dt(l1, s1, "white", f"'{tx}{slide}'", l1yv,
                     _alpha(dur, 0.1))]
        if l2:
            parts.append(_dt(l2, s2, "0xD8D8D8", f"'{tx}{slide}'", l2yv,
                             _alpha(dur, 0.22)))
        return ",".join(parts)

    return _dt(l1, 40, "white", "(w-text_w)/2", "h-160", _alpha(dur, 0.0))
