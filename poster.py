#!/usr/bin/env python3
"""Generate static PNG or animated GIF typographic repetition posters."""

import argparse
import colorsys
import math
import os
import sys
from PIL import Image, ImageDraw, ImageFont

# Cross-platform candidate font paths per style (first existing file wins)
FONT_CANDIDATES = {
    "sans": [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/System/Library/Fonts/HelveticaNeue.ttc",
        "/System/Library/Fonts/Helvetica.ttc",
        "C:\\Windows\\Fonts\\arialbd.ttf",
    ],
    "serif": [
        "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
        "/System/Library/Fonts/Supplemental/Georgia Bold.ttf",
        "/System/Library/Fonts/Supplemental/Times New Roman Bold.ttf",
        "/System/Library/Fonts/NewYork.ttf",
        "C:\\Windows\\Fonts\\georgiab.ttf",
    ],
    "mono": [
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
        "/System/Library/Fonts/Menlo.ttc",
        "/System/Library/Fonts/Supplemental/Courier New Bold.ttf",
        "/System/Library/Fonts/Monaco.ttf",
        "C:\\Windows\\Fonts\\consolab.ttf",
    ],
}


def resolve_font(font_key: str, override_path: str = "") -> str:
    if override_path:
        if os.path.exists(override_path):
            return override_path
        sys.exit(f"error: custom font file missing: {override_path}")
    for path in FONT_CANDIDATES[font_key]:
        if os.path.exists(path):
            return path
    sys.exit(
        f"error: no font file found for '{font_key}'. "
        f"Checked: {', '.join(FONT_CANDIDATES[font_key])}. "
        f"Pass --font-path to specify a .ttf/.ttc/.otf file."
    )


def parse_reps(s: str) -> list[int]:
    s = s.strip()
    if not s:
        return []
    if "," in s:
        return [int(x.strip()) for x in s.split(",") if x.strip()]
    if s.isdigit():
        return [int(ch) for ch in s]
    raise ValueError(f"invalid format '{s}'")


def hexc(color_str: str) -> tuple[int, int, int]:
    c = color_str.strip().lstrip("#")
    if len(c) == 3:
        c = "".join(ch * 2 for ch in c)
    if len(c) != 6:
        raise ValueError(f"invalid hex color: {color_str}")
    return (int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16))


def fit_size(font_path: str, text: str, target_w: float) -> int:
    """Binary search for the font size that fits target_w."""
    lo, hi = 1, 4096
    best = 1
    while lo <= hi:
        mid = (lo + hi) // 2
        font = ImageFont.truetype(font_path, mid)
        w = font.getlength(text)
        if w <= target_w:
            best = mid
            lo = mid + 1
        else:
            hi = mid - 1
    return best


def row_metrics(font_path: str, text: str, size: int, tight: bool) -> tuple[float, float]:
    font = ImageFont.truetype(font_path, size)
    if tight:
        bbox = font.getbbox(text)  # (left, top, right, bottom)
        return bbox[1], bbox[3] - bbox[1]
    ascent, descent = font.getmetrics()
    return 0, ascent + descent


def stack_height(font_path: str, sizes: list[int], tight: bool, gap: float) -> float:
    total = 0.0
    for s in sizes:
        _, h = row_metrics(font_path, "Hg", s, tight)
        total += h
    if len(sizes) > 1:
        total += gap * (len(sizes) - 1)
    return total


def compute_colors(mode: str, count: int, ink: tuple[int, int, int],
                   accent: tuple[int, int, int], hue_offset: float = 0.0) -> list[tuple[int, int, int]]:
    if mode == "alternate":
        return [ink if i % 2 == 0 else accent for i in range(count)]
    if mode == "rainbow":
        n = max(1, count - 1)
        return [
            tuple(
                int(v * 255)
                for v in colorsys.hsv_to_rgb(((260 / 360 * i / n) + hue_offset) % 1.0, 0.85, 0.62)
            )
            for i in range(count)
        ]
    return [ink] * count


def draw_stack(draw: ImageDraw.ImageDraw, font_path: str, rows: list[str],
               sizes: list[int], x: float, y: float, tight: bool,
               gap: float, mode: str, colors: list[tuple[int, int, int]],
               x_offsets: list[float] | None = None,
               y_offsets: list[float] | None = None):
    curr_y = y
    for i, (text, size, color) in enumerate(zip(rows, sizes, colors)):
        font = ImageFont.truetype(font_path, size)
        top_offset, h = row_metrics(font_path, "Hg", size, tight)
        dx = x_offsets[i] if x_offsets else 0.0
        dy = y_offsets[i] if y_offsets else 0.0
        draw.text((x + dx, curr_y - top_offset + dy), text, font=font, fill=color)
        curr_y += h + gap


