"""
Celebrity Documentary Studio - modular documentary production engine.

Each module owns one responsibility:
    settings         paths, config, constants
    logs             structured live logging (ring buffer + file)
    research         footage search-query planning
    transcript       transcript generation (template / API) + parsing
    narration        TTS or real-audio narration + spoken-time alignment
    assets           asset download, inventory, dedupe, missing report
    indexer          scene detection + shot database
    semantic         category groups, relevance, exercise families
    selection        per-sentence clip selection
    timeline         timeline assembly
    motion_graphics  animated text events + ffmpeg draw filters
    renderer         ffmpeg render of the timeline
    validation       editorial validation gate
    pipeline         orchestrates the whole flow with progress callbacks
"""

__version__ = "1.0.0"
