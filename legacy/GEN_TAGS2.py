#!/usr/bin/env python3
"""Emit vision_tags2.json from the manual visual classification of the
747 new scenes (38 contact sheets reviewed cell by cell)."""

import json

T = {}


def put(ids, cat, g="m", use=1, q=1):
    for i in (ids if isinstance(ids, (list, range)) else [ids]):
        T[str(i)] = [cat, g, use, q]


def zero(ids):
    for i in (ids if isinstance(ids, (list, range)) else [ids]):
        T[str(i)] = ["x", "n", 0, 0]


# ---- ryan_bts_a : Graham Norton (0-14)
put([1, 4], "ryan_interview", q=2)
put([0, 2, 3, 7, 9, 10, 12, 13], "ryan_interview", q=1)
zero([5, 6, 8, 11, 14])

# ---- ryan_bts_b : DP&W / Cavill-rumor video (15-47)
put([15, 17, 20, 22, 23, 25, 26, 33, 41, 43, 46], "deadpool_suit", q=2)
put([27, 42], "ryan_movie", q=2)
put([21, 39, 44, 45], "ryan_movie", q=1)
put(19, "ryan_movie", g="n", q=1)
zero([16, 18, 24, 28, 29, 30, 31, 32, 34, 35, 36, 37, 38, 40, 47])

# ---- ryan_bts_c : Free Guy BTS (48-71)
put([48, 50, 63], "ryan_movie", q=2)
put([55, 60, 64, 70], "ryan_bts", q=2)
put([56, 57, 58, 59], "food", q=2)
put([66, 68], "ryan_movie", q=1)
put(61, "deadpool_suit", q=1)
put(65, "deadpool_title", g="n", q=1)
zero([49, 51, 52, 53, 54, 62, 67, 69, 71])

# ---- ryan_bts_d : Deadpool 2 BTS (72-86)
put([75, 78, 83], "deadpool_suit", q=2)
put(76, "deadpool_suit", q=1)
put([73, 80], "ryan_movie", q=1)
put(77, "ryan_bts", q=1)
zero([72, 74, 79, 81, 82, 84, 85, 86])

# ---- ryan_coach_a : MH Train Like Ryan Reynolds (87-132)
put(87, "ryan_gym", q=2)
put(88, "deadpool_suit", q=1)
put([89, 93, 95, 99, 104, 107, 110, 131], "coach_talk", q=1)
put([91, 94, 96, 111, 112], "coach_gym", q=2)
put([97, 98, 100, 101, 102, 103, 105, 106, 108, 109], "recovery", q=2)
put(92, "ryan_bts", q=1)
put([120, 121, 122], "back", q=2)
put(123, "back", q=1)
put([124, 125, 126, 127, 128], "cardio", q=2)
put([113, 114, 115, 117], "legs", q=2)
put(116, "legs", q=1)
put([118, 119], "chest", q=2)
zero([90, 129, 130, 132])

# ---- ryan_coach_b : Don Saladino podcast (133-171)
put([134, 138, 141, 143, 145, 147, 149, 150, 152, 157, 159, 161, 164,
     166, 168, 170], "coach_talk", q=2)
put([139, 144, 146, 148, 153, 155, 158, 163, 167], "coach_talk", q=1)
zero([133, 135, 136, 137, 140, 142, 151, 154, 156, 160, 162, 165,
      169, 171])

# ---- ryan_gym_a : transformation explainer (172-281)
put([172, 173, 176, 186, 228, 233, 234, 235, 236, 240, 241, 245, 247],
    "ryan_photo", q=2)
put(246, "ryan_photo", q=1)
put(174, "coach_talk", q=2)
put(261, "coach_talk", q=1)
put([175, 242, 264], "ryan_gym", q=2)
put(281, "ryan_gym", q=1)
put([177, 182, 221, 262], "coach_gym", q=1)
put(178, "coach_gym", q=2)
put(180, "ryan_interview", q=1)
put([183, 251], "ryan_movie", q=2)
put(187, "ryan_movie", q=1)
put([184, 243, 248], "deadpool_suit", q=2)
put([185, 244, 249, 250], "deadpool_suit", q=1)
put([188, 196, 201, 217, 219, 224, 227], "food", g="n", q=2)
put([202, 206, 207, 208, 211, 216, 218, 220, 223, 226, 238, 267],
    "food", g="n", q=1)