def render_animated_gif(
    out_path: str,
    width_px: int,
    height_px: int,
    pad_px: float,
    gap_px: float,
    font_path: str,
    rows: list[str],
    sizes: list[int],
    tight: bool,
    mode: str,
    color_mode: str,
    ink: tuple[int, int, int],
    accent: tuple[int, int, int],
    paper: tuple[int, int, int],
    anim_style: str,
    frames_count: int,
    fps: int,
    out_scale: int = 1,
):
    frames: list[Image.Image] = []
    n_rows = len(rows)
    center = (n_rows - 1) / 2.0
    max_dist = max(1.0, center)
    phase_step = 2.0 * math.pi / max(2.0, center + 1.0)
    target_size = (max(1, width_px // out_scale), max(1, height_px // out_scale))

    for f in range(frames_count):
        t = f / frames_count  # 0.0 .. <1.0
        phase = 2.0 * math.pi * t
        img = Image.new("RGB", (width_px, height_px), paper)
        draw = ImageDraw.Draw(img)

        x_offsets = [0.0] * n_rows
        y_offsets = [0.0] * n_rows
        frame_sizes = list(sizes)
        frame_colors = compute_colors(color_mode, n_rows, ink, accent, 0.0)

        if anim_style == "kinetic":
            # Radiates symmetrically from the center row outward
            for i in range(n_rows):
                dist = abs(i - center)
                row_phase = phase - dist * phase_step
                x_offsets[i] = math.sin(row_phase) * (pad_px * 0.30)
                scale = 1.0 + 0.03 * math.cos(row_phase)
                frame_sizes[i] = max(1, int(round(sizes[i] * scale)))
                base_w = ImageFont.truetype(font_path, sizes[i]).getlength(rows[i])
                new_w = ImageFont.truetype(font_path, frame_sizes[i]).getlength(rows[i])
                x_offsets[i] += (base_w - new_w) / 2.0
                if color_mode == "solid":
                    blend = 0.5 + 0.5 * math.sin(row_phase)
                    frame_colors[i] = tuple(
                        int(round(ink[c] * (1.0 - blend * 0.85) + accent[c] * (blend * 0.85)))
                        for c in range(3)
                    )
                elif color_mode == "rainbow":
                    hue = ((260 / 360 * (dist / max_dist)) - t) % 1.0
                    frame_colors[i] = tuple(int(v * 255) for v in colorsys.hsv_to_rgb(hue, 0.85, 0.62))
        elif anim_style == "wave":
            for i in range(n_rows):
                dist = abs(i - center)
                sign = 0.0 if i == center else (1.0 if i > center else -1.0)
                row_phase = phase - dist * phase_step
                x_offsets[i] = math.sin(row_phase) * (pad_px * 0.35)
                y_offsets[i] = sign * math.cos(row_phase) * (gap_px * 0.25)
        elif anim_style == "pulse":
            for i in range(n_rows):
                dist = abs(i - center)
                row_phase = phase - dist * 0.85
                scale = 1.0 + 0.045 * math.sin(row_phase)
                frame_sizes[i] = max(1, int(round(sizes[i] * scale)))
                base_w = ImageFont.truetype(font_path, sizes[i]).getlength(rows[i])
                new_w = ImageFont.truetype(font_path, frame_sizes[i]).getlength(rows[i])
                x_offsets[i] = (base_w - new_w) / 2.0
        elif anim_style == "rainbow-shift":
            for i in range(n_rows):
                dist = abs(i - center)
                hue = ((260 / 360 * (dist / max_dist)) - t) % 1.0
                frame_colors[i] = tuple(int(v * 255) for v in colorsys.hsv_to_rgb(hue, 0.85, 0.62))
        elif anim_style == "cascade":
            for i in range(n_rows):
                dist = abs(i - center)
                row_t = (t - dist * (0.35 / max(1.0, center + 1.0))) % 1.0
                if row_t < 0.25:
                    p = row_t / 0.25
                    ease = 1.0 - (1.0 - p) ** 3
                    x_offsets[i] = (1.0 - ease) * (-width_px * 0.15)
                elif row_t > 0.75:
                    p = (row_t - 0.75) / 0.25
                    ease = p ** 3
                    x_offsets[i] = ease * (width_px * 0.15)

        draw_stack(
            draw,
            font_path,
            rows,
            frame_sizes,
            pad_px,
            pad_px * 0.5,
            tight,
            gap_px,
            mode,
            frame_colors,
            x_offsets=x_offsets,
            y_offsets=y_offsets,
        )
        if out_scale > 1:
            img = img.resize(target_size, Image.Resampling.LANCZOS)
        frames.append(img.convert("P", palette=Image.Palette.ADAPTIVE, colors=256))

    duration_ms = max(20, int(round(1000 / fps)))
    frames[0].save(
        out_path,
        save_all=True,
        append_images=frames[1:],
        duration=duration_ms,
        loop=0,
        optimize=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a typographic repetition poster.")
    parser.add_argument("word", help="Word or phrase to repeat")
    parser.add_argument("--reps", default="42124", help="Row repetition pattern (e.g. 42124 or 4,2,1,2,4)")
    parser.add_argument("--font", default="sans", choices=list(FONT_CANDIDATES.keys()))
    parser.add_argument("--font-path", default="", help="Custom path to a .ttf/.ttc/.otf font file")
    parser.add_argument("--upper", action="store_true", help="Convert phrase to uppercase")
    parser.add_argument("--sep", default="", help="Separator between repeated words")
    parser.add_argument("--width", type=int, default=800, help="Poster width in px")
    parser.add_argument("--pad", type=int, default=40, help="Horizontal padding in px")
    parser.add_argument("--gap", type=float, default=10.0, help="Gap between rows in px")
    parser.add_argument("--scale", type=int, default=2, help="Render scale multiplier")
    parser.add_argument("--tight", action="store_true", help="Use tight bounding box height")
    parser.add_argument("--mode", default="normal", help="Drawing mode")
    parser.add_argument("--colors", default="solid", choices=["solid", "alternate", "rainbow"])
    parser.add_argument("--ink-color", default="#111111")
    parser.add_argument("--accent", default="#e63946")
    parser.add_argument("--paper", default="#f8f9fa")
    parser.add_argument("--animate", action="store_true", help="Export an animated GIF instead of a static PNG")
    parser.add_argument(
        "--anim-style",
        default="kinetic",
        choices=["kinetic", "wave", "pulse", "rainbow-shift", "cascade"],
        help="Animation style when --animate is enabled",
    )
    parser.add_argument("--frames", type=int, default=48, help="Number of frames for animated GIF")
    parser.add_argument("--fps", type=int, default=24, help="Frames per second for animated GIF")
    parser.add_argument("--out", default="", help="Output file path")
    args = parser.parse_args()

    phrase = args.word.strip()
    if not phrase:
        sys.exit("error: empty phrase")
    if args.upper:
        phrase = phrase.upper()

    try:
        reps = parse_reps(args.reps)
    except ValueError as e:
        sys.exit(f"error: --reps {e} (use a digit string like 42124 or commas like 4,2,1,2,4)")
    if not reps or any(n < 1 or n > 999 for n in reps):
        sys.exit("error: repeats must be integers between 1 and 999")

    font_path = resolve_font(args.font, args.font_path)
    ink = hexc(args.ink_color)
    accent = hexc(args.accent)
    paper = hexc(args.paper)

    colors = compute_colors(args.colors, len(reps), ink, accent)
    rows = [(phrase + args.sep) * n if args.sep else phrase * n for n in reps]

    k = args.scale
    W = args.width
    target_w = (W - 2 * args.pad) * k
    sizes = [fit_size(font_path, r, target_w) for r in rows]
    gap = args.gap * k
    vertical_pad = args.pad * k if args.animate else 0
    H = int(round((stack_height(font_path, sizes, args.tight, gap) + vertical_pad) / k))

    slug = "".join(c if c.isalnum() else "-" for c in phrase.lower()).strip("-") or "poster"
    pattern_slug = "-".join(f"{n}x" for n in reps)
    ext = "gif" if args.animate else "png"
    out_path = args.out or os.path.join("output", f"{slug}-{pattern_slug}.{ext}")
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)

    if args.animate:
        render_animated_gif(
            out_path=out_path,
            width_px=W * k,
            height_px=H * k,
            pad_px=args.pad * k,
            gap_px=gap,
            font_path=font_path,
            rows=rows,
            sizes=sizes,
            tight=args.tight,
            mode=args.mode,
            color_mode=args.colors,
            ink=ink,
            accent=accent,
            paper=paper,
            anim_style=args.anim_style,
            frames_count=args.frames,
            fps=args.fps,
            out_scale=k,
        )
    else:
        img = Image.new("RGB", (W * k, H * k), paper)
        draw = ImageDraw.Draw(img)
        draw_stack(draw, font_path, rows, sizes, args.pad * k, 0.0,
                   args.tight, gap, args.mode, colors)
        img.save(out_path, "PNG")

    # ---- report (poster px, i.e. render px / k) ----
    print(f"phrase   : {phrase}")
    print(f"config   : {''.join(str(n) for n in reps)}  ({len(reps)} rows)")
    print(f"font     : {args.font} ({font_path})")
    print(
        f"rows     : {len(rows)}, fitted to {target_w // k}px row width "
        f"(poster {W}px, pad {args.pad}px)"
    )
    for i, (n, s) in enumerate(zip(reps, sizes)):
        actual = ImageFont.truetype(font_path, s).getlength(rows[i])
        print(f"  row {i + 1}: {n:2d}x  size {s / k:7.2f}px  width {actual / k:.1f}/{target_w // k}px")
    print(f"poster   : {W}x{H} px  ->  {ext.upper()} {W * k}x{H * k} (scale {k})")
    print(f"saved    : {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
