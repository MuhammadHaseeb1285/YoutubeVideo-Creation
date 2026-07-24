"""settings - all paths, the project config, and shared constants.

Every other module imports paths from here so the folder layout lives in
exactly one place.
"""

import json
from pathlib import Path

# ------------------------------------------------------------ folder layout
# Everything for one subject lives under  projects/<slug>/  so each celebrity
# is a self-contained folder (its footage, transcript, narration, cache and
# final video). set_project(slug) repoints all the paths below; every module
# reads them as attributes, so switching project switches the whole workspace.
ROOT = Path(__file__).resolve().parent.parent

PROJECTS = ROOT / "projects"              # one folder per subject
LOG_DIR = ROOT / "logs"                   # shared app logs
CONFIG = ROOT / "config.json"             # active-project pointer + settings

# these are (re)assigned by set_project(); declared here for import safety
PROJECT_SLUG = "default"
PROJECT_DIR = PROJECTS / PROJECT_SLUG
ASSETS = ASSETS_VIDEO = ASSETS_IMAGE = ASSETS_AUDIO = None
CACHE = OUTPUT = TRANSCRIPTS = None
SHOT_INDEX = SHEETS_MAP = VISION_TAGS = TIMING = TIMELINE = None


def set_project(slug: str):
    """Point every data path at projects/<slug>/. Returns the project dir."""
    global PROJECT_SLUG, PROJECT_DIR, ASSETS, ASSETS_VIDEO, ASSETS_IMAGE
    global ASSETS_AUDIO, CACHE, OUTPUT, TRANSCRIPTS
    global SHOT_INDEX, SHEETS_MAP, VISION_TAGS, TIMING, TIMELINE
    PROJECT_SLUG = slug or "default"
    base = PROJECTS / PROJECT_SLUG
    PROJECT_DIR = base
    ASSETS = base / "assets"
    ASSETS_VIDEO = ASSETS / "videos"
    ASSETS_IMAGE = ASSETS / "images"
    ASSETS_AUDIO = ASSETS / "audio"
    CACHE = base / "cache"
    OUTPUT = base / "output"
    TRANSCRIPTS = base / "transcripts"
    SHOT_INDEX = CACHE / "shot_index.json"
    SHEETS_MAP = CACHE / "sheets_map.json"
    VISION_TAGS = CACHE / "vision_tags.json"
    TIMING = CACHE / "narration_timing.json"
    TIMELINE = CACHE / "timeline.json"
    return base

VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac"}

# ------------------------------------------------------------ edit constants
MAX_PIECE = 4.0            # a shot never exceeds 4 seconds
MIN_SHOT = 1.4
SEG_EVERY = 7             # one usable segment per ~7s of a long scene
SEG_MAX = 12
SCENE_SPACING = 12        # min pieces between two segments of one scene
FONT = "C\\:/Windows/Fonts/arialbd.ttf"
ACCENT = "0xE50914"       # brand red used across the motion graphics

DEFAULT_VOICE = "en-US-ChristopherNeural"   # deep, authoritative narrator

# validation thresholds (the render is refused below these)
MIN_TOPIC_MATCH = 92
MIN_EXERCISE_SYNC = 85

# Advanced, per-project controls the dashboard exposes. Stored under
# config["settings"] so they change behaviour without code edits.
DEFAULT_SETTINGS = {
    "narration_profile": "auto",   # auto | energetic | motivational | ...
    "narration_pace": 0,           # -3..+3 slider steps
    "narration_energy": 0,         # -3..+3
    "emotional_intensity": 2,      # 0..4 (reserved / UI)
    "confidence": 3,               # 0..4 (reserved / UI)
    "music_volume": 0,             # 0..100 (reserved)
    "mograph_intensity": "high",   # high | medium | minimal
    "transition_speed": "normal",  # slow | normal | fast
    "max_clip": 4.0,               # seconds, hard cap per shot
    "text_anim_style": "cinematic",  # cinematic | fast | minimal
    "theme": "midnight",           # midnight | graphite | noir
}

_DEFAULT_CONFIG = {
    "subject": "",
    "coach": "",
    "slug": "subject",
    "voice": DEFAULT_VOICE,
    "transcript": "",
    "output": "DOCUMENTARY.mp4",
    "settings": dict(DEFAULT_SETTINGS),
}


def ensure_dirs():
    for d in (ASSETS_VIDEO, ASSETS_IMAGE, ASSETS_AUDIO, CACHE, OUTPUT,
              TRANSCRIPTS, PROJECTS, LOG_DIR):
        d.mkdir(parents=True, exist_ok=True)


def list_projects():
    """Subject folders that exist, newest first, with a couple of stats."""
    out = []
    if PROJECTS.exists():
        for d in PROJECTS.iterdir():
            if not d.is_dir():
                continue
            vids = d / "assets" / "videos"
            n = len(list(vids.glob("*"))) if vids.exists() else 0
            finals = list((d / "output").glob("*.mp4")) \
                if (d / "output").exists() else []
            out.append({"slug": d.name, "videos": n,
                        "has_output": bool(finals),
                        "mtime": d.stat().st_mtime})
    return sorted(out, key=lambda p: p["mtime"], reverse=True)


def load_config() -> dict:
    cfg = dict(_DEFAULT_CONFIG)
    cfg["settings"] = dict(DEFAULT_SETTINGS)
    if CONFIG.exists():
        try:
            saved = json.loads(CONFIG.read_text(encoding="utf-8"))
            st = {**DEFAULT_SETTINGS, **(saved.get("settings") or {})}
            cfg.update(saved)
            cfg["settings"] = st
        except Exception:
            pass
    return cfg


def load_settings() -> dict:
    return load_config()["settings"]


def save_settings(patch: dict):
    cfg = load_config()
    cfg["settings"] = {**cfg["settings"], **(patch or {})}
    save_config(cfg)
    return cfg["settings"]


def save_config(cfg: dict):
    CONFIG.write_text(json.dumps(cfg, indent=2), encoding="utf-8")


def voiceover_path(slug: str) -> Path:
    return ASSETS_AUDIO / f"voiceover_{slug}.mp3"


def output_path(cfg: dict) -> Path:
    return OUTPUT / cfg.get("output", "DOCUMENTARY.mp4")


# initialise paths to the last active project (or default) at import time
def _init_active():
    slug = "default"
    if CONFIG.exists():
        try:
            slug = json.loads(CONFIG.read_text(encoding="utf-8")) \
                .get("slug") or "default"
        except Exception:
            pass
    set_project(slug)


_init_active()