put(193, "arms", q=2)
put([190, 191, 198, 199, 209, 212, 222, 225, 229, 230], "arms", q=1)
put(232, "chest", q=2)
put([194, 266, 271, 274], "chest", q=1)
put([200, 204], "shoulders", q=2)
put(272, "shoulders", q=1)
put(197, "legs", q=2)
put([192, 263], "legs", q=1)
put([269, 270], "back", q=2)
put([205, 260], "back", q=1)
put([203, 210], "cardio", q=1)
put([195, 268], "recovery", g="n", q=1)
put(265, "ryan_event", q=2)
put(215, "ryan_shirtless", q=1)
put([275, 277], "legs", q=2)
put(276, "chest", q=2)
put(278, "back", q=2)
put(279, "cardio", q=2)
zero([179, 181, 189, 213, 214, 231, 237, 239, 252, 253, 254, 255, 256,
      257, 258, 259, 280])

# ---- ryan_gym_b : Blade/GL era compilation (282-362)
put([282, 317, 328], "ryan_movie", q=2)
put([283, 284, 285, 295, 316, 318, 319, 320, 321, 353], "ryan_movie",
    q=1)
put([286, 287, 290, 292, 297, 300, 302, 304, 305, 307, 331],
    "ryan_gym", q=2)
put([298, 308, 335, 338], "ryan_gym", q=1)
put([291, 293, 299, 310, 315, 330, 332, 341], "ryan_shirtless", q=2)
put([301, 303, 309, 342], "ryan_shirtless", q=1)
put(294, "ryan_abs", q=2)
put(314, "ryan_bts", q=2)
put([306, 311, 312, 313], "ryan_bts", q=1)
put([323, 324, 326, 327, 355, 356, 357, 358, 359, 360, 361],
    "ryan_photo", q=2)
put([325, 329, 333, 334, 336, 337, 351, 352], "ryan_photo", q=1)
put(339, "ryan_interview", q=2)
put([340, 343, 354], "ryan_press", q=2)
put(list(range(344, 351)), "deadpool_suit", q=2)
zero([322, 362])

# ---- ryan_int_a : duplicate of deadpool_2016 compilation (363-436)
zero(range(363, 437))

# ---- ryan_int_b : Ryan + Jackman puppy interview (437-551)
for i in range(437, 552):
    T[str(i)] = ["ryan_interview", "m", 1, 1]
put([439, 457, 464, 465, 483, 486, 496, 502, 503, 507, 509, 511, 515,
     521, 522, 525, 527, 529, 534, 538, 542, 544, 546],
    "ryan_interview", q=2)
zero([442, 448, 449, 454, 461, 463, 466, 471, 481, 485, 490, 500, 517,
      547, 550, 551])

# ---- ryan_int_c : WIRED autocomplete Ryan + Gyllenhaal (552-700)
for i in range(552, 701):
    T[str(i)] = ["ryan_interview", "m", 1, 1]
put([565, 567, 579, 583, 585, 592, 598, 607, 609, 614, 621, 623, 625,
     633, 661, 664, 667, 678], "ryan_interview", q=2)
zero([553, 554, 556, 557, 560, 562, 564, 568, 571, 573, 575, 577, 584,
      586, 594, 596, 597, 600, 601, 603, 605, 611, 612, 616, 618, 622,
      627, 631, 634, 636, 638, 639, 660, 662, 668, 670, 671, 672, 674,
      675, 676])

# ---- ryan_mh_a : duplicate of ryan_coach_a MH video (701-746)
zero(range(701, 747))

with open("vision_tags2.json", "w") as f:
    json.dump(T, f)

usable = sum(1 for v in T.values() if v[2])
ryan = sum(1 for v in T.values()
           if v[2] and v[0].startswith(("ryan", "deadpool", "coach")))
print(f"[OK] vision_tags2.json: {len(T)} scenes, {usable} usable, "
      f"{ryan} Ryan/coach")
