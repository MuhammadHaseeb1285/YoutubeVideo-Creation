"""vision - classify what is ACTUALLY IN each detected scene, so the editor
matches footage to the narration by real content instead of filenames.

For every scene we grab a representative frame, tile the frames into labeled
contact sheets, and send each sheet to Gemini Vision. Gemini returns a
category per scene (subject-talking, subject-gym, chest, food, ...), plus a
usability flag that drops graphics / text slides / subscribe screens /
watermarked junk. The result is written to vision_tags.json + sheets_map.json,
which the shot database already reads.

This mirrors the reference project's AUTO_TAGS step and is what lifts
audio-visual sync from "filename-approximate" to content-accurate.

Needs a Google Gemini API key (free tier at aistudio.google.com/apikey),
read from GEMINI_API_KEY or gemini_key.txt.
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

from . import settings, logs

MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash")
COLS, ROWS = 4, 5
CELL_W, CELL_H = 320, 180
PER_SHEET = COLS * ROWS
# bump when the classification prompt changes so stale cached tags
# (made with a weaker prompt) are re-generated instead of reused
TAGS_VERSION = 3


class NoVisionKey(Exception):
    """No Gemini API key available for content classification."""


def _key():
    k = os.environ.get("GEMINI_API_KEY", "").strip()
    if not k:
        kf = settings.ROOT / "gemini_key.txt"
        if kf.exists():
            k = kf.read_text(encoding="utf-8").strip()
    return k


def _photo_is_portrait(img_path, subject, client):
    """Ask Gemini whether a candidate image is a real portrait of a person
    (not a graphic / poster / text image / logo / wrong-topic picture)."""
    try:
        from PIL import Image
        r = client.models.generate_content(
            model=MODEL,
            contents=[f"Answer only YES or NO. Is this image a clear photo "
                      f"of a single real person (a portrait or candid shot "
                      f"showing their face) - suitable as a reference photo "
                      f"of the public figure '{subject}'? Answer NO for "
                      f"graphics, posters, text images, logos, calendars, "
                      f"cartoons or group photos.",
                      Image.open(img_path)])
        return "YES" in (r.text or "").upper()
    except Exception:
        return True     # if validation fails, don't block the pipeline


def _subject_photo(subject: str, hint: str = "", client=None, image_url: str = ""):
    """Download a verified reference photo of the celebrity (their visual
    profile). If image_url provided, use that; else Wikipedia lead image,
    YouTube channel avatar, DuckDuckGo, then Bing image results with a
    profession-qualified query; each candidate is validated as a real
    portrait before being accepted."""
    out = settings.CACHE / "subject_ref.jpg"
    if out.exists() and out.stat().st_size > 5000:
        return out
    import requests
    ua = {"User-Agent": "DocumentaryStudio/1.0"}
    urls = []
    if image_url:
        urls.append(image_url)
    try:
        r = requests.get(
            "https://en.wikipedia.org/api/rest_v1/page/summary/"
            + subject.replace(" ", "_"), headers=ua, timeout=15).json()
        for k in ("originalimage", "thumbnail"):
            u = (r.get(k) or {}).get("source")
            if u:
                urls.append(u)
    except Exception:
        pass
    bua = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
           "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 "
           "Safari/537.36", "Accept-Language": "en"}
    # For creators the most reliable photo on the internet is their own
    # YouTube channel avatar - grab og:image from the channels behind the
    # top search results for their name.
    try:
        import re as _re
        r = subprocess.run(
            ["yt-dlp", "--flat-playlist", "--print", "channel_url",
             f"ytsearch4:{subject}"],
            capture_output=True, text=True, timeout=90)
        seen = set()
        for cu in [l.strip() for l in (r.stdout or "").splitlines()
                   if l.strip().startswith("http")]:
            if cu in seen:
                continue
            seen.add(cu)
            try:
                page = requests.get(cu, headers=bua, timeout=15).text
                m = _re.search(r'property="og:image" content="([^"]+)"',
                               page)
                if m:
                    urls.append(m.group(1))
            except Exception:
                continue
    except Exception:
        pass
    # Image search (DuckDuckGo images API), profession-qualified to avoid
    # homonyms (e.g. the Islamic month 'Rajab')
    try:
        import re as _re
        q = f"{subject} {hint}".strip()
        s = requests.Session()
        s.headers.update(bua)
        r = s.get("https://duckduckgo.com/", params={"q": q}, timeout=15)
        m = (_re.search(r"vqd=([\d-]+)", r.text)
             or _re.search(r"vqd='([\d-]+)'", r.text)
             or _re.search(r'vqd="([\d-]+)"', r.text))
        if m:
            r2 = s.get("https://duckduckgo.com/i.js",
                       params={"l": "us-en", "o": "json", "q": q,
                               "vqd": m.group(1)}, timeout=15)
            for it in (r2.json().get("results") or [])[:6]:
                u = it.get("image", "")
                if u:
                    urls.append(u)
    except Exception:
        pass
    # last resort: Bing image results
    try:
        import html as _html
        import json as _json
        import re as _re
        q = f'"{subject}" {hint} face photo'.replace("  ", " ")
        r = requests.get("https://www.bing.com/images/search",
                         params={"q": q}, headers=bua, timeout=15)
        for attr in _re.findall(r'class="iusc"[^>]*m="([^"]+)"', r.text)[:8]:
            try:
                mu = _json.loads(_html.unescape(attr)).get("murl", "")
                if mu.lower().split("?")[0].endswith((".jpg", ".jpeg",
                                                      ".png", ".webp")):
                    urls.append(mu)
            except Exception:
                continue
    except Exception:
        pass
    tmp = settings.CACHE / "_ref_candidate.jpg"
    for u in urls:
        try:
            img = requests.get(u, headers=ua, timeout=15).content
            if len(img) <= 5000:
                continue
            tmp.write_bytes(img)
            if client is not None and not _photo_is_portrait(tmp, subject,
                                                             client):
                logs.log(f"  rejected non-portrait candidate: {u[:60]}")
                continue
            tmp.replace(out)
            logs.log(f"vision: subject reference photo saved "
                     f"({len(img)//1000} KB)")
            return out
        except Exception:
            continue
    try:
        if tmp.exists():
            tmp.unlink()                 # never leave a rejected candidate
    except OSError:
        pass
    logs.log("vision: no reference photo found - identity check will rely "
             "on Gemini's own knowledge of the subject", "error")
    return None


def _scenes_from_index():
    """[(cell_id, source_stem, scene_index, src_path, mid_time)] for every
    usable detected scene."""
    if not settings.SHOT_INDEX.exists():
        return []
    cache = json.loads(settings.SHOT_INDEX.read_text())
    out, cid = [], 0
    for src_path, meta in cache.items():
        src = Path(src_path)
        if not src.exists():
            continue
        dur = meta["duration"]
        cuts = [c for c in meta["cuts"] if 0.5 < c < dur - 0.5]
        bounds = [0.0] + cuts + [dur]
        for si in range(len(bounds) - 1):
            a, b = bounds[si], bounds[si + 1]
            if b - a < settings.MIN_SHOT:
                continue
            out.append((cid, src.stem, si, src, (a + b) / 2))
            cid += 1
    return out


def _grab(src, t, out):
    subprocess.run(
        ["ffmpeg", "-ss", f"{t:.2f}", "-i", str(src), "-frames:v", "1",
         "-vf", f"scale={CELL_W}:{CELL_H}:force_original_aspect_ratio="
         f"increase,crop={CELL_W}:{CELL_H}", "-y", str(out)],
        capture_output=True, timeout=30)


def build_contact_sheets(progress_cb=None):
    """Extract one frame per scene, tile into labeled 4x5 sheets, and write
    sheets_map.json. Returns (sheet_paths, cells)."""
    from PIL import Image, ImageDraw, ImageFont
    scenes = _scenes_from_index()
    sheets_dir = settings.CACHE / "sheets"
    frames_dir = settings.CACHE / "frames"
    sheets_dir.mkdir(parents=True, exist_ok=True)
    frames_dir.mkdir(parents=True, exist_ok=True)

    try:
        font = ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", 20)
    except Exception:
        font = ImageFont.load_default()

    frames, cells = [], []
    for i, (cid, stem, si, src, mid) in enumerate(scenes):
        fp = frames_dir / f"f_{cid}.jpg"
        _grab(src, mid, fp)
        if fp.exists() and fp.stat().st_size > 500:
            frames.append((cid, fp))
            cells.append({"id": cid, "source": stem, "scene": si})
        if progress_cb and i % 20 == 0:
            progress_cb(40 * i / max(1, len(scenes)), f"frames {i}/{len(scenes)}")

    sheet_paths = []
    for s in range(0, len(frames), PER_SHEET):
        batch = frames[s:s + PER_SHEET]
        sheet = Image.new("RGB", (COLS * CELL_W, ROWS * CELL_H), (12, 12, 16))
        d = ImageDraw.Draw(sheet)
        for i, (cid, fp) in enumerate(batch):
            try:
                cell = Image.open(fp).convert("RGB").resize((CELL_W, CELL_H))
            except Exception:
                continue
            x, y = (i % COLS) * CELL_W, (i // COLS) * CELL_H
            sheet.paste(cell, (x, y))
            d.rectangle([x, y, x + 70, y + 26], fill=(210, 0, 20))
            d.text((x + 6, y + 3), f"#{cid}", fill="white", font=font)
        sp = sheets_dir / f"sheet_{s // PER_SHEET}.jpg"
        sheet.save(sp, quality=85)
        sheet_paths.append((sp, [c for c, _ in batch]))

    settings.SHEETS_MAP.write_text(json.dumps(cells))
    return sheet_paths, cells


def _prompt(subject, coach, ids, has_ref):
    coach_line = (f"COACH/TRAINER (the actual trainer of {subject}, a "
                  f"different specific person):\n  coach_gym, coach_talk\n"
                  ) if coach else ""
    ref_line = (f"The FIRST image is a reference photo of {subject}, to "
                f"HELP you recognise them. Combine it with your own "
                f"knowledge of {subject}: their appearance can differ a lot "
                f"across years, films and settings (younger/older, beard or "
                f"clean-shaven, different hair, costumes, on stage, in a "
                f"movie role). The SECOND image is the grid to classify.\n\n"
                ) if has_ref else ""
    return f"""You are labeling frames from a documentary about {subject}.
{ref_line}The grid image contains video frames, read left-to-right, top-to-
bottom. Each frame has a red "#<id>" label in its top-left corner.

