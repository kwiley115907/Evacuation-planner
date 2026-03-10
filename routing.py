from __future__ import annotations

from dataclasses import dataclass
from heapq import heappush, heappop
from typing import Dict, List, Optional, Tuple

RC = Tuple[int, int]


def _heur(a: RC, b: RC) -> int:
    # Manhattan distance
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def _neighbors(r: int, c: int):
    # 4-neighborhood
    yield r - 1, c
    yield r + 1, c
    yield r, c - 1
    yield r, c + 1


def astar(grid: List[List[int]], start: RC, goal: RC) -> Optional[List[RC]]:
    """
    A* on a 2D grid.
    grid[r][c] == 1 walkable
    grid[r][c] == 0 blocked
    Returns list of (r,c) from start to goal, or None.
    """
    h = len(grid)
    if h == 0:
        return None
    w = len(grid[0])

    sr, sc = start
    gr, gc = goal

    def inb(rr: int, cc: int) -> bool:
        return 0 <= rr < h and 0 <= cc < w

    if not inb(sr, sc) or not inb(gr, gc):
        return None
    if grid[sr][sc] == 0 or grid[gr][gc] == 0:
        return None

    open_heap = []
    heappush(open_heap, (0 + _heur(start, goal), 0, start))

    came_from: Dict[RC, RC] = {}
    gscore: Dict[RC, int] = {start: 0}
    closed = set()

    while open_heap:
        _, g, cur = heappop(open_heap)
        if cur in closed:
            continue
        if cur == goal:
            # reconstruct
            path = [cur]
            while cur in came_from:
                cur = came_from[cur]
                path.append(cur)
            path.reverse()
            return path

        closed.add(cur)
        r, c = cur

        for rr, cc in _neighbors(r, c):
            if not inb(rr, cc):
                continue
            if grid[rr][cc] == 0:
                continue
            nxt = (rr, cc)
            ng = g + 1
            if nxt in closed:
                continue
            if ng < gscore.get(nxt, 10**18):
                gscore[nxt] = ng
                came_from[nxt] = cur
                f = ng + _heur(nxt, goal)
                heappush(open_heap, (f, ng, nxt))

    return None
