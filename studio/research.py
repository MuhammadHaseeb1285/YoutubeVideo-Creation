"""research - look the subject up from real sources BEFORE writing anything.

Given a name, query Wikipedia (no API key) for a real biography, classify
what kind of public figure they are (youtuber / actor / musician / athlete
/ entrepreneur / ...), and pull the facts the transcript is built from.
Footage searches are then tailored to that type, so a YouTuber gets channel
and interview footage, an actor gets film and red-carpet footage, etc. -
never a hardcoded workout documentary.
"""

import re

from . import logs

_UA = {"User-Agent": "DocumentaryStudio/1.0 (research)"}
_WIKI = "https://en.wikipedia.org"

# type -> keywords that appear in the Wikipedia description / categories
TYPE_KEYWORDS = [
    ("youtuber", ["youtuber", "youtube", "streamer", "twitch",
                  "internet personality", "content creator", "vlogger",
                  "social media", "influencer", "tiktok", "podcaster"]),
    ("musician", ["singer", "rapper", "musician", "songwriter", "band",
                  "record producer", "dj", "vocalist", "composer"]),
    ("actor", ["actor", "actress", "filmmaker", "director", "screenwriter",
               "comedian"]),
    ("athlete", ["footballer", "basketball", "boxer", "wrestler", "athlete",
                 "player", "sportsperson", "tennis", "cricketer", "mma",
                 "racing driver", "gymnast", "sprinter"]),
    ("entrepreneur", ["entrepreneur", "businessman", "businesswoman", "ceo",
                      "founder", "investor", "billionaire", "executive"]),
]


def _get(path, params, timeout=15, attempts=3):
    import time
    import requests
    last = None
    for i in range(attempts):
        try:
            r = requests.get(_WIKI + path, params=params, headers=_UA,
                             timeout=timeout)
            r.raise_for_status()
            return r.json()
        except Exception as e:      # transient throttle / network blip
            last = e
            time.sleep(0.6 * (i + 1))
    raise last


def classify(description: str, categories: list, text: str) -> str:
    # The Wikipedia one-line description lists the PRIMARY role first
    # ("actor and singer" -> actor). So the type whose keyword appears
    # earliest in the description wins.
    desc = (description or "").lower()
    best_type, best_pos = None, 10 ** 9
    for typ, keys in TYPE_KEYWORDS:
        for k in keys:
            p = desc.find(k)
            if 0 <= p < best_pos:
                best_pos, best_type = p, typ
    if best_type:
        return best_type
    blob = " ".join((categories or []) + [text[:400]]).lower()
    for typ, keys in TYPE_KEYWORDS:
        if any(k in blob for k in keys):
            return typ
    return "public figure"


_FITNESS_KW = [
    "workout", "training", "trained", "train ", "gym", "exercise", "reps",
    "sets", "bench", "squat", "deadlift", "press", "curl", "cardio", "hiit",
    "muscle", "physique", "body fat", "bodyfat", "shredded", "bulk", "cut ",
    "lean", "diet", "nutrition", "eats", "eating", "meal", "protein",
    "carb", "calorie", "macro", "supplement", "trainer", "coach", "routine",
    "split", "lifting", "weights", "fitness", "pounds", "abs", "core",
    "conditioning", "recovery", "pull-up", "push-up", "lunge", "row ",
    "fat loss", "transformation", "shape", "ripped", "regimen",
]
_FIT_SITES = ["menshealth", "muscleandfitness", "mensjournal", "gq.com",
              "coachmag", "manofmany", "healthline", "esquire", "shape.com",
              "womenshealthmag", "muscleandhealth", "thefitnesstribe",
              "generationiron", "boxrox", "hindustantimes", "ndtv",
              "popsugar", "self.com", "eatthis"]


def _is_fitness(text: str) -> bool:
    t = text.lower()
    return sum(1 for k in _FITNESS_KW if k in t) >= 1


def _extract_text(html_str: str) -> str:
    import html
    import re
    html_str = re.sub(r"(?is)<(script|style|nav|footer|header|aside|form)"
                      r"[^>]*>.*?</\1>", " ", html_str)
    ps = re.findall(r"(?is)<p[^>]*>(.*?)</p>", html_str)
    txt = " ".join(re.sub(r"(?s)<[^>]+>", "", p) for p in ps)
    txt = html.unescape(txt)
    # normalise smart punctuation to ASCII (clean for TTS + on-screen text)
    for a, b in (("’", "'"), ("‘", "'"), ("“", '"'),
                 ("”", '"'), ("—", " - "), ("–", "-"),
                 ("…", "..."), (" ", " "), ("�", "'")):
        txt = txt.replace(a, b)
    return re.sub(r"\s+", " ", txt).strip()


