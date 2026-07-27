"""timeline_enhanced - Build transformation-focused documentaries with full metadata.

Structure follows the 8-section format:
1. OPENING (before/after)
2. BEGINNING (stats, starting physique)
3. DIET (meals, macros, nutrition)
4. GYM (workouts, progression)
5. TRANSFORMATION (body progression montage)
6. CHALLENGES (recovery, plateaus)
7. RESULTS (final stats, current)
8. CLOSING (call-to-action)

Every clip includes metadata:
- Section (which of 8 sections)
- Type (gym_chest, gym_back, diet, interview, etc.)
- Date/Week marker
- Exercise name (if gym)
- Weight/reps (if gym)
- Stats at that point (weight, bodyfat, etc.)
- Duration matched to voiceover
"""

def build_transformation_timeline(sentences, shots, subject_stats, progress_photos):
    """Build 8-section transformation documentary.

    Args:
        sentences: Narration sentences with timing
        shots: Available video clips/scenes
        subject_stats: Dict with start/current stats
        progress_photos: Chronological transformation photos

    Returns:
        timeline: Enhanced structure with sections, metadata, animations
    """

    timeline = {
        "subject": subject_stats.get("name", "Subject"),
        "duration_total": sentences[-1]["end"] if sentences else 0,
        "sections": {},
        "clips": [],
        "animations": [],
    }

    # ============ SECTION 1: OPENING (0-30 sec) ============
    timeline["sections"]["opening"] = {
        "title": "THE COMPLETE TRANSFORMATION",
        "duration": 30,
        "start": 0,
        "clips": [
            {
                "type": "before_after_split",
                "before_photo": progress_photos[0] if progress_photos else None,
                "after_photo": progress_photos[-1] if progress_photos else None,
                "text": f"From {subject_stats.get('start_date')} to {subject_stats.get('end_date')}",
                "animation": "split_screen_zoom_in",
                "duration": 30,
            }
        ],
    }

    # ============ SECTION 2: BEGINNING (1st sentences) ============
    beginning_sentences = [s for s in sentences
                          if s.get("section", "").upper() in ["HOOK", "BEGINNING", "STARTED"]][:3]
    beginning_clips = _select_clips_for_section(shots, "beginning", 3)

    timeline["sections"]["beginning"] = {
        "title": "THE BEGINNING",
        "duration": sum(s["dur"] for s in beginning_sentences),
        "start": 30,
        "text_overlays": [
            {
                "stat": "STARTING WEIGHT",
                "value": subject_stats.get("start_weight"),
                "unit": "lbs",
                "animation": "counter_up",
            },
            {
                "stat": "BODY FAT %",
                "value": subject_stats.get("start_bodyfat"),
                "unit": "%",
                "animation": "counter_up",
            },
        ],
        "clips": beginning_clips,
    }

    # ============ SECTION 3: DIET (diet-related sentences) ============
    diet_sentences = [s for s in sentences
                     if "diet" in s.get("text", "").lower()
                     or "nutrition" in s.get("text", "").lower()
                     or "eat" in s.get("text", "").lower()]
    diet_clips = _select_clips_for_section(shots, "diet", len(diet_sentences) * 2)

    timeline["sections"]["diet"] = {
        "title": "THE NUTRITION STRATEGY",
        "duration": sum(s["dur"] for s in diet_sentences),
        "start": timeline["sections"]["beginning"]["duration"] + 30,
        "macros": {
            "protein_grams": subject_stats.get("diet_protein", 200),
            "carbs_grams": subject_stats.get("diet_carbs", 250),
            "fat_grams": subject_stats.get("diet_fat", 65),
            "calories_daily": subject_stats.get("diet_calories", 2800),
        },
        "meals_per_day": subject_stats.get("meals_per_day", 6),
        "text_overlays": [
            {"text": "6 MEALS PER DAY", "animation": "slide_in_left"},
            {"text": "200G PROTEIN DAILY", "animation": "slide_in_right"},
            {"text": "WHOLE FOODS FOCUS", "animation": "slide_in_up"},
        ],
        "clips": diet_clips,
    }

    # ============ SECTION 4: GYM PROGRESSION ============
    gym_sentences = [s for s in sentences
                    if any(word in s.get("text", "").lower()
                           for word in ["train", "lift", "squat", "bench", "deadlift", "gym", "workout"])]

    gym_clips_by_week = {
        "week_1_4": _select_clips_for_section(shots, "gym", 4, tag="light_weights"),
        "week_5_8": _select_clips_for_section(shots, "gym", 4, tag="progressive"),
        "week_9_plus": _select_clips_for_section(shots, "gym", 4, tag="heavy"),
    }

    timeline["sections"]["gym"] = {
        "title": "GYM PROGRESSION",
        "training_split": "Push/Pull/Legs",
        "frequency": "6 days/week",
        "progression": {
            "week_1_4": {
                "focus": "Form & Technique",
                "weights": "light_to_moderate",
                "clips": gym_clips_by_week["week_1_4"],
            },
            "week_5_8": {
                "focus": "Progressive Overload",
                "weights": "moderate_to_heavy",
                "clips": gym_clips_by_week["week_5_8"],
            },
            "week_9_plus": {
                "focus": "Compound Strength",
                "weights": "heavy",
                "clips": gym_clips_by_week["week_9_plus"],
            },
        },
        "exercises": {
            "compound": ["Squat", "Deadlift", "Bench Press", "Rows"],
            "accessory": ["Curls", "Tricep Extensions", "Lateral Raises"],
        },
    }

    # ============ SECTION 5: BODY TRANSFORMATION ============
    # Progress photos every 2-4 weeks
    transformation_timeline = _build_photo_progression(progress_photos, subject_stats)

    timeline["sections"]["transformation"] = {
        "title": "THE TRANSFORMATION",
        "photos_chronological": transformation_timeline,
        "text_overlays": [
            {
                "type": "stat_counter",
                "label": "WEIGHT LOST",
                "start": subject_stats.get("start_weight"),
                "end": subject_stats.get("current_weight"),
                "unit": "lbs",
            },
            {
                "type": "stat_counter",
                "label": "BODY FAT DECREASE",
                "start": subject_stats.get("start_bodyfat"),
                "end": subject_stats.get("current_bodyfat"),
                "unit": "%",
            },
            {
                "type": "stat_counter",
                "label": "MUSCLE GAINED",
                "start": subject_stats.get("start_muscle"),
                "end": subject_stats.get("current_muscle"),
                "unit": "lbs",
            },
        ],
    }

    # ============ SECTION 6: CHALLENGES ============
    timeline["sections"]["challenges"] = {
        "title": "OVERCOMING OBSTACLES",
        "challenges": [
            {
                "challenge": subject_stats.get("challenge_1", "Motivation"),
                "solution": subject_stats.get("solution_1", "Consistency"),
            },
            {
                "challenge": subject_stats.get("challenge_2", "Plateau"),
                "solution": subject_stats.get("solution_2", "Progressive Overload"),
            },
        ],
        "clips": _select_clips_for_section(shots, "recovery", 3),
    }

    # ============ SECTION 7: RESULTS ============
    timeline["sections"]["results"] = {
        "title": "FINAL RESULTS",
        "duration_text": subject_stats.get("total_duration", "8 weeks"),
        "final_stats": {
            "weight": subject_stats.get("current_weight"),
            "bodyfat": subject_stats.get("current_bodyfat"),
            "muscle": subject_stats.get("current_muscle"),
            "strength_gains": subject_stats.get("strength_gains", {}),
        },
        "photos": [
            {
                "type": "before_after_side_by_side",
                "before": progress_photos[0],
                "after": progress_photos[-1],
            }
        ],
        "text_overlays": [
            {
                "text": f"LOST {subject_stats.get('start_weight', 0) - subject_stats.get('current_weight', 0)} LBS",
                "animation": "pop_scale",
            },
            {
                "text": f"BODY FAT DOWN TO {subject_stats.get('current_bodyfat')}%",
                "animation": "slide_in",
            },
        ],
    }

    # ============ SECTION 8: CLOSING ============
    timeline["sections"]["closing"] = {
        "title": "START YOUR TRANSFORMATION",
        "duration": 15,
        "message": subject_stats.get("closing_message", "Your transformation starts now."),
        "cta": "Like, Subscribe, and Start Today",
        "animation": "fade_in_text",
    }

    return timeline


