"""narration_enhanced - Intelligent voice selection per section + professional voice API support.

Features:
- Section-based voice profiles (gym = energetic, diet = informative, interview = conversational)
- ElevenLabs API integration for professional-quality voices
- Fallback to edge-tts if no API key
- Dynamic pitch/rate adjustments per section type
- Proper volume normalization
"""

import json
import os
import subprocess
from pathlib import Path

from . import settings, logs, narration


# Voice profiles: (elevenlabs_voice_id, edge_tts_voice, rate, pitch, energy_level)
VOICE_PROFILES = {
    "energetic": {
        "elevenlabs": "cgSgspJ2msLfdFcuWe7K",  # High-energy voice
        "edge_tts": "en-US-GuyNeural",          # Male, energetic
        "rate": "+20%",
        "pitch": "+10%",
        "energy": 1.0,
    },
    "motivational": {
        "elevenlabs": "MF3mGyEYCl7XYWbV9V5O",  # Inspirational
        "edge_tts": "en-US-ChristopherNeural",  # Deep, authoritative
        "rate": "+15%",
        "pitch": "+5%",
        "energy": 0.9,
    },
    "informative": {
        "elevenlabs": "pFZP5JQG7iQjIQuC4Iy3",   # Clear, educational
        "edge_tts": "en-US-AriaNeural",         # Clear, neutral
        "rate": "0%",
        "pitch": "0%",
        "energy": 0.7,
    },
    "conversational": {
        "elevenlabs": "EXAVITQu4vr4xnSDxMaL",   # Friendly, casual
        "edge_tts": "en-US-AmberNeural",        # Warm, conversational
        "rate": "-10%",
        "pitch": "-5%",
        "energy": 0.6,
    },
    "dramatic": {
        "elevenlabs": "9Bu3jMDBKfCMzKS7P9wL",   # Dramatic, intense
        "edge_tts": "en-US-BrandonNeural",      # Deep, dramatic
        "rate": "-15%",
        "pitch": "+15%",
        "energy": 1.1,
    }
}

# Section type detection patterns
SECTION_PATTERNS = {
    "workout": ["train", "gym", "work out", "exercise", "lift", "press", "squat", "bench", "deadlift", "cardio"],
    "diet": ["eat", "diet", "nutrition", "protein", "meal", "food", "calories", "macro"],
    "discipline": ["discipline", "consistency", "commitment", "grind", "mentality", "mindset", "push"],
    "transformation": ["transform", "change", "progress", "body", "physique", "lean", "muscle"],
    "interview": ["said", "told", "explain", "talked", "interview", "discussed", "shared"],
}


def detect_section_type(text: str) -> str:
    """Detect section type from narration text."""
    text_lower = text.lower()
    for section, keywords in SECTION_PATTERNS.items():
        if any(kw in text_lower for kw in keywords):
            return section
    return "motivational"  # default


def get_voice_for_section(section_type: str, use_elevenlabs: bool = False) -> tuple:
    """Get voice profile for a section. Returns (voice_id, rate, pitch)."""
    # Map section types to voice profiles
    profile_map = {
        "workout": "energetic",
        "diet": "informative",
        "discipline": "motivational",
        "transformation": "dramatic",
        "interview": "conversational",
        "motivational": "motivational",
    }
    profile = profile_map.get(section_type, "motivational")
    voice_cfg = VOICE_PROFILES[profile]

    if use_elevenlabs:
        return voice_cfg["elevenlabs"], voice_cfg["rate"], voice_cfg["pitch"]
    else:
        return voice_cfg["edge_tts"], voice_cfg["rate"], voice_cfg["pitch"]


def make_elevenlabs_tts(text: str, voice_id: str, rate: str = "0%", pitch: str = "0%") -> bytes:
    """Generate TTS using ElevenLabs API."""
    key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    if not key:
        kf = settings.ROOT / "elevenlabs_key.txt"
        if kf.exists():
            key = kf.read_text(encoding="utf-8").strip()

    if not key:
        raise RuntimeError("ElevenLabs API key not found. Set ELEVENLABS_API_KEY env var or create elevenlabs_key.txt")

    try:
        import requests
    except ImportError:
        raise RuntimeError("requests module required for ElevenLabs API")

    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    headers = {
        "xi-api-key": key,
        "Content-Type": "application/json"
    }

    # Parse rate/pitch ("+20%" -> 1.2, "-10%" -> 0.9)
    rate_mult = 1.0 + (float(rate.strip("+%")) / 100) if "%" in rate else 1.0
    pitch_mult = 1.0 + (float(pitch.strip("+%")) / 100) if "%" in pitch else 1.0

    payload = {
        "text": text,
        "model_id": "eleven_monolingual_v1",
        "voice_settings": {
            "stability": 0.75,
            "similarity_boost": 0.85,
        }
    }

    resp = requests.post(url, json=payload, headers=headers, timeout=30)
    if resp.status_code != 200:
        raise RuntimeError(f"ElevenLabs API error: {resp.status_code} {resp.text}")

    return resp.content


