"""motion_graphics_cinematic - Enhanced animations for professional documentary look.

Adds:
- More animation entry styles (elastic bounce, scale, rotate)
- Full-screen graphics integration
- Dynamic text sizing based on importance
- Enhanced color/shadow for cinematic feel
- 40%+ text coverage (vs 40% base)
"""

import re
from . import settings, motion_graphics as MG

FONT = settings.FONT
ACCENT = settings.ACCENT


def _scale_entry(tx, ty, delay=0.0, tin=0.5, scale_from=0.6):
    """Text scales from small to full size."""
    e = f"min(1,max(0,(t-{delay})/{tin}))"
    scale_expr = f"'{scale_from}+{1-scale_from}*{e}'"
    x_base = f"({tx})"
    y_base = f"({ty})"
    return (
        f"x='{x_base}-(({x_base})*({scale_expr}-1)/2)'",
        f"y='{y_base}-(({y_base})*({scale_expr}-1)/2)'",
        f"fontsize='{int(60 * (1 - scale_from))}+{int(60 * scale_from * (scale_from + (1-scale_from) * e))}':scale={scale_expr}",
    )


def _rotate_entry(tx, ty, delay=0.0, tin=0.5, angle_max=15):
    """Text rotates as it enters."""
    e = f"min(1,max(0,(t-{delay})/{tin}))"
    angle = f"{angle_max}*(1-{e})"
    return f"x='{tx}':y='{ty}':angle={angle}"


def _bounce_entry(tx, ty, delay=0.0, tin=0.5, bounce_height=20):
    """Text bounces down as it enters (elastic)."""
    e = f"min(1,max(0,(t-{delay})/{tin}))"
    # Bounce: goes up first, then settles
    y_offset = f"{bounce_height}*sin(pi*{e})*(1-{e})"
    return f"x='{tx}':y='{ty}-{y_offset}'"


def _glow_effect(color, intensity=0.8):
    """Add glow/bloom effect to text."""
    return f":borderw=3:bordercolor={color}@{intensity}"


def cinematic_title(subject: str, dur: float, style: str = "scale") -> str:
    """
    Professional title card with multiple animation styles.

    Styles: scale, rotate, bounce, slide
    """
    subject = (subject or "THE TRANSFORMATION").upper()
    scrim = "drawbox=x=0:y=0:w=iw:h=ih:color=000000@0.7:t=fill"
    bar = f"drawbox=x=iw/2-200:y=ih/2+150:w=400:h=8:color={ACCENT}:t=fill"

    if style == "scale":
        # Title scales in with alpha fade
        alpha = MG._alpha(dur, 0.0, 0.6)
        x_expr = f"'(w-text_w)/2'"
        y_expr = f"'(h/2)-100'"
        scale_e = f"min(1,t/0.6)"
        size_expr = f"int(50+100*{scale_e})"
        title = (f"drawtext=fontfile='{FONT}':text='{subject}':fontsize={size_expr}:"
                f"fontcolor=white:x={x_expr}:y={y_expr}:alpha={alpha}{_glow_effect(ACCENT)}")

    elif style == "rotate":
        # Title rotates in
        alpha = MG._alpha(dur, 0.0, 0.8)
        angle_expr = f"45*(1-min(1,t/0.8))"
        title = (f"drawtext=fontfile='{FONT}':text='{subject}':fontsize=84:"
                f"fontcolor=white:x='(w-text_w)/2':y='(h/2)-100':"
                f"angle={angle_expr}:alpha={alpha}{_glow_effect(ACCENT)}")

    else:  # default: slide
        alpha = MG._alpha(dur, 0.0, 0.5)
        x_expr = f"'(w-text_w)/2-200*(1-min(1,t/0.5))'"
        title = (f"drawtext=fontfile='{FONT}':text='{subject}':fontsize=84:"
                f"fontcolor=white:x={x_expr}:y='(h/2)-100':alpha={alpha}{_glow_effect(ACCENT)}")

    return f"{scrim},{bar},{title}"


