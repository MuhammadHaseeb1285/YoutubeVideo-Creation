"""renderer - turn the validated timeline into the final MP4. Each piece is
normalized to 1920x1080/30fps, graded (contrast/saturation/vignette),
given a slow punch-in on alternating shots, and composited with its text
animation. Pieces are concatenated and married to the narration.
"""

import os
import shutil
import subprocess

from . import settings, logs, motion_graphics

BASE_VF = ("scale=1920:1080:force_original_aspect_ratio=decrease,"
           "pad=1920:1080:(ow-iw)/2:(oh-ih)/2:black,fps=30,"
           "format=yuv420p,eq=contrast=1.05:saturation=1.15,vignette=PI/5")


def render(timeline, events, audio_dur, voiceover, out_path, progress_cb=None):
    work = settings.OUTPUT / f"_render_{os.getpid()}"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)

    def render_piece(e, out):
        work.mkdir(parents=True, exist_ok=True)
        vf = BASE_VF
        if e["slot"] % 2 == 0:
            frames = max(2, int(e["dur"] * 30))
            vf += (f",zoompan=z='1+0.06*on/{frames}':d=1:"
                   "x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
                   "s=1920x1080:fps=30")
        ev = events.get(e["slot"])
        if ev:
            vf += "," + motion_graphics.text_filter(ev[0], ev[1], ev[2],
                                                    e["dur"], e["slot"])
        subprocess.run(
            ["ffmpeg", "-ss", str(e["in"]), "-i", e["src"], "-t",
             str(e["dur"]), "-vf", vf, "-an", "-c:v", "libx264",
             "-preset", "veryfast", "-crf", "22", "-y", str(out)],
            capture_output=True, timeout=180)

    n = len(timeline)
    for i, e in enumerate(timeline):
        render_piece(e, work / f"p_{i:04d}.mp4")
        if progress_cb and (i + 1) % 5 == 0:
            progress_cb(100 * (i + 1) / n, f"rendered {i + 1}/{n} shots")
        if (i + 1) % 25 == 0:
            logs.log(f"    rendered {i + 1}/{n}")

    parts = []
    for i, e in enumerate(timeline):
        out = work / f"p_{i:04d}.mp4"
        if not out.exists():
            subprocess.run(
                ["ffmpeg", "-ss", str(e["in"]), "-i", e["src"], "-t",
                 str(e["dur"]), "-vf", BASE_VF, "-an", "-c:v", "libx264",
                 "-preset", "veryfast", "-crf", "22", "-y", str(out)],
                capture_output=True, timeout=180)
        if out.exists():
            parts.append(out)
    if not parts:
        raise RuntimeError("no rendered pieces on disk")

    lst = work / "list.txt"
    with open(lst, "w", encoding="utf-8") as f:
        for p in parts:
            f.write(f"file '{p.absolute().as_posix()}'\n")
    silent = work / "video.mp4"
    subprocess.run(["ffmpeg", "-f", "concat", "-safe", "0", "-i", str(lst),
                    "-c:v", "copy", "-an", "-y", str(silent)],
                   capture_output=True, text=True, timeout=1800)
    if not silent.exists():
        raise RuntimeError("concat failed")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-i", str(silent), "-i", str(voiceover),
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                    "-map", "0:v:0", "-map", "1:a:0",
                    "-t", f"{audio_dur:.2f}", "-y", str(out_path)],
                   capture_output=True, text=True, timeout=1800)
    if not out_path.exists():
        raise RuntimeError("mux failed")
    shutil.rmtree(work, ignore_errors=True)
    return out_path
