#!/usr/bin/env python3
"""
NARRATION_FROM_AUDIO - turn a real narration recording into the project's
narration + a time-aligned transcript, for ANY subject.

Give it an audio OR video file (local path, YouTube / Google Drive / direct
URL). It:
  1. pulls the audio out,
  2. transcribes it locally with Whisper (no API, no keys) capturing the
     real spoken start/end time of every segment,
  3. trims trailing silence so the film ends on the last word,
  4. writes  voiceover_<slug>.mp3  (the narration the film plays),
           narration_timing.json  (real per-segment timings -> exact sync),
           transcript_<slug>.md   (chaptered script the selector reads).

Because the visuals are chosen per sentence and each sentence is pinned to
its real spoken time, the audio and video stay matched for whatever was
said - it is not specific to one person.
"""

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent

# Section headers for a transformation/fitness documentary. These triggers
# describe the FORMAT (Monday chest, nutrition, recovery...), not any one
# celebrity, so they chapter any subject's routine video. If none match,
# the script is left as a single opening section - sync is unaffected.
SECTION_TRIGGERS = [
    ("set the stage", "BASELINE"), ("some context", "BASELINE"),
    ("his progression", "THE PROGRESSION"),
    ("her progression", "THE PROGRESSION"),
    ("actual week", "THE WEEKLY SPLIT"),
    ("weekly split", "THE WEEKLY SPLIT"),
    ("monday", "MONDAY"), ("tuesday", "TUESDAY"),
    ("wednesday", "WEDNESDAY"), ("thursday", "THURSDAY"),
    ("friday", "FRIDAY"), ("saturday", "SATURDAY"),
    ("sunday", "SUNDAY"),
    ("training style notes", "TRAINING PRINCIPLES"),
    ("training principles", "TRAINING PRINCIPLES"),
    ("actually eats", "NUTRITION"), ("nutrition", "NUTRITION"),
    ("sample daily", "A DAY OF EATING"),
    ("treadmill", "CARDIO"), ("cardio is", "CARDIO"),
    ("recovery is treated", "RECOVERY"),
    ("scaled down", "THE REALISTIC VERSION"),
    ("realistic version", "THE REALISTIC VERSION"),
    ("most people can't", "THE REALISTIC VERSION"),
    ("biggest mistakes", "COMMON MISTAKES"),
    ("week by week breakdown", "FINAL WORD"),
    ("go get to work", "FINAL WORD"),
]


def _run(args):
    return subprocess.run(args, capture_output=True, text=True)


def resolve_media(src: str) -> Path:
    """Return a local media file for src (path or URL)."""
    p = Path(src.strip().strip('"'))
    if p.exists():
        return p
    url = src.strip().strip('"')
    dst = ROOT / "narration_source"
    low = url.lower()
    if "youtube.com" in low or "youtu.be" in low:
        out = dst.with_suffix(".mp4")
        _run(["yt-dlp", "-f", "best[ext=mp4]/best", "--no-playlist",
              "-o", str(out), url])
        return out
    if "drive.google" in low or "docs.google" in low:
        m = re.search(r"/d/([A-Za-z0-9_-]+)", url) or \
            re.search(r"[?&]id=([A-Za-z0-9_-]+)", url)
        if not m:
            raise SystemExit("could not parse Google Drive id from URL")
        try:
            import gdown
        except ImportError:
            _run([sys.executable, "-m", "pip", "install", "gdown", "-q"])
            import gdown
        out = str(dst)
        gdown.download(id=m.group(1), output=out, quiet=False)
        return Path(out)
    # direct link
    import requests
    out = dst
    r = requests.get(url, timeout=120)
    out.write_bytes(r.content)
    return out


def transcribe(wav: Path, model_size: str = "base") -> dict:
    import whisper
    model = whisper.load_model(model_size)
    return model.transcribe(str(wav), language="en",
                            word_timestamps=True, verbose=False)


def build_narration(src: str, slug: str, model_size: str = "base",
                    subject: str = "") -> Path:
    """Full pipeline. Returns the transcript path."""
    media = resolve_media(src)
    print(f"    source media: {media.name}")

    wav = ROOT / "_narration_16k.wav"
    _run(["ffmpeg", "-y", "-i", str(media), "-vn", "-ac", "1",
          "-ar", "16000", "-c:a", "pcm_s16le", str(wav)])

    print("    transcribing with Whisper (local, no API)...")
    result = transcribe(wav, model_size)
    segs = [{"start": round(s["start"], 3), "end": round(s["end"], 3),
             "text": s["text"].strip()}
            for s in result["segments"] if s["text"].strip()]
    if not segs:
        raise SystemExit("transcription produced no speech segments")
    last_end = segs[-1]["end"]
    print(f"    {len(segs)} segments, {len(result['text'].split())} words, "
          f"speech ends {last_end:.0f}s")

    # narration the film plays: full-quality audio trimmed to last word+1.3s
    voiceover = ROOT / f"voiceover_{slug}.mp3"
    _run(["ffmpeg", "-y", "-i", str(media), "-vn", "-t",
          f"{last_end + 1.3:.2f}", "-c:a", "libmp3lame", "-b:a", "192k",
          str(voiceover)])

    # chaptered transcript + real timings (both from the same segments)
    def mmss(t):
        return f"{int(t // 60):02d}:{int(t % 60):02d}"

    title = subject or slug.replace("_", " ").title()
    lines = [f"# {title} - Documentary (narration transcript)", "",
             f"## [{mmss(0)}] HOOK", ""]
    timing, used = [], set()
    for s in segs:
        low = s["text"].lower()
        for trig, sect in SECTION_TRIGGERS:
            if trig in low and sect not in used:
                used.add(sect)
                lines += ["", f"## [{mmss(s['start'])}] {sect}", ""]
                break
        lines.append(s["text"])
        timing.append({"t": s["start"], "dur": round(s["end"] - s["start"], 3),
                       "text": s["text"]})

    transcript = ROOT / f"transcript_{slug}.md"
    transcript.write_text("\n".join(lines), encoding="utf-8")
    (ROOT / "narration_timing.json").write_text(json.dumps(timing))
    try:
        wav.unlink()
    except OSError:
        pass
    print(f"    [OK] {voiceover.name}, narration_timing.json, "
          f"{transcript.name} ({len(used)} chapters)")
    return transcript


if __name__ == "__main__":
    src = sys.argv[1] if len(sys.argv) > 1 else input("audio/video path or URL: ")
    slug = sys.argv[2] if len(sys.argv) > 2 else "subject"
    build_narration(src, slug)
