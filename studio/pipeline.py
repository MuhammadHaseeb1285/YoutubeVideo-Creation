"""pipeline - orchestrate the whole documentary build, stage by stage,
emitting progress the dashboard renders. Each stage is a small call into
the module that owns it, so the flow reads top to bottom:

    script -> config -> footage -> index -> narration -> timeline
           -> motion graphics -> validation -> render -> export
"""

from . import (settings, logs, research, transcript as T, narration,
               narration_profile as NP, assets, indexer, timeline as TL,
               motion_graphics as MG, validation, renderer)

STAGES = ["Script", "Footage", "Indexing", "Narration",
          "Selection & Timeline", "Validation", "Render"]


def resolve_script(params) -> tuple:
    """Return (transcript_path, subject, coach) from the chosen input."""
    mode = params.get("mode", "name")
    name = params.get("name", "").strip()
    coach = params.get("coach", "").strip()
    slug = T.slugify(name)

    if mode == "transcript_path":
        p = params["transcript_path"]
        from pathlib import Path
        tp = Path(p)
        if not tp.exists():
            raise RuntimeError(f"transcript not found: {p}")
        return tp, name, coach
    if mode == "transcript_url":
        import requests
        tp = settings.TRANSCRIPTS / f"transcript_{slug}.md"
        tp.parent.mkdir(parents=True, exist_ok=True)
        tp.write_text(requests.get(params["transcript_url"], timeout=30).text,
                      encoding="utf-8")
        return tp, name, coach
    if mode == "transcript_text":
        tp = settings.TRANSCRIPTS / f"transcript_{slug}.md"
        tp.parent.mkdir(parents=True, exist_ok=True)
        tp.write_text(params["transcript_text"], encoding="utf-8")
        return tp, name, coach
    if mode == "audio":
        tp = narration.import_recording(params["audio_src"], slug, name)
        return tp, name, coach
    # mode == "name": a researched documentary about the subject's WORKOUT
    # and DIET plan (with role/film body transformations woven in). We
    # research the person ONCE (Wikipedia) and work with BOTH sources: that
    # research grounds the Claude API write-up; without a key we fall back
    # to an honest chronological documentary from the same research.
    minutes = int(params.get("minutes", 12) or 12)
    from . import research as R
    prof = R.research_subject(name)
    ctype = prof.get("type", "public figure")
    context = (prof.get("intro") or prof.get("summary") or "")[:2800]

    # A real WORKOUT & DIET documentary needs a knowledge source for the
    # training/nutrition specifics. Wikipedia only has a biography, so
    # without the API key we STOP with a clear instruction instead of
    # shipping a 1-minute off-topic bio.
    try:
        tp, detected = T.generate_api(name, minutes, context)
        coach = coach or detected
        logs.log("script: workout & diet documentary (Wikipedia research + "
                 "Claude API, verified, length-filled)")
    except T.NoApiKey:
        raise RuntimeError(
            f"A workout & diet documentary about {name} needs a knowledge "
            f"source for the real training and nutrition. Add a Claude API "
            f"key in Settings (the app then researches and writes it), OR "
            f"paste your own script in the Documentary Input tab. Wikipedia "
            f"only has a biography - not workout/diet data - so a name alone "
            f"cannot produce a fitness documentary offline.")
    except T.NoFitnessData:
        raise RuntimeError(
            f"{name} has no publicly documented workout or diet, so a "
            f"fitness documentary can't be built from real sources. Choose a "
            f"celebrity with a documented fitness/transformation - e.g. an "
            f"action-movie actor, an athlete, or a fitness creator.")

    logs.metric("subject_type", ctype)
    params["_ctype"] = ctype
    return tp, name, coach


