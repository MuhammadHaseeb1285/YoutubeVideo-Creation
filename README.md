# Documentary Studio

A modular application that produces workout / physique-transformation
documentaries for **any** subject. It turns a script (written, generated,
or transcribed from your own narration) plus a library of footage into a
finished, narration-synced YouTube video where the visuals are chosen per
sentence to match what is being said — driven from a professional dashboard
instead of the terminal.

## Launch

```
python app.py
```

The dashboard opens in your browser. From there you:

1. Enter a **celebrity name**, or paste / link a **transcript**, or import
   your own **narration audio**.
2. Import or auto-download **footage**.
3. Click **Generate Documentary**.

The pipeline then runs and streams live progress: research → script →
asset indexing → semantic clip selection → timeline → narration → motion
graphics → validation → render → export.

## Architecture

```
app.py                 launch the dashboard
studio/                the engine (one responsibility per module)
  settings.py          paths, config, constants
  logs.py              live structured logging + progress events
  research.py          footage search-query planning
  transcript.py        script generation (template / Claude API) + parsing
  narration.py         TTS or real-audio narration + spoken-time alignment
  assets.py            download, inventory, dedupe, missing report
  indexer.py           scene detection + shot database
  semantic.py          category groups, relevance scoring, exercise families
  selection.py         per-sentence clip selection (ranks the whole pool)
  timeline.py          timeline assembly with documentary pacing
  motion_graphics.py   animated text events + ffmpeg draw filters
  renderer.py          ffmpeg render of the timeline
  validation.py        editorial gate (refuses low-quality edits)
  pipeline.py          orchestrates every stage with progress callbacks
dashboard/
  server.py            dependency-free local web server + JSON API
  app.html             the dashboard UI (dark, responsive)
legacy/                the previous single-file scripts, archived
```

## How the intelligence works

- **Semantic selection** — for every sentence, the entire unused shot pool
  is ranked by relevance (exact spoken exercise > same movement family >
  topic affinity, subject as tie-breaker). The highest-scoring unique shot
  wins. No filename matching, no "next available clip".
- **Audio–visual sync** — narration is either generated with a documentary
  TTS voice or transcribed from your own recording (Whisper, local). Either
  way every sentence is pinned to its real spoken time, so the visuals
  follow the voice.
- **Cinematic motion graphics** — animated titles, chapter cards, movie
  title cards, stat callouts, pull-quotes, timeline markers, dual-side
  lower-thirds and exercise labels, all with slide-ins and fades.
- **Validation gate** — the render is refused unless topic-match ≥ 92%,
  exercise-sync ≥ 85%, all shots unique, none over 4s, and video length
  equals narration length.

## Requirements

- Python 3.10+
- `ffmpeg` / `ffprobe` on PATH
- `pip install yt-dlp edge-tts openai-whisper gdown requests psutil`

Output: `output/<SUBJECT>_FINAL.mp4`
