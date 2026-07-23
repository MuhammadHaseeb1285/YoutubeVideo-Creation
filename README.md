# YoutubeVideo-Creation

Automated documentary video builder. Turns a narration transcript plus a
folder of source videos into a finished, voiceover-synced YouTube video
with intelligent clip selection.

## Pipeline

| Step | Script | What it does |
|------|--------|--------------|
| 1 | `DOWNLOAD_VIDEOS.py` | Downloads source videos from YouTube (yt-dlp) and Pexels (API) by keyword |
| 2 | `VISION_INDEX.py` | Detects real scene cuts in every video (ffmpeg scene detection) and builds labeled contact sheets so each scene's content can be visually classified into `vision_tags.json` |
| 3 | `CUT_CLIPS.py` | (Optional) blind 4-second clip cutter for quick previews |
| 4 | `GENERATE_FINAL_VIDEO.py` | The editor: generates the TTS narration, maps every sentence onto the audio timeline, selects one unique, content-matched shot per moment (subject-first scoring, gender-consistent B-roll, max 4s per shot, no scene repeated nearby), overlays animated titles / lower-thirds / stat callouts, validates the whole timeline, and renders the final MP4 |

## Requirements

- Python 3.10+
- `ffmpeg` / `ffprobe` on PATH
- `pip install yt-dlp edge-tts pillow requests`

## Run

```
python DOWNLOAD_VIDEOS.py
python VISION_INDEX.py        # then classify scenes into vision_tags.json
python GENERATE_FINAL_VIDEO.py
```

Output: `final_video/RYAN_REYNOLDS_FINAL.mp4`