def generate(params: dict) -> dict:
    """Run the complete pipeline. Returns a result dict."""
    settings.ensure_dirs()
    logs.start_session("build")
    result = {"ok": False}
    try:
        name = params.get("name", "").strip()
        coach = params.get("coach", "").strip()
        slug = T.slugify(name)
        voice = params.get("voice", settings.DEFAULT_VOICE)
        mode = params.get("mode", "name")
        st = {**settings.load_settings(), **(params.get("settings") or {})}

        # everything for this subject lives in its own project folder
        proj = settings.set_project(slug)
        settings.ensure_dirs()
        logs.log(f"project folder: {proj}")
        logs.metric("project", slug)

        # 1 - SCRIPT
        logs.stage(1, len(STAGES), "Script")
        tp, name, coach = resolve_script(params)
        logs.metric("transcript", tp.name)

        cfg = {"subject": name, "coach": coach, "slug": slug,
               "voice": voice, "transcript": str(tp),
               "output": f"{(slug or 'documentary').upper()}_FINAL.mp4",
               "settings": st}
        settings.save_config(cfg)

        # 2 - FOOTAGE (only when asked to fetch by name)
        logs.stage(2, len(STAGES), "Footage")
        if params.get("download", mode == "name") and name:
            ctype = params.get("_ctype", "public figure")
            assets.download(research.build_queries(name, coach, slug, ctype))
        inv = assets.inventory()
        logs.metric("assets", inv)
        logs.log(f"assets: {inv['videos']} videos, {inv['images']} images")

        # 3 - INDEX
        logs.stage(3, len(STAGES), "Indexing")
        indexer.index_videos(progress_cb=lambda p, d: logs.progress(p, d))
        shots, dropped = indexer.build_shot_db()
        logs.metric("shots", len(shots))
        logs.log(f"shot database: {len(shots)} shots ({dropped} dropped)")
        if not shots:
            raise RuntimeError("no usable footage - import or download "
                               "videos before building")

        # 4 - NARRATION (profile chosen from the transcript's tone)
        logs.stage(4, len(STAGES), "Narration")
        voiceover = settings.voiceover_path(slug)
        if mode == "audio":
            logs.log("using imported narration (real voice)")
        else:
            analysis = NP.analyze(tp)
            key = st.get("narration_profile", "auto")
            if key == "auto" or key not in NP.PROFILES:
                key = analysis["recommended"]
            v, rate, pitch = NP.resolve(key, int(st.get("narration_pace", 0)),
                                        int(st.get("narration_energy", 0)))
            if params.get("voice"):                  # explicit override wins
                v = params["voice"]
            logs.metric("narration_profile",
                        {"key": key, "label": NP.PROFILES[key]["label"],
                         "genre": analysis["genre"], "voice": v,
                         "rate": rate, "traits": NP.PROFILES[key]["traits"]})
            logs.log(f"narration profile: {NP.PROFILES[key]['label']} "
                     f"({analysis['genre']})")
            narration.make_tts(tp, slug, v, rate, pitch)
        audio_dur = narration.ffprobe_duration(voiceover)
        logs.metric("narration_dur", round(audio_dur, 1))
        logs.log(f"narration: {int(audio_dur//60)}:{int(audio_dur%60):02d}")

        # 5 - SELECTION & TIMELINE
        logs.stage(5, len(STAGES), "Selection & Timeline")
        sentences = narration.sentence_timeline(tp, audio_dur, coach, name)
        logs.metric("sentences", len(sentences))
        tl = TL.build(sentences, shots,
                      progress_cb=lambda p, d: logs.progress(p, d),
                      max_clip=float(st.get("max_clip", settings.MAX_PIECE)))
        logs.metric("timeline_pieces", len(tl))
        events = MG.build_events(sentences, tl, name, coach)
        logs.metric("text_events", len(events))

        # 6 - VALIDATION
        logs.stage(6, len(STAGES), "Validation")
        ok, report = validation.validate(tl, sentences, audio_dur)
        logs.metric("validation", report)
        for c in report["checks"]:
            logs.log(f"  {'OK ' if c['pass'] else 'X  '}{c['name']}: "
                     f"{c['detail']}")
        if not ok:
            raise RuntimeError("validation failed - rebuild required")

        # 7 - RENDER
        logs.stage(7, len(STAGES), "Render")
        out = settings.output_path(cfg)
        renderer.render(tl, events, audio_dur, voiceover, out,
                        progress_cb=lambda p, d: logs.progress(p, d))
        logs.log(f"SUCCESS: {out}")
        logs.metric("output", str(out))
        result = {"ok": True, "output": str(out), "report": report,
                  "pieces": len(tl), "events": len(events),
                  "duration": round(audio_dur, 1)}
    except Exception as e:
        logs.log(f"ERROR: {e}", "error")
        result = {"ok": False, "error": str(e)}
    logs.progress(100, "done")
    return result
