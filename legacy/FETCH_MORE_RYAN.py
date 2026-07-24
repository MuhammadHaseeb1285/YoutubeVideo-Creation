#!/usr/bin/env python3
"""
FETCH_MORE_RYAN - expand the Ryan Reynolds footage pool.
Targeted YouTube queries for Ryan training / BTS / interviews / coach.
Videos land in youtube_videos/ ; already-downloaded files are skipped.
"""

import subprocess
from pathlib import Path

OUT = Path("youtube_videos")
OUT.mkdir(exist_ok=True)

QUERIES = [
    ("Don Saladino trains Ryan Reynolds workout", "ryan_coach_a"),
    ("Ryan Reynolds Deadpool training behind the scenes", "ryan_bts_a"),
    ("Ryan Reynolds workout routine gym footage", "ryan_gym_a"),
    ("Ryan Reynolds Men's Health cover workout", "ryan_mh_a"),
    ("Ryan Reynolds interview Deadpool body transformation", "ryan_int_a"),
    ("Deadpool and Wolverine behind the scenes training", "ryan_bts_b"),
    ("Ryan Reynolds Free Guy behind the scenes", "ryan_bts_c"),
    ("Don Saladino celebrity training interview", "ryan_coach_b"),
    ("Ryan Reynolds Hugh Jackman training", "ryan_int_b"),
    ("Ryan Reynolds gym transformation 2024", "ryan_gym_b"),
    ("Deadpool 2 behind the scenes gag reel", "ryan_bts_d"),
    ("Ryan Reynolds talk show funny interview fitness", "ryan_int_c"),
]


def main():
    print("\n" + "=" * 70)
    print("FETCHING ADDITIONAL RYAN REYNOLDS FOOTAGE")
    print("=" * 70)
    got = fail = 0
    for query, name in QUERIES:
        out = OUT / f"{name}.mp4"
        if out.exists():
            print(f"[=] {name} exists ({out.stat().st_size/1e6:.0f} MB)")
            got += 1
            continue
        print(f"[*] {name}: {query}")
        from CELEB_VIDEO import download_one
        if download_one(query, out):
            print(f"    OK ({out.stat().st_size/1e6:.0f} MB)")
            got += 1
        else:
            print("    FAILED after all retries")
            fail += 1
    print(f"\n[OK] {got} videos ready, {fail} failed")
    print("[->] next: python INDEX_NEW.py")


if __name__ == "__main__":
    main()