def _select_clips_for_section(shots, section_type, count, tag=None):
    """Select best clips for a section based on type."""
    selected = []
    for shot in shots[:count]:
        clip = {
            "shot_id": shot.get("id"),
            "src": shot.get("src"),
            "cat": shot.get("cat"),
            "duration": shot.get("len", 2.5),
            "section_type": section_type,
            "tag": tag,
        }
        selected.append(clip)
    return selected


def _build_photo_progression(photos, stats):
    """Build chronological progression timeline from photos."""
    progression = []
    if not photos:
        return progression

    weeks = len(photos)
    interval = max(1, stats.get("total_days", 56) // weeks)

    for i, photo in enumerate(photos):
        week = (i * interval) // 7
        progression.append({
            "week": week,
            "date": stats.get(f"photo_{i}_date"),
            "image": photo,
            "stats": {
                "weight": stats.get(f"weight_week_{week}"),
                "bodyfat": stats.get(f"bodyfat_week_{week}"),
            },
            "animation": "fade_morph" if i > 0 else "fade_in",
        })

    return progression


# Example usage:
SAMPLE_STATS = {
    "name": "Rajab Butt",
    "start_date": "January 1, 2018",
    "end_date": "August 15, 2018",
    "start_weight": 185,
    "current_weight": 165,
    "start_bodyfat": 22,
    "current_bodyfat": 10,
    "start_muscle": 140,
    "current_muscle": 155,
    "diet_protein": 200,
    "diet_carbs": 250,
    "diet_fat": 65,
    "diet_calories": 2800,
    "meals_per_day": 6,
    "total_duration": "8 months",
    "challenge_1": "Staying consistent during work travels",
    "solution_1": "Flexible meal prep and portable workouts",
    "challenge_2": "Breaking through a plateau at month 4",
    "solution_2": "Increased training volume and progressive overload",
    "closing_message": "Discipline is the muscle that builds muscle.",
}
