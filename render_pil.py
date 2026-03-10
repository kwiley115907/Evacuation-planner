from __future__ import annotations
from typing import List, Tuple, Dict
from PIL import Image, ImageDraw, ImageFont
import math

RC = Tuple[int, int]  # (row, col)

def _font():
    try:
        return ImageFont.load_default()
    except Exception:
        return None

def draw_path(
    img: Image.Image,
    path_rc: List[RC],
    downscale: int,
    width: int = 4,
    arrow_every_px: int = 80,
    head_len: int = 14,
    head_angle_deg: float = 28.0,
) -> Image.Image:
    """
    Draw a red route with arrowheads along the path.
    """
    out = img.copy()
    if not path_rc or len(path_rc) < 2:
        return out

    draw = ImageDraw.Draw(out)
    pts = [(int(c * downscale), int(r * downscale)) for r, c in path_rc]

    # main line
    for i in range(1, len(pts)):
        draw.line([pts[i - 1], pts[i]], fill=(255, 0, 0), width=width)

    def arrowhead(p0, p1):
        x0, y0 = p0
        x1, y1 = p1
        dx, dy = x1 - x0, y1 - y0
        L = math.hypot(dx, dy)
        if L < 1e-6:
            return
        ux, uy = dx / L, dy / L
        angle = math.radians(head_angle_deg)

        def rot(u, v, a):
            return (u * math.cos(a) - v * math.sin(a),
                    u * math.sin(a) + v * math.cos(a))

        rx1, ry1 = rot(ux, uy, angle)
        rx2, ry2 = rot(ux, uy, -angle)

        p_left = (x1 - head_len * rx1, y1 - head_len * ry1)
        p_right = (x1 - head_len * rx2, y1 - head_len * ry2)

        draw.line([p_left, (x1, y1)], fill=(255, 0, 0), width=width)
        draw.line([p_right, (x1, y1)], fill=(255, 0, 0), width=width)

    # arrowheads every N pixels
    dist_since = 0.0
    for i in range(1, len(pts)):
        ax, ay = pts[i - 1]
        bx, by = pts[i]
        seg_len = math.hypot(bx - ax, by - ay)
        if seg_len < 1e-6:
            continue

        while dist_since + seg_len >= arrow_every_px:
            t = (arrow_every_px - dist_since) / seg_len
            mx = ax + t * (bx - ax)
            my = ay + t * (by - ay)

            back = 8.0
            p0 = (mx - back * (bx - ax) / seg_len, my - back * (by - ay) / seg_len)
            p1 = (mx, my)
            arrowhead(p0, p1)

            seg_len -= (arrow_every_px - dist_since)
            ax, ay = mx, my
            dist_since = 0.0

        dist_since += seg_len

    # final arrowhead
    arrowhead(pts[-2], pts[-1])

    return out

def draw_labeled_points(
    img: Image.Image,
    points: List[Dict],
    color_rgb: Tuple[int, int, int],
    radius: int = 10,
) -> Image.Image:
    out = img.copy()
    d = ImageDraw.Draw(out)
    font = _font()

    for p in points:
        x, y = int(p["x"]), int(p["y"])
        label = str(p.get("id", ""))
        d.ellipse((x-radius, y-radius, x+radius, y+radius), fill=color_rgb, outline=(0, 0, 0))
        if label:
            d.text((x + 12, y - radius), label, fill=(0, 0, 0), font=font)

    return out

def draw_start_to_exit_labels(
    img: Image.Image,
    starts: List[Dict],
    start_to_exit: Dict[str, str],
) -> Image.Image:
    """
    Labels like "R101 → E1" near each start dot.
    start_to_exit maps start_id -> exit_id
    """
    out = img.copy()
    d = ImageDraw.Draw(out)
    font = _font()

    for s in starts:
        sid = str(s.get("id", ""))
        exid = start_to_exit.get(sid)
        if not exid:
            continue
        x, y = int(s["x"]), int(s["y"])
        text = f"{sid} \u2192 {exid}"
        d.text((x + 13, y - 25), text, fill=(255, 255, 255), font=font)
        d.text((x + 12, y - 26), text, fill=(0, 0, 0), font=font)

    return out

def draw_exit_sign(img: Image.Image, x: int, y: int, direction: str, scale: int = 1) -> Image.Image:
    """
    Draw a green EXIT sign with a directional arrow.
    direction: "up"|"down"|"left"|"right"
    """
    out = img.copy()
    d = ImageDraw.Draw(out)
    font = _font()

    w = 60 * scale
    h = 22 * scale
    pad = 4 * scale

    sx = x + 14 * scale
    sy = y - h // 2

    d.rectangle((sx, sy, sx + w, sy + h), fill=(0, 160, 0), outline=(0, 0, 0))
    d.text((sx + pad, sy + 3 * scale), "EXIT", fill=(255, 255, 255), font=font)

    ax = sx + w - 18 * scale
    ay = sy + h // 2

    if direction == "right":
        arrow = [(ax, ay - 5 * scale), (ax + 12 * scale, ay), (ax, ay + 5 * scale)]
    elif direction == "left":
        arrow = [(ax + 12 * scale, ay - 5 * scale), (ax, ay), (ax + 12 * scale, ay + 5 * scale)]
    elif direction == "up":
        arrow = [(ax + 6 * scale, ay - 8 * scale), (ax, ay + 4 * scale), (ax + 12 * scale, ay + 4 * scale)]
    else:  # down
        arrow = [(ax, ay - 4 * scale), (ax + 12 * scale, ay - 4 * scale), (ax + 6 * scale, ay + 8 * scale)]

    d.polygon(arrow, fill=(255, 255, 255))
    return out

def draw_exit_signs(
    img: Image.Image,
    exits: List[Dict],
    exit_directions: Dict[str, str],
    scale: int = 1,
) -> Image.Image:
    """
    exit_directions: exit_id -> direction
    """
    out = img.copy()
    for ex in exits:
        exid = str(ex.get("id", ""))
        direction = exit_directions.get(exid, "right")
        out = draw_exit_sign(out, int(ex["x"]), int(ex["y"]), direction, scale=scale)
    return out