def make_tts_intelligent(transcript_path: Path, slug: str, use_elevenlabs: bool = False,
                        progress_cb=None) -> Path:
    """
    Generate TTS with intelligent section-based voice selection.

    If use_elevenlabs=True, uses ElevenLabs for professional voices.
    Otherwise falls back to edge-tts.
    """
    from . import narration as N

    tp = transcript_path
    if not tp.exists():
        raise RuntimeError(f"transcript not found: {tp}")

    text = tp.read_text(encoding="utf-8").strip()
    sentences = [s.strip() for s in text.split("\n") if s.strip()]

    logs.log(f"[NARRATION] Generating intelligent TTS ({len(sentences)} sentences)...")
    logs.log(f"[NARRATION] Using {'ElevenLabs' if use_elevenlabs else 'Edge-TTS'}")

    voiceover = settings.voiceover_path(slug)
    voiceover.parent.mkdir(parents=True, exist_ok=True)

    audio_segments = []
    timings = []
    current_time = 0.0

    try:
        import edge_tts
    except ImportError:
        edge_tts = None

    for i, sent in enumerate(sentences):
        section_type = detect_section_type(sent)
        voice, rate, pitch = get_voice_for_section(section_type, use_elevenlabs)

        try:
            if use_elevenlabs:
                # Use ElevenLabs API
                audio_data = make_elevenlabs_tts(sent, voice, rate, pitch)
                # Write temp file
                temp_audio = voiceover.parent / f"_seg_{i:04d}.mp3"
                temp_audio.write_bytes(audio_data)
                audio_segments.append(str(temp_audio))
            else:
                # Use edge-tts with section-based rate/pitch
                if not edge_tts:
                    raise ImportError("edge-tts not available")

                temp_audio = voiceover.parent / f"_seg_{i:04d}.mp3"
                c = edge_tts.Communicate(sent, voice, rate=rate, pitch=pitch)

                # Save segment
                import asyncio
                async def save_tts():
                    with open(temp_audio, "wb") as f:
                        async for chunk in c.stream():
                            if chunk["type"] == "audio":
                                f.write(chunk["data"])

                asyncio.run(save_tts())
                audio_segments.append(str(temp_audio))

            # Get duration via ffprobe
            result = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1:noinvert_searchable=1",
                 str(temp_audio)],
                capture_output=True, text=True, timeout=10
            )

            dur = float(result.stdout.strip()) if result.stdout.strip() else 2.0
            timings.append({
                "text": sent,
                "start": round(current_time, 2),
                "duration": round(dur, 2),
                "section": section_type,
                "voice": voice,
            })
            current_time += dur

            if progress_cb:
                progress_cb(100 * (i + 1) / len(sentences), f"TTS: {section_type}")

            logs.log(f"  [{section_type:12}] {sent[:60]:<60} ({dur:.2f}s)")

        except Exception as e:
            logs.log(f"  ERROR on sentence {i}: {e}", "error")
            continue

    # Concatenate all audio segments
    if not audio_segments:
        raise RuntimeError("No audio segments generated")

    if len(audio_segments) == 1:
        import shutil
        shutil.copy(audio_segments[0], voiceover)
    else:
        # Use ffmpeg concat demuxer
        concat_list = voiceover.parent / "_concat.txt"
        concat_list.write_text("\n".join(f"file '{s}'" for s in audio_segments),
                               encoding="utf-8")

        subprocess.run(
            ["ffmpeg", "-f", "concat", "-safe", "0", "-i", str(concat_list),
             "-c", "aac", "-b:a", "192k", "-y", str(voiceover)],
            capture_output=True, timeout=300
        )

    # Normalize volume
    normalized = voiceover.parent / "_normalized.mp3"
    subprocess.run(
        ["ffmpeg-normalize", str(voiceover), "-o", str(normalized),
         "-c:a", "aac", "-b:a", "192k"],
        capture_output=True, timeout=60
    )
    if normalized.exists():
        normalized.replace(voiceover)

    # Save timing info
    timing_file = settings.CACHE / "narration_timings.json"
    timing_file.parent.mkdir(parents=True, exist_ok=True)
    timing_file.write_text(json.dumps(timings, indent=2), encoding="utf-8")

    # Cleanup temp files
    for seg in audio_segments:
        Path(seg).unlink(missing_ok=True)
    concat_list.unlink(missing_ok=True)

    logs.log(f"[NARRATION] Complete: {N.ffprobe_duration(voiceover):.0f}s, {len(timings)} sections")
    return voiceover
