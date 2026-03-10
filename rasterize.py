from __future__ import annotations

from typing import List, Tuple, Dict, Any

from PIL import Image, ImageDraw

# grid is List[List[int]] with 1 walkable, 0 blocked
Grid = List[List[int]]


def rasterize_obstacles(
    image_size: Tuple[int, int],
    obstacles: List[Dict[str, Any]],
    downscale: int = 4,
) -> Tuple[Grid, int]:
    """
    Builds a walkable grid from image_size (W,H) and obstacles.
    Uses a downscaled mask for speed (pure Pillow, no numpy/cv2).
    """
    W, H = image_size
    w = max(1, W // downscale)
    h = max(1, H // downscale)

    # mask: 0 walkable, 1 blocked
    mask = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(mask)

    for ob in obstacles or []:
        t = ob.get("type")
        if t == "rect":
            x1 = int(ob["x1"]) // downscale
            y1 = int(ob["y1"]) // downscale
            x2 = int(ob["x2"]) // downscale
            y2 = int(ob["y2"]) // downscale
            d.rectangle((x1, y1, x2, y2), fill=1)
        elif t == "poly":
            pts = ob.get("points", [])
            pts2 = [(int(x) // downscale, int(y) // downscale) for (x, y) in pts]
            if len(pts2) >= 3:
                d.polygon(pts2, fill=1)

    pix = mask.load()
    grid: Grid = [[1] * w for _ in range(h)]
    for r in range(h):
        for c in range(w):
            if pix[c, r] == 1:
                grid[r][c] = 0
    return grid, downscale


def block_point_disk(grid: Grid, rc: Tuple[int, int], radius: int = 6) -> None:
    """
    Blocks a disk around rc=(r,c) in the GRID coordinates.
    """
    h = len(grid)
    if h == 0:
        return
    w = len(grid[0])

    r0, c0 = rc
    r_min = max(0, r0 - radius)
    r_max = min(h - 1, r0 + radius)
    c_min = max(0, c0 - radius)
    c_max = min(w - 1, c0 + radius)

    r2 = radius * radius
    for r in range(r_min, r_max + 1):
        dr = r - r0
        for c in range(c_min, c_max + 1):
            dc = c - c0
            if dr * dr + dc * dc <= r2:
                grid[r][c] = 0
