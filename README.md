# YoutubeVideo-Creation

Automated documentary video builder. Turns a narration transcript plus a
folder of source videos into a finished, voiceover-synced YouTube video
with intelligent clip selection.

## Pipeline

| Step | Script | What it does |
|------|--------|--------------|
| 1 | `DOWNLOAD_VIDEOS.py` | Downloads base source videos from YouTube (yt-dlp) and Pexels (API) by keyword |
| 1b | `FETCH_MORE_RYAN.py` | Targeted fetch of extra subject footage (training, BTS, interviews, coach) |
| 2 | `VISION_INDEX.py` | Detects real scene cuts in every video (ffmpeg scene detection) and builds labeled contact sheets so each scene's content can be visually classified into `vision_tags.json` |
| 2b | `INDEX_NEW.py` | Incrementally scene-detects videos added later and sheets only the new scenes (`vision_tags2.json` batch) |
| 2c | `GEN_TAGS2.py` | Emits the classification database for the second batch from the manual visual review |
| 3 | `CUT_CLIPS.py` | (Optional) blind 4-second clip cutter for quick previews |
| 4 | `GENERATE_FINAL_VIDEO.py` | The editor: generates the TTS narration, maps every sentence onto the audio timeline, selects one unique, content-matched shot per moment (subject-first ~90/10 balance, gender-consistent B-roll, max 4s per shot, no scene repeated nearby, footage reservation for subject narration), overlays animated titles / lower-thirds / stat callouts, validates the whole timeline, and renders the final MP4 |

The scene classification databases (`vision_tags*.json`, `sheets_map*.json`)
are committed so the selector works without redoing the visual review.

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
