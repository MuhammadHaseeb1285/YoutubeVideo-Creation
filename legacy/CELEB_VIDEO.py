#!/usr/bin/env python3
"""
CELEB_VIDEO - celebrity documentary launcher.

  Option 1: enter a celebrity NAME
      -> Claude API writes a documentary transcript, TTS narration
  Option 2: enter a TRANSCRIPT PATH
      -> your script is used as-is, TTS narration; you give the subject
         name so the footage searches match it
  Option 3: provide your own NARRATION AUDIO (file path or URL - local,
      YouTube, Google Drive, or direct link)
      -> the recording is transcribed locally with Whisper (no API, no
         keys), trailing silence trimmed, and a time-aligned transcript
         written. The film plays YOUR real voice and every sentence is
         pinned to its true spoken moment, so audio and video stay matched.

Everything downstream (scene detection, semantic per-sentence shot
selection, text animations, validation) is subject-agnostic - the
selector maps any subject's footage to the right topic, so the audio and
visuals match for whoever the documentary is about, not just one person.
"""

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent
CONFIG = ROOT / "config.json"


# ------------------------------------------------------------ helpers

def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def generate_transcript(name: str, minutes: int) -> tuple[Path, str]:
    """Write a documentary transcript of the requested length."""
    try:
        import anthropic
    except ImportError:
        subprocess.run([sys.executable, "-m", "pip", "install",
                        "anthropic", "-q"], check=True)
        import anthropic

    words = minutes * 152
    prompt = f"""Write a {minutes}-minute YouTube documentary narration
script about {name}'s physical transformation, workout routines, and
diet - the whole story of how they built and maintain their physique
across their career, including training for specific movies or roles
where publicly known.

Hard requirements:
- ~{words:,} words ({minutes}:00 at 152 wpm).
- First line must be exactly:  <!--COACH: full name-->  naming their
  best-publicly-known trainer/coach, or  <!--COACH: none-->  if none is
  publicly associated with them.
- Then a title line:  # {name} - Documentary Script ({minutes}-minute cut)
- Split into sections with headers of the form:
  ## [MM:SS-MM:SS] SECTION TITLE
  Cover at least: a hook, a sourcing disclaimer, baseline stats,
  the career/physique timeline (movies/roles and years), training
  philosophy, a weekly training split (day by day, concrete exercises),
  nutrition/diet plan, recovery, an honest "what you can copy" section,
  and an outro with a call to action.
- Attribute claims ("reported", "has said in interviews") - never invent
  private details, exact private numbers, or quotes. Spell numbers that
  will be narrated (e.g. "thirty-eight"), keep sentences speakable.
- No camera directions, no markdown besides the headers."""

    import os
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    key_file = ROOT / "anthropic_key.txt"
    if not key and key_file.exists():
        key = key_file.read_text().strip()
    if not key:
        print("\n[!] No Anthropic API key found.")
        print("    Transcript generation needs your own key from")
        print("    https://console.anthropic.com  (Settings > API keys)")
        key = input("    Paste API key (or ENTER to abort): ").strip()
        if not key:
            raise SystemExit("aborted - no API key")
        key_file.write_text(key)
        print(f"    saved to {key_file.name} for next time")
    client = anthropic.Anthropic(api_key=key)
    print("    calling Claude API (claude-opus-4-8)...")
    resp = client.messages.create(
        model="claude-opus-4-8",
        max_tokens=16000,
        thinking={"type": "adaptive"},
        messages=[{"role": "user", "content": prompt}],
    )
    if resp.stop_reason == "refusal":
        raise RuntimeError("transcript generation was refused")
    text = "".join(b.text for b in resp.content if b.type == "text").strip()

    coach = "none"
    m = re.match(r"\s*<!--COACH:\s*(.+?)\s*-->", text)
    if m:
        coach = m.group(1).strip()
        text = text[m.end():].lstrip()

    out = ROOT / f"transcript_{slugify(name)}.md"
    out.write_text(text, encoding="utf-8")
    print(f"    [OK] transcript: {out.name} ({len(text.split())} words)")
    print(f"    [OK] detected coach: {coach}")
    return out, ("" if coach.lower() == "none" else coach)


def build_queries(name: str, coach: str, slug: str) -> list:
    """Multiple targeted searches - never a single query."""
    q = [
        (f"{name} workout training routine", f"{slug}_gym_a"),
        (f"{name} gym training footage", f"{slug}_gym_b"),
        (f"{name} physique transformation explained", f"{slug}_gym_c"),
        (f"{name} training montage", f"{slug}_gym_d"),
        (f"{name} training behind the scenes movie", f"{slug}_bts_a"),
        (f"{name} behind the scenes on set", f"{slug}_bts_b"),
        (f"{name} movie preparation training", f"{slug}_bts_c"),
        (f"{name} interview body transformation", f"{slug}_int_a"),
        (f"{name} interview funny talk show", f"{slug}_int_b"),
        (f"{name} interview about fitness", f"{slug}_int_c"),
        (f"{name} press conference red carpet", f"{slug}_int_d"),
        (f"{name} diet nutrition what I eat", f"{slug}_diet_a"),
    ]
    if coach:
        q += [
            (f"{coach} trains {name}", f"{slug}_coach_a"),
            (f"{coach} trainer interview", f"{slug}_coach_b"),
        ]
    return q