def fetch_fitness_content(name: str, max_articles: int = 4) -> list:
    """Search fitness publications for the subject's real workout & diet
    coverage and return extracted article text. No API key."""
    import re
    import requests
    q = f"{name} workout routine and diet plan"
    urls = []
    try:
        r = requests.post("https://html.duckduckgo.com/html/",
                          data={"q": q}, headers=_UA, timeout=20)
        for href in re.findall(r'href="(https?://[^"]*uddg=[^"]+)"', r.text):
            m = re.search(r"uddg=([^&]+)", href)
            if m:
                urls.append(requests.utils.unquote(m.group(1)))
        # plain result links too
        urls += re.findall(r'class="result__a"[^>]*href="(https?://[^"]+)"',
                           r.text)
    except Exception as ex:
        logs.log(f"fitness search failed: {ex}", "error")
    # prefer known fitness / entertainment outlets
    urls = list(dict.fromkeys(urls))
    urls.sort(key=lambda u: 0 if any(s in u.lower() for s in _FIT_SITES)
              else 1)
    out = []
    for u in urls[:10]:
        if len(out) >= max_articles:
            break
        try:
            a = requests.get(u, headers=_UA, timeout=15)
            a.encoding = a.apparent_encoding or "utf-8"
            txt = _extract_text(a.text)
            if len(txt.split()) > 150 and _is_fitness(txt):
                out.append({"url": u, "text": txt})
                logs.log(f"  fitness source: {u[:70]} "
                         f"({len(txt.split())} words)")
        except Exception:
            pass
    return out


def research_subject(name: str) -> dict:
    """Return a real, sourced profile of the subject (or a minimal stub)."""
    out = {"name": name, "title": name, "type": "public figure",
           "description": "", "summary": "", "intro": "", "url": "",
           "sourced": False}
    try:
        # 1. find the best-matching article title
        arr = _get("/w/api.php", {"action": "opensearch", "search": name,
                                  "limit": 1, "namespace": 0,
                                  "format": "json"})
        title = arr[1][0] if arr and arr[1] else name
        # 2. short summary + one-line description
        s = _get(f"/api/rest_v1/page/summary/{title.replace(' ', '_')}", {})
        desc = s.get("description", "")
        summary = s.get("extract", "")
        url = s.get("content_urls", {}).get("desktop", {}).get("page", "")
        # 3. full intro (real biography prose)
        e = _get("/w/api.php", {"action": "query", "prop": "extracts",
                                "exintro": 1, "explaintext": 1,
                                "redirects": 1, "titles": title,
                                "format": "json"})
        intro = next(iter(e["query"]["pages"].values())).get("extract", "")
        # 4. categories (help classify)
        c = _get("/w/api.php", {"action": "query", "prop": "categories",
                                "cllimit": 40, "titles": title,
                                "format": "json"})
        cats = [x["title"].replace("Category:", "")
                for x in next(iter(c["query"]["pages"].values()))
                .get("categories", [])]
        typ = classify(desc, cats, intro or summary)
        out.update({"title": title, "type": typ, "description": desc,
                    "summary": summary, "intro": intro or summary,
                    "url": url, "sourced": bool(intro or summary)})
        logs.log(f"research: {title} -> {typ} ({desc or 'no description'})")
    except Exception as ex:
        logs.log(f"research: lookup failed ({ex}); using generic profile",
                 "error")
    return out


# ------------------------------------------------------------ footage queries
def build_queries(name: str, coach: str, slug: str,
                  ctype: str = "public figure") -> list:
    """Footage searches for a fitness / body-transformation documentary:
    the subject training, their physique across roles, interviews about
    fitness, and the coach - plus a few type-specific project searches so
    the film can show the moments that required each transformation."""
    q = [
        (f"{name} workout training routine", f"{slug}_gym_a"),
        (f"{name} gym training footage", f"{slug}_gym_b"),
        (f"{name} body transformation", f"{slug}_gym_c"),
        (f"{name} physique training", f"{slug}_gym_d"),
        (f"{name} training behind the scenes", f"{slug}_bts_a"),
        (f"{name} transformation before after", f"{slug}_bts_b"),
        (f"{name} interview fitness training", f"{slug}_int_a"),
        (f"{name} interview", f"{slug}_int_b"),
        (f"{name} diet nutrition what he eats", f"{slug}_diet_a"),
    ]
    extra = {
        "actor": [(f"{name} movie role training", f"{slug}_bts_c"),
                  (f"{name} shirtless movie scene", f"{slug}_film_a"),
                  (f"{name} red carpet", f"{slug}_int_c")],
        "athlete": [(f"{name} training session", f"{slug}_gym_e"),
                    (f"{name} highlights", f"{slug}_film_a"),
                    (f"{name} workout", f"{slug}_gym_f")],
        "musician": [(f"{name} tour rehearsal fitness", f"{slug}_bts_c"),
                     (f"{name} live performance", f"{slug}_film_a")],
        "youtuber": [(f"{name} fitness challenge", f"{slug}_gym_e"),
                     (f"{name} body transformation video", f"{slug}_bts_c"),
                     (f"{name} podcast", f"{slug}_int_c")],
        "entrepreneur": [(f"{name} fitness routine", f"{slug}_gym_e"),
                         (f"{name} interview health", f"{slug}_int_c")],
    }
    q += extra.get(ctype, [(f"{name} training", f"{slug}_gym_e"),
                           (f"{name} public appearance", f"{slug}_int_c")])
    if coach:
        q += [(f"{coach} trains {name}", f"{slug}_coach_a"),
              (f"{coach} trainer interview", f"{slug}_coach_b")]
    return q