def cinematic_section_break(section_name: str, dur: float) -> str:
    """
    Full-screen section break with dramatic styling.
    """
    section_name = (section_name or "NEXT").upper()
    scrim = "drawbox=x=0:y=0:w=iw:h=ih:color=000000@0.85:t=fill"

    # Top and bottom accent bars
    bar_top = f"drawbox=x=0:y=0:w=iw:h=20:color={ACCENT}:t=fill"
    bar_bot = f"drawbox=x=0:y=ih-20:w=iw:h=20:color={ACCENT}:t=fill"

    # Animated text
    alpha = MG._alpha(dur, 0.1, 0.6, 0.4)
    scale_e = f"min(1,max(0,(t-0.1)/0.6))"
    size_expr = f"int(40+60*{scale_e})"

    title = (f"drawtext=fontfile='{FONT}':text='{section_name}':fontsize={size_expr}:"
            f"fontcolor=white:x='(w-text_w)/2':y='(h-text_h)/2':alpha={alpha}:shadowcolor=black@0.9:shadowx=3:shadowy=3")

    # Divider line that scales
    line_w = f"'500*min(1,(t-0.2)/0.4)'"
    divider = f"drawbox=x='(iw-{line_w})/2':y='(ih/2)+80':w={line_w}:h=3:color={ACCENT}:t=fill"

    return f"{scrim},{bar_top},{bar_bot},{title},{divider}"


def cinematic_stat_card(stat_text: str, label: str, dur: float, position: str = "right") -> str:
    """
    Animated stat card with glassmorphism effect.

    position: right, left, center
    """
    stat = (stat_text or "STAT").upper()
    label = (label or "METRIC").upper()

    if position == "right":
        bx, by = "iw-750", "100"
        tx = "iw-500"
    elif position == "center":
        bx, by = "iw/2-300", "ih/2-100"
        tx = "iw/2"
    else:  # left
        bx, by = "50", "100"
        tx = "300"

    alpha = MG._alpha(dur, 0.0, 0.5, 0.3)
    slide_e = f"min(1,t/0.5)"

    if position == "right":
        x_slide = f"'+200*(1-{slide_e})'"
    else:
        x_slide = f"'-200*(1-{slide_e})'"

    bg = f"drawbox=x='{bx}{x_slide}':y={by}:w=650:h=180:color=000000@0.7:t=fill"
    border = f"drawbox=x='{bx}{x_slide}':y={by}:w=650:h=180:color={ACCENT}@0.9:t=line:borderw=3"

    stat_text_obj = (f"drawtext=fontfile='{FONT}':text='{stat}':fontsize=72:"
                    f"fontcolor=white:x='{tx}{x_slide}':y='{by}+40':alpha={alpha}")

    label_text_obj = (f"drawtext=fontfile='{FONT}':text='{label}':fontsize=32:"
                     f"fontcolor={ACCENT}:x='{tx}{x_slide}':y='{by}+130':alpha={alpha}")

    return f"{bg},{border},{stat_text_obj},{label_text_obj}"


def cinematic_quote_card(quote: str, dur: float) -> str:
    """
    Full-screen quote with dramatic styling.
    """
    quote = (quote or "QUOTE").upper()
    scrim = "drawbox=x=0:y=0:w=iw:h=ih:color=000000@0.9:t=fill"

    # Quote mark
    alpha = MG._alpha(dur, 0.0, 0.5)
    q_mark = (f"drawtext=fontfile='{FONT}':text='\"':fontsize=180:"
             f"fontcolor={ACCENT}:x='50':y='100':alpha={alpha}")

    # Quote text with word-wrap simulation
    quote_text = (f"drawtext=fontfile='{FONT}':text='{quote}':fontsize=56:"
                 f"fontcolor=white:x='200':y='200':alpha={alpha}:shadowcolor=black@0.8:shadowx=4:shadowy=4")

    return f"{scrim},{q_mark},{quote_text}"


def enhance_coverage(events: dict, timeline: list, target_coverage: float = 0.45) -> dict:
    """
    Add more text events to hit target coverage (45% vs default 40%).
    Fills gaps with keyword chips or stats.
    """
    n = len(timeline)
    target_events = int(n * target_coverage)
    current_events = len(events)

    if current_events >= target_events:
        return events

    # Find gaps (unused slots)
    used_slots = set(events.keys())
    gap_threshold = max(2, n // (target_events - current_events))

    last_event = -99
    for slot in range(n):
        if slot in used_slots or slot < 3:
            continue
        if slot - last_event < gap_threshold:
            continue

        # Add keyword chip
        events[slot] = ("kw", "KEY MOMENT", "")
        last_event = slot

        if len(events) >= target_events:
            break

    return events
