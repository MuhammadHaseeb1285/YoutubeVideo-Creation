"""timeline - assemble the edit. Walk the narration in spoken order, ask
the Selector for the best shot at each moment, trim it to a paced 1-4s
piece, and lay pieces back-to-back so total video length equals narration
length. Records what was wanted vs got for validation.
"""

import json

from . import settings, semantic
from .selection import Selector


def _cap(cat, max_clip):
    """Documentary pacing by visual group: interviews breathe, workouts
    cut fast. Never exceeds the project's max_clip setting."""
    g = semantic.group_of(cat)
    if g in ("subject_talk", "coach"):
        return max_clip                     # interviews breathe
    if g in ("subject_gym", "ex_chest", "ex_back", "ex_legs",
             "ex_should", "ex_cardio"):
        return min(2.2, max_clip)           # workouts cut fast
    return min(3.0, max_clip)


def build(sentences, shots, progress_cb=None, max_clip=None):
    max_clip = float(max_clip or settings.MAX_PIECE)
    sel = Selector(shots)
    timeline = []
    carry = 0.0
    n = len(sentences)
    for si, sent in enumerate(sentences):
        remaining = sent["dur"] + carry
        t_cursor = sent["start"] - carry
        while remaining > 0.35:
            sh = sel.pick(sent["type"], sent.get("ex"))
            if sh is None:
                return timeline
            cap = _cap(sh["cat"], max_clip)
            piece = min(cap, sh["len"], remaining)
            piece = max(piece, min(1.0, remaining))
            timeline.append({
                "slot": sel.slot, "shot_id": sh["id"], "src": sh["src"],
                "source": sh["source"], "scene": sh["scene"],
                "cat": sh["cat"], "in": sh["start"], "dur": round(piece, 2),
                "at": round(t_cursor, 2), "stype": sent["type"],
                "ex_want": sent.get("ex"), "ex_got": sh.get("ex"),
                "section": sent["section"]})
            sel.commit(sh)
            remaining -= piece
            t_cursor += piece
        carry = max(0.0, remaining)
        if progress_cb and si % 5 == 0:
            progress_cb(100 * si / max(1, n),
                        f"{sel.used} shots placed")

    # close any residue so video length == narration length
    while carry > 0.05 and timeline:
        last = timeline[-1]
        room = settings.MAX_PIECE - last["dur"]
        if room > 0.01:
            add = min(room, carry)
            last["dur"] = round(last["dur"] + add, 2)
            carry -= add
        else:
            sh = sel.pick("generic")
            if sh is None:
                break
            piece = min(settings.MAX_PIECE, sh["len"], max(carry, 0.6))
            timeline.append({
                "slot": sel.slot, "shot_id": sh["id"], "src": sh["src"],
                "source": sh["source"], "scene": sh["scene"],
                "cat": sh["cat"], "in": sh["start"], "dur": round(piece, 2),
                "at": round(timeline[-1]["at"] + timeline[-1]["dur"], 2),
                "stype": "generic", "ex_want": None, "ex_got": sh.get("ex"),
                "section": "CLOSE"})
            sel.commit(sh)
            carry -= piece

    settings.TIMELINE.parent.mkdir(parents=True, exist_ok=True)
    settings.TIMELINE.write_text(json.dumps(timeline, indent=0))
    return timeline
