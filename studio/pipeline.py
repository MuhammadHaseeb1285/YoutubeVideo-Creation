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
        # No key: search public FITNESS publications (Men's Health, Muscle &
        # Fitness, etc.) for the real workout/diet coverage and build from it.
        logs.log(f"no API key - searching fitness publications for "
                 f"{name}'s real workout & diet coverage...")
        arts = R.fetch_fitness_content(name)
        if not arts:
            raise RuntimeError(
                f"No public workout/diet coverage was found online for "
                f"{name}. Pick a celebrity with a documented fitness "
                f"transformation (action-movie actor, athlete, or fitness "
                f"creator), or paste your own script in Documentary Input.")
        try:
            tp, meta = T.generate_from_sources(name, minutes, arts)
            coach = coach or meta.get("coach", "")
            logs.log(f"script: built from {len(arts)} public fitness "
                     f"sources (no API key needed)")
        except T.NoFitnessData:
            raise RuntimeError(
                f"Found articles for {name} but not enough real workout/diet "
                f"detail to build a fitness documentary. Try a celebrity with "
                f"a well-documented transformation, or paste your own script.")

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

        # 2 - FOOTAGE (manual URLs + auto-search + Pexels)
        logs.stage(2, len(STAGES), "Footage")

        # Check for manually-provided video URLs
        manual_urls = (params.get("video_urls") or "").strip().split("\n")
        manual_urls = [u.strip() for u in manual_urls if u.strip()]

        want_dl = params.get("download")
        if want_dl is None:
            want_dl = bool(name)

        if manual_urls and want_dl:
            # User provided direct links - ALWAYS download these first
            logs.log(f"downloading {len(manual_urls)} user-provided URL(s)...")
            try:
                assets.download_from_urls(manual_urls, slug)
                logs.log(f"✓ Downloaded {len(manual_urls)} manual URLs")
            except Exception as e:
                logs.log(f"manual URL download failed: {e}", "error")

        # YouTube auto-search (only if download enabled)
        if want_dl and name:
            ctype = params.get("_ctype", "public figure")
            if manual_urls:
                logs.log("supplementing with auto-search...")
            else:
                logs.log("searching YouTube for all footage...")

            try:
                from . import assets_enhanced as AE
                # YouTube auto-search only
                AE.auto_search_youtube(name, coach, ctype)
                logs.log("✓ YouTube auto-search complete")
            except ImportError:
                # Fallback to old system
                logs.log("enhanced assets unavailable, using standard download")
                assets.download(research.build_queries(name, coach, slug, ctype),
                               subject=name)

        # ALWAYS fetch Pexels (even if download disabled) - supplement existing footage
        logs.log("fetching Pexels media as supplement...")
        try:
            from . import assets_enhanced as AE
            AE.fetch_supplementary_media(name, coach)
            logs.log("✓ Pexels media fetched")
        except Exception as e:
            logs.log(f"Pexels fetch: {e}")

        inv = assets.inventory()
        logs.metric("assets", inv)
        logs.log(f"assets: {inv['videos']} videos, {inv['images']} images")

        # 3 - INDEX (scene detection, then classify each scene BY CONTENT
        # with Gemini Vision so footage matches the narration for real).
        logs.stage(3, len(STAGES), "Indexing")
        indexer.index_videos(progress_cb=lambda p, d: logs.progress(p, d))

        # Check which filtering mode is active
        try:
            from . import clip_filter_enhanced
            logs.log("using ENHANCED filtering (Gemini Vision + text detection)")
        except ImportError:
            logs.log("using standard filtering")

        from . import vision
        try:
            vision.auto_tag(name or "the subject", coach,
                            progress_cb=lambda p, d: logs.progress(p, d),
                            hint=params.get("_ctype", ""),
                            image_url=params.get("image_url", ""))
        except vision.NoVisionKey:
            logs.log("no Gemini key found - matching footage by FILENAME "
                     "only, so sync will be approximate. Add a free Gemini "
                     "key (gemini_key.txt) for content-accurate sync.",
                     "error")
        except Exception as e:
            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e) or "quota" in str(e).lower():
                logs.log("Gemini API quota exceeded (free tier limit) - skipping Vision. "
                         "Continuing with filename-based matching. "
                         "Upgrade to paid Gemini API for content-accurate sync.", "error")
            else:
                logs.log(f"vision tagging failed ({e}); using filename tags")
        shots, dropped = indexer.build_shot_db()
        logs.metric("shots", len(shots))
        logs.log(f"shot database: {len(shots)} shots ({dropped} dropped)")
        if not shots:
            raise RuntimeError(
                "No footage to build from. Enter the celebrity's name so "
                "the app can download clips (footage = Auto or Always), or "
                "import your own videos in Asset Manager - then generate "
                "again.")

        # 4 - NARRATION (profile chosen from the transcript's tone)
        logs.stage(4, len(STAGES), "Narration")
        voiceover = settings.voiceover_path(slug)
        if mode == "audio":
            logs.log("using imported narration (real voice)")
        else:
            # Check if intelligent section-based narration requested
            use_intelligent = params.get("intelligent_narration", False)
            use_elevenlabs = params.get("professional_voice", False)

            if use_intelligent:
                # Use enhanced intelligent narration with section-based voices
                try:
                    from . import narration_enhanced as NE
                    NE.make_tts_intelligent(tp, slug, use_elevenlabs=use_elevenlabs,
                                           progress_cb=lambda p, d: logs.progress(p, d))
                    logs.log("narration: intelligent section-based voices")
                    if use_elevenlabs:
                        logs.log("  using ElevenLabs professional voices")
                    else:
                        logs.log("  using Edge-TTS with dynamic rate/pitch per section")
                except ImportError:
                    logs.log("intelligent narration unavailable, falling back to standard TTS")
                    analysis = NP.analyze(tp)
                    key = st.get("narration_profile", "auto")
                    if key == "auto" or key not in NP.PROFILES:
                        key = analysis["recommended"]
                    v, rate, pitch = NP.resolve(key, int(st.get("narration_pace", 0)),
                                                int(st.get("narration_energy", 0)))
                    if params.get("voice"):
                        v = params["voice"]
                    narration.make_tts(tp, slug, v, rate, pitch)
            else:
                # Standard TTS with single voice
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

        # 5 - SELECTION & TIMELINE (SMART SENTENCE-LEVEL MATCHING)
        logs.stage(5, len(STAGES), "Selection & Timeline")
        sentences = narration.sentence_timeline(tp, audio_dur, coach, name)
        logs.metric("sentences", len(sentences))

        # Get Pexels footage (videos + images converted to clips) as supplementary
        pexels_shots = []
        pexels_image_count = 0

        if settings.ASSETS_PEXELS.exists():
            try:
                pexels_list = [p for p in settings.ASSETS_PEXELS.glob("*.mp4")]
                if pexels_list:
                    logs.log(f"Using {len(pexels_list)} Pexels videos as supplement")
                    # Index Pexels videos (indexer already imported at top)
                    pexels_indexed = indexer.index_videos_in_folder(settings.ASSETS_PEXELS)
                    pexels_shots = indexer.build_shot_db_from_indexed(pexels_indexed)
            except Exception as e:
                logs.log(f"Could not load Pexels videos: {e}")

        # Load Pexels images (for variety, overlay potential)
        if settings.ASSETS_IMAGE.exists():
            try:
                pexels_images = [p for p in settings.ASSETS_IMAGE.glob("*.{jpg,png,webp}")]
                if pexels_images:
                    pexels_image_count = len(pexels_images)
                    logs.log(f"Using {pexels_image_count} Pexels images for supplementary content")
            except Exception as e:
                logs.log(f"Could not load Pexels images: {e}")

        # Build timeline using smart, sentence-level selection
        tl = TL.build(
            sentences,
            shots,
            pexels_shots=pexels_shots,
            subject_name=name,
            progress_cb=lambda p, d: logs.progress(p, d),
            max_clip=float(st.get("max_clip", settings.MAX_PIECE))
        )

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