THE MOST IMPORTANT RULE - SUBJECT DOMINANCE:
Use a SUBJECT category when {subject} (at any age / in any look, including
movie roles) is the MAIN person in the frame. Mark a frame "x" if the
dominant person is CLEARLY someone else - an interviewer, podcast host,
another guest, a reporter, an audience member, or an unrelated person - or
if {subject} is absent, tiny, or only barely visible in the background. If
a frame shows {subject} together with others but {subject} is the focus,
that still counts as SUBJECT footage.

Classify EACH labeled frame using exactly one category:

SUBJECT ({subject}) is the main person, talking / posing / in public:
  ryan_interview, ryan_press, ryan_event
SUBJECT ({subject}) training or showing physique:
  ryan_gym, ryan_photoshoot, ryan_abs, ryan_shirtless
SUBJECT ({subject}) other (film role, behind the scenes, candid):
  ryan_movie, ryan_bts, ryan_photo, ryan_outdoor, ryan_home
{coach_line}GENERIC EXERCISE B-ROLL (a non-famous person training, use only as backup):
  chest, back, legs, shoulders, arms, cardio, equipment, recovery
NUTRITION (food, meals, cooking, supplements):
  food
UNUSABLE - mark "x":
  graphics, text slides, titles, logos, channel watermarks, subscribe/like
  screens, social-media or Shorts/Reels UI, cartoons, OR any frame whose main
  person is NOT {subject} (interviewer/host/guest/audience/other), OR where
  {subject} is absent or barely visible.

