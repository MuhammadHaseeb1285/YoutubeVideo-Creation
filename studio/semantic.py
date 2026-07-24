"""semantic - the meaning layer. Maps every footage category to a coarse
visual group, scores how well any shot fits a sentence, and knows which
exercises read the same on screen. This is what makes the visuals follow
the narration instead of the filenames. Subject-agnostic: works for any
celebrity, not one hardcoded person.
"""

# ------------------------------------------------------------ category groups
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
    """Explicit table first, then subject-agnostic keyword rules so ANY
    subject's footage (or a new label) still lands in the right group."""
    g = CAT_GROUP.get(cat)
    if g:
        return g
    c = (cat or "").lower()
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


# ------------------------------------------------------------ exercise family
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
    """How well a shot's visual group fits a sentence of this type."""
    if stype in EX_STYPES:
        tgt = STYPE_TARGET_GROUP.get(stype)
        if grp == "subject_gym":
            return 700
        if grp == tgt:
            return 620
        if grp == "coach":
            return 430
        if grp == "equipment":
            return 330
        if grp == "subject_phys":
            return 400
        if grp.startswith("ex_"):
            return 300 if stype == "workout" else 210
        if grp == "subject_movie":
            return 250
        if grp == "subject_talk":
            return 180
        if grp in ("food", "recovery"):
            return 40
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
    return {"subject_gym": 560, "subject_talk": 540, "subject_phys": 540,
            "subject_movie": 520, "coach": 320, "equipment": 150}.get(grp, 90)


def relevance(sh, stype, want_ex):
    """Positive semantic score of one shot for one sentence. The whole
    unused pool is ranked by this every pick."""
    grp = group_of(sh["cat"])
    ex = sh.get("ex")
    r = 0.0
    if want_ex:
        fam = EXERCISE_FAMILY.get(want_ex)
        if ex == want_ex:
            r += 1300
        elif ex and EXERCISE_FAMILY.get(ex) == fam:
            r += 660
        elif not ex and CAT_FAMILY.get(grp) == fam:
            r += 430
    r += topic_affinity(stype, grp)
    if grp in SUBJECT_GROUPS:
        r += 55
    r += 22 * sh.get("q", 1)
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
