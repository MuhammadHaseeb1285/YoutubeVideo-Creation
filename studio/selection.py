"""selection - the clip-selection engine. Holds the pool state and, for
every narration moment, ranks the ENTIRE unused pool by semantic relevance
minus a repetition cost, returning the single best shot. No buckets, no
filename matching, no "next available clip".
"""

from collections import Counter

from . import settings, semantic


class Selector:
    def __init__(self, shots):
        self.all = {s["id"]: s for s in shots}
        self.unused = dict(self.all)
        self.scene_used = Counter()
        self.scene_last_slot = {}
        self.last_src = []
        self.last_cat = []
        self.slot = 0
        self.total = len(shots)

    def refill(self):
        """Allow shots to be reused once the fresh pool is exhausted, so the
        timeline can still reach the full narration length. Repetition
        penalties (scene reuse + spacing) keep repeats spread out and favour
        the least-recently-used footage."""
        self.unused = dict(self.all)

    def penalty(self, sh):
        p = 0.0
        p += 260 * self.scene_used[sh["scene"]]
        if self.slot - self.scene_last_slot.get(sh["scene"], -999) \
                < settings.SCENE_SPACING:
            p += 800
        if sh["source"] in self.last_src[-2:]:
            p += 180
        if sh["cat"] in self.last_cat[-1:]:
            p += 70
        return p

    def pick(self, stype, want_ex=None):
        best, best_s = None, -1e18
        for sh in self.unused.values():
            s = semantic.relevance(sh, stype, want_ex) - self.penalty(sh)
            if s > best_s:
                best_s, best = s, sh
        return best

    def commit(self, sh):
        del self.unused[sh["id"]]
        self.scene_used[sh["scene"]] += 1
        self.scene_last_slot[sh["scene"]] = self.slot
        self.last_src.append(sh["source"])
        self.last_cat.append(sh["cat"])
        self.slot += 1

    @property
    def used(self):
        return self.total - len(self.unused)

    @property
    def remaining(self):
        return len(self.unused)