For each id return a 4-item array: [category, gender, use, quality]
  - category: one exact string above, or "x"
  - gender: "m", "f", or "n"
  - use: 1 if usable AND {subject} clearly dominates (or it is pure B-roll/
         food); 0 for anything "x"
  - quality: 0 (poor/blurry/low-res/watermarked), 1 (ok), 2 (clean, sharp,
         cinematic, {subject} large and centred)

The ids on this sheet are: {ids}
Return ONLY a JSON object mapping each id (as a string) to its 4-item array."""


def auto_tag(subject, coach="", progress_cb=None, hint="", image_url: str = ""):
    """Classify every scene's real content with Gemini. Writes
    vision_tags.json. Returns the number of scenes tagged."""
    key = _key()
    if not key:
        raise NoVisionKey("no GEMINI_API_KEY / gemini_key.txt")
    # reuse cached tags only when made with the CURRENT prompt version
    scenes = _scenes_from_index()
    if settings.VISION_TAGS.exists() and settings.SHEETS_MAP.exists():
        try:
            existing = json.loads(settings.VISION_TAGS.read_text())
            ver = existing.pop("__version__", 0)
            if scenes and ver == TAGS_VERSION \
                    and len(existing) >= len(scenes) * 0.9:
                logs.log(f"vision: using cached content tags for "
                         f"{len(existing)} scenes (v{ver})")
                return len(existing)
            if ver != TAGS_VERSION:
                logs.log("vision: cached tags are from an older prompt - "
                         "re-classifying with identity verification")
        except Exception:
            pass
    try:
        from google import genai
    except ImportError:
        subprocess.run([sys.executable, "-m", "pip", "install",
                        "google-genai", "-q"], check=True)
        from google import genai
    from PIL import Image

    sheet_paths, cells = build_contact_sheets(progress_cb)
    if not sheet_paths:
        raise RuntimeError("no scenes to classify")
    client = genai.Client(api_key=key)
    ref_path = _subject_photo(subject, hint, client, image_url)
    ref_img = Image.open(ref_path) if ref_path else None

    def _classify(sp, ids, use_ref):
        contents = [_prompt(subject, coach, ids, use_ref)]
        if use_ref:
            contents.append(ref_img)
        contents.append(Image.open(sp))
        last = None
        for attempt in range(3):
            try:
                resp = client.models.generate_content(model=MODEL,
                                                      contents=contents)
                raw = (resp.text or "").strip()
                m = re.search(r"\{.*\}", raw, re.S)
                if m:
                    out = {}
                    for k, v in json.loads(m.group(0)).items():
                        if isinstance(v, list) and len(v) >= 4:
                            out[str(k)] = [v[0], v[1], int(v[2]), int(v[3])]
                    return out
                last = "no JSON in response"
            except Exception as e:
                last = e
                import time
                time.sleep(8 * (attempt + 1))    # back off on rate limits
        raise RuntimeError(str(last))

    tags = {}
    import time
    for i, (sp, ids) in enumerate(sheet_paths):
        try:
            part = _classify(sp, ids, ref_img is not None)
            usable = sum(1 for v in part.values() if v[2])
            # a full sheet with ZERO usable cells usually means the identity
            # match was too strict - retry once without the reference photo
            if ref_img is not None and usable == 0 and len(part) >= 10:
                part2 = _classify(sp, ids, False)
                if sum(1 for v in part2.values() if v[2]) > 0:
                    part = part2
            tags.update(part)
        except Exception as e:
            logs.log(f"  vision sheet {i} failed: {e}", "error")
        if progress_cb:
            progress_cb(40 + 60 * (i + 1) / len(sheet_paths),
                        f"classified sheet {i + 1}/{len(sheet_paths)}")
        time.sleep(2.0)                       # stay under free-tier RPM
    out = {"__version__": TAGS_VERSION}
    out.update(tags)
    settings.VISION_TAGS.write_text(json.dumps(out))
    usable = sum(1 for v in tags.values() if v[2])
    logs.log(f"vision: {len(tags)} scenes classified, {usable} usable "
             f"({len(tags) - usable} rejected: wrong person / junk / "
             f"low quality)")
    return len(tags)