def download_one(query: str, out: Path, attempts: int = 4) -> bool:
    """Download with retries. Each attempt takes a DIFFERENT search
    result, so one blocked/unavailable/filtered video cannot kill the
    slot. Duration filter relaxes on later attempts."""
    if out.exists() and out.stat().st_size > 500_000:
        return True
    filters = ["duration<720", "duration<1500", "duration<2400", None]
    for i in range(1, attempts + 1):
        flt = filters[min(i - 1, len(filters) - 1)]
        args = ["yt-dlp", "-f",
                "best[ext=mp4][height<=720]/best[ext=mp4]",
                "--no-playlist", "-o", str(out),
                "--playlist-items", str(i)]
        if flt:
            args += ["--match-filter", flt]
        args.append(f"ytsearch{attempts}:{query}")
        try:
            subprocess.run(args, capture_output=True, text=True,
                           timeout=240 + i * 60)
        except Exception:
            pass
        if out.exists() and out.stat().st_size > 500_000:
            return True
        for part in out.parent.glob(out.stem + "*"):   # clean partials
            try:
                part.unlink()
            except OSError:
                pass
        print(f"      attempt {i} failed - trying next search result")
    return False


def download(queries: list):
    out_dir = ROOT / "youtube_videos"
    out_dir.mkdir(exist_ok=True)
    got = 0
    for query, stem in queries:
        out = out_dir / f"{stem}.mp4"
        if out.exists():
            print(f"  [=] {stem} exists")
            got += 1
            continue
        print(f"  [*] {stem}: {query}")
        if download_one(query, out):
            print(f"      OK ({out.stat().st_size/1e6:.0f} MB)")
            got += 1
        else:
            print("      FAILED after all retries - continuing")
    print(f"[OK] {got}/{len(queries)} videos ready")


# ------------------------------------------------------------ main

def main():
    print("\n" + "=" * 70)
    print("CELEBRITY DOCUMENTARY BUILDER")
    print("=" * 70)
    print("\n  1) Enter a celebrity name   (transcript is generated, TTS voice)")
    print("  2) Enter a transcript path  (your script is used, TTS voice)")
    print("  3) Provide narration audio  (your real recording - "
          "transcribed & synced)\n")
    choice = input("Choose 1, 2 or 3: ").strip()
    has_audio = False

    if choice == "3":
        src = input("Narration audio/video (file path or URL): ").strip()
        if not src:
            print("[!] nothing given")
            return False
        name = input("Celebrity name (for footage searches): ").strip()
        coach = input("Coach/trainer name (ENTER if none): ").strip()
        slug = slugify(name) or "subject"
        print("\n[1/4] Transcribing your narration (real audio -> "
              "time-aligned transcript)...")
        import NARRATION_FROM_AUDIO
        transcript = NARRATION_FROM_AUDIO.build_narration(
            src, slug, subject=name)
        has_audio = True
    elif choice == "1":
        name = input("Celebrity name: ").strip()
        if not name:
            print("[!] no name given")
            return False
        m = input("Video duration in minutes [17]: ").strip()
        minutes = int(m) if m.isdigit() and 3 <= int(m) <= 60 else 17
        print(f"\n[1/4] Generating {minutes}-minute transcript for "
              f"{name}...")
        transcript, coach = generate_transcript(name, minutes)
        extra = input(f"Coach detected: '{coach or 'none'}' - press ENTER "
                      "to accept or type a correction: ").strip()
        if extra:
            coach = extra
    elif choice == "2":
        path = input("Transcript file or URL: ").strip().strip('"')
        if path.lower().startswith(("http://", "https://")):
            import requests
            print("    downloading transcript...")
            transcript = ROOT / "transcript_downloaded.md"
            transcript.write_text(
                requests.get(path, timeout=30).text, encoding="utf-8")
        else:
            transcript = Path(path)
        if not transcript.exists():
            print(f"[!] not found: {transcript}")
            return False
        name = input("Celebrity name (for footage searches): ").strip()
        coach = input("Coach/trainer name (ENTER if none): ").strip()
        print(f"\n[1/4] Using transcript: {transcript}")
    else:
        print("[!] invalid choice")
        return False

    if has_audio:
        voice = ""            # real recording is used; no TTS voice needed
        print("\n[OK] Using your real narration (no TTS voice).")
    else:
        print("\nNarrator voice (a professional documentary voice - real"
              " celebrity voices cannot be cloned):")
        print("  1) Male   (en-US-ChristopherNeural)")
        print("  2) Female (en-US-JennyNeural)")
        print("  3) Male UK (en-GB-RyanNeural)")
        v = input("Choose 1-3 [1]: ").strip()
        voice = {"2": "en-US-JennyNeural",
                 "3": "en-GB-RyanNeural"}.get(v, "en-US-ChristopherNeural")

    slug = slugify(name)
    CONFIG.write_text(json.dumps({
        "subject": name,
        "coach": coach,
        "slug": slug,
        "voice": voice,
        "transcript": str(transcript),
        "output": f"{slug.upper()}_FINAL.mp4",
    }, indent=2))
    print(f"[OK] config.json written (subject={name}, coach="
          f"{coach or 'none'})")

    print(f"\n[2/4] Downloading footage - "
          "multiple searches matched to the subject...")
    download(build_queries(name, coach, slug))

    print("\n[3/4] Scene detection + classification sheets for new "
          "footage...")
    subprocess.run([sys.executable, str(ROOT / "INDEX_NEW.py")])

    print("\n[4/4] Building the documentary...")
    r = subprocess.run([sys.executable,
                        str(ROOT / "GENERATE_FINAL_VIDEO.py")])
    return r.returncode == 0


if __name__ == "__main__":
    raise SystemExit(0 if main() else 1)
