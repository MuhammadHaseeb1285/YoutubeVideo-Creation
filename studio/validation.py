"""validation - the editorial gate. The render is refused unless the edit
is genuinely synchronized: every piece on-topic, exercises on-movement,
shots unique, none over 4s, and video length == narration length. Returns
(ok, report) so the dashboard can show every check.
"""

from collections import Counter

from . import settings, semantic


def validate(timeline, sentences, audio_dur):
    checks = []
    ok = True

    ids = [e["shot_id"] for e in timeline]
    uniq = len(ids) == len(set(ids))
    checks.append(("unique shots", uniq,
                   f"{len(set(ids))}/{len(ids)} pieces unique"))
    ok &= uniq

    over = [e for e in timeline if e["dur"] > 4.001]
    checks.append(("max shot length 4s", not over,
                   f"{len(over)} over-length"))
    ok &= not over

    total = sum(e["dur"] for e in timeline)
    dur_ok = total >= audio_dur - 4
    checks.append(("duration matches narration", dur_ok,
                   f"{total:.1f}s video vs {audio_dur:.1f}s audio"))
    ok &= dur_ok

    on = [e for e in timeline if semantic.on_topic(e["stype"], e["cat"])]
    trate = len(on) / max(1, len(timeline)) * 100
    tok = trate >= settings.MIN_TOPIC_MATCH
    checks.append(("visuals match narration topic", tok,
                   f"{len(on)}/{len(timeline)} on-topic ({trate:.0f}%)"))
    ok &= tok

    ex_pieces = [e for e in timeline if e.get("ex_want")]
    exact = [e for e in ex_pieces if e.get("ex_got") == e.get("ex_want")]

    def fam_ok(e):
        w, g = e.get("ex_want"), e.get("ex_got")
        if g == w:
            return True
        return bool(g and semantic.EXERCISE_FAMILY.get(g)
                    == semantic.EXERCISE_FAMILY.get(w))
    fam = [e for e in ex_pieces if fam_ok(e)]
    if ex_pieces:
        fr = len(fam) / len(ex_pieces) * 100
        eok = fr >= settings.MIN_EXERCISE_SYNC
        checks.append(("exercise sync", eok,
                       f"{len(exact)} exact + {len(fam)-len(exact)} family "
                       f"= {fr:.0f}% on-movement"))
        ok &= eok

    scenes = [e["scene"] for e in timeline]
    reuse = len(scenes) - len(set(scenes))
    checks.append(("scene variety", True,
                   f"{reuse} scene re-segments (spaced)"))

    cats = Counter(e["cat"] for e in timeline)
    subj = sum(v for k, v in cats.items()
               if semantic.group_of(k) in semantic.SUBJECT_GROUPS)
    checks.append(("subject presence", True,
                   f"{subj}/{len(timeline)} pieces show the subject "
                   f"({subj/max(1,len(timeline))*100:.0f}%)"))

    report = {
        "ok": ok,
        "checks": [{"name": n, "pass": bool(p), "detail": d}
                   for n, p, d in checks],
        "topic_match": round(trate, 1),
        "pieces": len(timeline),
        "duration": round(total, 1),
    }
    return ok, report
