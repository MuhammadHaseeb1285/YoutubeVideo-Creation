"""narration - produce the voiceover and align every sentence to its real
spoken time. Two sources:
  * TTS (edge-tts) from the transcript, capturing sentence-boundary timings
  * a real recording (file or URL) transcribed locally with Whisper
Either way we write voiceover_<slug>.mp3 + narration_timing.json, and the
timeline is pinned to the true spoken moments so audio and video match.
"""

import asyncio
import json
import re
import subprocess
import sys
from pathlib import Path

from . import settings, logs, transcript as T


def ffprobe_duration(p):
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(p)],
        capture_output=True, text=True, timeout=30)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


# ------------------------------------------------------------ TTS narration
def _edge():
    try:
        import edge_tts
    except ImportError:
        subprocess.run([sys.executable, "-m", "pip", "install",
                        "edge-tts", "-q"], check=True)
        import edge_tts
    return edge_tts


def make_tts(transcript_path: Path, slug: str, voice: str,
             rate: str = "+0%", pitch: str = "+0Hz"):
    """Render narration with edge-tts (prosody-aware) and capture
    per-sentence timings."""
    edge_tts = _edge()
    sentences = [s for _, sents in T.parse_sections(transcript_path)
                 for s in sents]
    text = " ".join(sentences)
    voiceover = settings.voiceover_path(slug)
    voiceover.parent.mkdir(parents=True, exist_ok=True)
    segs = []

    async def _run():
        c = edge_tts.Communicate(text, voice or settings.DEFAULT_VOICE,
                                 rate=rate, pitch=pitch)
        with open(voiceover, "wb") as f:
            async for chunk in c.stream():
                ct = chunk.get("type")
                if ct == "audio":
                    f.write(chunk["data"])
                elif ct in ("SentenceBoundary", "WordBoundary"):
                    segs.append({"t": round(chunk["offset"] / 1e7, 3),
                                 "dur": round(chunk["duration"] / 1e7, 3),
                                 "text": chunk.get("text", "")})
    asyncio.run(_run())
    settings.TIMING.parent.mkdir(parents=True, exist_ok=True)
    settings.TIMING.write_text(json.dumps(segs))
    logs.log(f"narration: {ffprobe_duration(voiceover):.0f}s, "
             f"{len(segs)} timing points, voice={voice} {rate}")
    return voiceover


def preview_sample(voice: str, rate: str, pitch: str, text: str,
                   out_path: Path):
    """Render a short spoken sample (used by the narration preview UI)."""
    edge_tts = _edge()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    async def _run():
        c = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
        await c.save(str(out_path))
    asyncio.run(_run())
    return out_path


# ------------------------------------------------------------ real audio
def resolve_media(src: str) -> Path:
    p = Path(src.strip().strip('"'))
    if p.exists():
        return p
    url = src.strip().strip('"')
    low = url.lower()
    dst = settings.ASSETS_AUDIO / "narration_source"
    dst.parent.mkdir(parents=True, exist_ok=True)
    if "youtube.com" in low or "youtu.be" in low:
        out = dst.with_suffix(".mp4")
        subprocess.run(["yt-dlp", "-f", "best[ext=mp4]/best",
                        "--no-playlist", "-o", str(out), url],
                       capture_output=True)
        return out
    if "drive.google" in low or "docs.google" in low:
        m = (re.search(r"/d/([A-Za-z0-9_-]+)", url)
             or re.search(r"[?&]id=([A-Za-z0-9_-]+)", url))
        if not m:
            raise RuntimeError("cannot parse Google Drive id")
        try:
            import gdown
        except ImportError:
            subprocess.run([sys.executable, "-m", "pip", "install",
                            "gdown", "-q"])
            import gdown
        gdown.download(id=m.group(1), output=str(dst), quiet=True)
        return dst
    import requests
    dst.write_bytes(requests.get(url, timeout=120).content)
    return dst


def import_recording(src: str, slug: str, subject: str,
                     model_size: str = "base") -> Path:
    """Transcribe a real recording -> voiceover + timings + transcript."""
    import whisper
    media = resolve_media(src)
    logs.log(f"narration source: {media.name}")
    wav = settings.CACHE / "_narration_16k.wav"
    wav.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-y", "-i", str(media), "-vn", "-ac", "1",
                    "-ar", "16000", "-c:a", "pcm_s16le", str(wav)],
                   capture_output=True)
    logs.log("transcribing with Whisper (local)...")
    model = whisper.load_model(model_size)
    result = model.transcribe(str(wav), language="en",
                              word_timestamps=True, verbose=False)
    segs = [{"start": round(s["start"], 3), "end": round(s["end"], 3),
             "text": s["text"].strip()}
            for s in result["segments"] if s["text"].strip()]
    if not segs:
        raise RuntimeError("no speech detected")
    last_end = segs[-1]["end"]
    logs.log(f"{len(segs)} segments, speech ends {last_end:.0f}s")

    voiceover = settings.voiceover_path(slug)
    voiceover.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-y", "-i", str(media), "-vn", "-t",
                    f"{last_end + 1.3:.2f}", "-c:a", "libmp3lame",
                    "-b:a", "192k", str(voiceover)], capture_output=True)

    tr = T.chapter_segments(segs, subject, slug)
    timing = [{"t": s["start"], "dur": round(s["end"] - s["start"], 3),
               "text": s["text"]} for s in segs]
    settings.TIMING.write_text(json.dumps(timing))
    try:
        wav.unlink()
    except OSError:
        pass
    return tr


# ------------------------------------------------------------ alignment
def _load_timing():
    if settings.TIMING.exists():
        try:
            return json.loads(settings.TIMING.read_text())
        except Exception:
            return None
    return None


def sentence_start_times(sentences, audio_dur):
    """Real start time per sentence from captured boundaries via character
    alignment; proportional fallback when timings are missing."""
    segs = _load_timing()
    if segs and len(segs) >= max(3, len(sentences) * 0.5):
        spoken, pos = [], 0
        for s in segs:
            n = len(s.get("text", ""))
            spoken.append((pos, pos + n, s["t"]))
            pos += n + 1
        starts, cur = [], 0
        for sent in sentences:
            mid = cur + len(sent) / 2
            covering = [sp for sp in spoken if sp[0] <= mid < sp[1]]
            if covering:
                start = covering[0][2]
            else:
                start = min(spoken,
                            key=lambda sp: abs(mid - (sp[0] + sp[1]) / 2))[2]
            starts.append(start)
            cur += len(sent) + 1
        for i in range(1, len(starts)):
            if starts[i] < starts[i - 1]:
                starts[i] = starts[i - 1]
        return starts
    total = sum(len(s) for s in sentences) or 1
    starts, t = [], 0.0
    for s in sentences:
        starts.append(round(t, 3))
        t += len(s) / total * audio_dur
    return starts


def sentence_timeline(transcript_path, audio_dur, coach="", subject=""):
    flat = [(title, s) for title, sents in T.parse_sections(transcript_path)
            for s in sents]
    sents_only = [s for _, s in flat]
    starts = sentence_start_times(sents_only, audio_dur)
    out, seen = [], set()
    for i, (title, s) in enumerate(flat):
        st = starts[i]
        nxt = starts[i + 1] if i + 1 < len(starts) else audio_dur
        first = title not in seen
        seen.add(title)
        out.append({"text": s, "type": T.type_of_sentence(s, coach, subject),
                    "ex": T.exercise_of_sentence(s), "section": title,
                    "sec_start": first, "start": round(st, 2),
                    "dur": round(max(0.4, nxt - st), 2)})
    return out
