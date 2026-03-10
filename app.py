import base64
import io
import json
from datetime import date
from pathlib import Path

import streamlit as st
from PIL import Image, ImageDraw, ImageFont

from evacplan.routing import astar
from evacplan.rasterize import rasterize_obstacles, block_point_disk
from evacplan.export_pdf import export_plan_pdf


st.set_page_config(page_title="Emergency Evacuation Plan", layout="wide")
st.title("Emergency Evacuation Plan Generator")
st.caption("Live crosshair follows finger/mouse (no click). On Termux we can't stream coords into Python, so use the X/Y boxes.")


# ----------------- helpers -----------------

def st_image_bytes(pil_img: Image.Image, caption: str | None = None):
    buf = io.BytesIO()
    pil_img.save(buf, format="PNG")
    st.image(buf.getvalue(), caption=caption, use_container_width=True)


def points_to_text(points) -> str:
    lines = []
    for p in points:
        if p.get("label"):
            lines.append(f'{p["id"]},{p["x"]},{p["y"]},{p["label"]}')
        else:
            lines.append(f'{p["id"]},{p["x"]},{p["y"]}')
    return "\n".join(lines)


def parse_points(text: str):
    out = []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 3:
            continue
        pid = parts[0]
        try:
            x = int(float(parts[1]))
            y = int(float(parts[2]))
        except Exception:
            continue
        label = parts[3] if len(parts) >= 4 else ""
        out.append({"id": pid, "x": x, "y": y, "label": label})
    return out


def parse_obstacles(text: str):
    obs = []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("rect"):
            parts = [p.strip() for p in line.split(",")]
            if len(parts) != 5:
                continue
            try:
                x1, y1, x2, y2 = map(lambda v: int(float(v)), parts[1:])
            except Exception:
                continue
            obs.append({
                "type": "rect",
                "x1": min(x1, x2), "y1": min(y1, y2),
                "x2": max(x1, x2), "y2": max(y1, y2),
            })
        elif line.startswith("poly"):
            parts = line.split(",", 1)
            if len(parts) != 2:
                continue
            pts = []
            for pair in parts[1].split(";"):
                pair = pair.strip()
                if not pair:
                    continue
                xy = [p.strip() for p in pair.split(",")]
                if len(xy) != 2:
                    continue
                try:
                    x = int(float(xy[0]))
                    y = int(float(xy[1]))
                except Exception:
                    continue
                pts.append((x, y))
            if len(pts) >= 3:
                obs.append({"type": "poly", "points": pts})
    return obs


# ----------------- drawing -----------------

def draw_path(img_pil: Image.Image, path_rc, downscale: int, thickness: int = 4):
    if not path_rc or len(path_rc) < 2:
        return img_pil
    out = img_pil.copy()
    d = ImageDraw.Draw(out)
    pts = [(int(c * downscale), int(r * downscale)) for (r, c) in path_rc]
    d.line(pts, fill=(0, 0, 0), width=thickness + 2)
    d.line(pts, fill=(255, 0, 0), width=thickness)
    return out


def draw_points_and_icons(img: Image.Image, starts, exits, elevators, assembly_areas, extinguishers):
    out = img.copy()
    d = ImageDraw.Draw(out)
    try:
        font = ImageFont.load_default()
    except Exception:
        font = None

    def label_text(x, y, text):
        if not text:
            return
        d.text((x + 13, y - 11), text, fill=(255, 255, 255), font=font)
        d.text((x + 12, y - 12), text, fill=(0, 0, 0), font=font)

    def dot(x, y, color, text):
        r = 10
        d.ellipse((x - r, y - r, x + r, y + r), fill=color, outline=(0, 0, 0))
        label_text(x, y, text)

    for s in starts or []:
        dot(int(s["x"]), int(s["y"]), (255, 255, 0), s["id"])       # start yellow
    for e in exits or []:
        dot(int(e["x"]), int(e["y"]), (0, 255, 0), e["id"])         # exit green
    for el in elevators or []:
        dot(int(el["x"]), int(el["y"]), (255, 165, 0), el["id"])    # elevator orange

    for a in assembly_areas or []:
        x, y = int(a["x"]), int(a["y"])
        r = 14
        d.ellipse((x - r, y - r, x + r, y + r), outline=(0, 0, 0), width=3)
        d.ellipse((x - r + 3, y - r + 3, x + r - 3, y + r - 3), outline=(0, 160, 0), width=3)
        d.text((x - 4, y - 8), "A", fill=(0, 160, 0), font=font)
        label_text(x, y, a["id"])

    for fe in extinguishers or []:
        x, y = int(fe["x"]), int(fe["y"])
        w, h = 22, 16
        d.rectangle((x - w // 2, y - h // 2, x + w // 2, y + h // 2),
                    fill=(220, 0, 0), outline=(0, 0, 0), width=2)
        d.text((x - w // 2 + 3, y - h // 2 - 1), "FE", fill=(255, 255, 255), font=font)
        label_text(x, y, fe["id"])

    return out


def add_zoom_callout(
    img: Image.Image,
    *,
    target_xy: tuple[int, int],
    line_from_xy: tuple[int, int] | None = None,
    label: str = "",
    crop_radius: int = 90,
    inset_size: int = 240,
    margin: int = 18,
    side: str = "right",
    leader_color: str = "black",
    fe_scale: float = 2.2,
):
    base = img.copy().convert("RGB")
    W, H = base.size
    x, y = target_xy

    extra_w = inset_size + margin * 2
    new_W = W + extra_w
    new_img = Image.new("RGB", (new_W, H), (255, 255, 255))

    if side == "right":
        base_x = 0
        inset_x = W + margin
    else:
        base_x = extra_w
        inset_x = margin

    new_img.paste(base, (base_x, 0))

    x0 = max(0, x - crop_radius)
    y0 = max(0, y - crop_radius)
    x1 = min(W, x + crop_radius)
    y1 = min(H, y + crop_radius)

    crop = base.crop((x0, y0, x1, y1)).resize((inset_size, inset_size), resample=Image.NEAREST)

    inset_y = margin
    new_img.paste(crop, (inset_x, inset_y))

    d = ImageDraw.Draw(new_img)
    try:
        font = ImageFont.load_default()
    except Exception:
        font = None

    d.rectangle((inset_x, inset_y, inset_x + inset_size, inset_y + inset_size),
                outline=(0, 0, 0), width=3)

    cw = max(1, (x1 - x0))
    ch = max(1, (y1 - y0))
    rel_x = (x - x0) / cw
    rel_y = (y - y0) / ch
    cx = inset_x + int(rel_x * inset_size)
    cy = inset_y + int(rel_y * inset_size)

    # black crosshair
    d.line((cx - 12, cy, cx + 12, cy), fill=(0, 0, 0), width=3)
    d.line((cx, cy - 12, cx, cy + 12), fill=(0, 0, 0), width=3)

    # big FE inside inset
    w = int(22 * fe_scale)
    h = int(16 * fe_scale)
    xL, yT = cx - w // 2, cy - h // 2
    xR, yB = cx + w // 2, cy + h // 2
    d.rectangle((xL - 2, yT - 2, xR + 2, yB + 2), outline=(0, 0, 0), width=3)
    d.rectangle((xL, yT, xR, yB), fill=(220, 0, 0), outline=(0, 0, 0), width=2)
    d.text((xL + int(0.18 * w), yT + int(0.05 * h)), "FE", fill=(255, 255, 255), font=font)

    inset_pt = (inset_x, cy) if side == "right" else (inset_x + inset_size, cy)
    base_pt = (base_x + x, y) if line_from_xy is None else (base_x + int(line_from_xy[0]), int(line_from_xy[1]))

    if leader_color == "black":
        d.line((base_pt, inset_pt), fill=(0, 0, 0), width=5)
    else:
        d.line((base_pt, inset_pt), fill=(0, 0, 0), width=5)
        d.line((base_pt, inset_pt), fill=(255, 0, 0), width=3)

    if label:
        d.text((inset_x, inset_y + inset_size + 6), label, fill=(0, 0, 0), font=font)

    return new_img


def add_print_layout_right_legend(base_img: Image.Image, *, building_name: str, floor_name: str, footer_text: str):
    base = base_img.convert("RGB")
    W, H = base.size

    panel_w = 360
    bottom_h = 260

    new_W = W + panel_w
    new_H = H + bottom_h

    img = Image.new("RGB", (new_W, new_H), (255, 255, 255))
    img.paste(base, (0, 0))

    d = ImageDraw.Draw(img)
    try:
        font = ImageFont.load_default()
    except Exception:
        font = None

    # right panel
    d.rectangle((W, 0, new_W, H), fill=(255, 255, 255), outline=(0, 0, 0), width=2)

    # legend centered vertically
    legend_w = panel_w - 26
    legend_h = 320
    legend_x0 = W + 13
    legend_y0 = max(10, (H - legend_h) // 2)

    d.rectangle((legend_x0, legend_y0, legend_x0 + legend_w, legend_y0 + legend_h),
                fill=(255, 255, 255), outline=(0, 0, 0), width=2)

    header_h = 40
    d.rectangle((legend_x0, legend_y0, legend_x0 + legend_w, legend_y0 + header_h),
                fill=(242, 242, 242), outline=(0, 0, 0), width=2)
    d.text((legend_x0 + 10, legend_y0 + 10), "LEGEND", fill=(0, 0, 0), font=font)
    d.text((legend_x0 + 10, legend_y0 + 24), f"{building_name} — {floor_name}", fill=(0, 0, 0), font=font)

    y = legend_y0 + header_h + 14

    def legend_dot(label, color):
        nonlocal y
        cx, cy = legend_x0 + 18, y + 7
        r = 7
        d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=color, outline=(0, 0, 0))
        d.text((legend_x0 + 40, y), label, fill=(0, 0, 0), font=font)
        y += 24

    def legend_line(label, color):
        nonlocal y
        d.line((legend_x0 + 12, y + 8, legend_x0 + 44, y + 8), fill=color, width=3)
        d.text((legend_x0 + 50, y), label, fill=(0, 0, 0), font=font)
        y += 24

    legend_dot("You Are Here", (255, 255, 0))
    legend_dot("Exit", (0, 255, 0))
    legend_dot("Elevator (Avoid)", (255, 165, 0))
    legend_line("Evacuation Route", (255, 0, 0))

    # Assembly
    d.ellipse((legend_x0 + 11, y + 2, legend_x0 + 27, y + 18), outline=(0, 0, 0), width=2)
    d.ellipse((legend_x0 + 13, y + 4, legend_x0 + 25, y + 16), outline=(0, 160, 0), width=2)
    d.text((legend_x0 + 17, y + 3), "A", fill=(0, 160, 0), font=font)
    d.text((legend_x0 + 50, y), "Assembly Area", fill=(0, 0, 0), font=font)
    y += 24

    # FE
    d.rectangle((legend_x0 + 10, y + 4, legend_x0 + 36, y + 18),
                fill=(220, 0, 0), outline=(0, 0, 0), width=2)
    d.text((legend_x0 + 14, y + 4), "FE", fill=(255, 255, 255), font=font)
    d.text((legend_x0 + 50, y), "Fire Extinguisher", fill=(0, 0, 0), font=font)

    # bottom strip notes
    d.rectangle((0, H, new_W, new_H), fill=(255, 255, 255), outline=(0, 0, 0), width=2)

    notes_x0, notes_y0 = 14, H + 14
    notes_x1, notes_y1 = new_W - 14, new_H - 40
    d.rectangle((notes_x0, notes_y0, notes_x1, notes_y1), outline=(0, 0, 0), width=2)
    d.text((notes_x0 + 12, notes_y0 + 10), "EMERGENCY NOTES", fill=(0, 0, 0), font=font)

    y2 = notes_y0 + 34
    gap = 18

    for line in [
        "• In case of an emergency, call 911.",
        "• Proceed to the designated waiting point and wait for instructions.",
    ]:
        d.text((notes_x0 + 12, y2), line, fill=(0, 0, 0), font=font)
        y2 += gap

    def underline(x, y, w):
        d.line((x, y, x + w, y), fill=(0, 0, 0), width=2)

    t = "• DO NOT USE THE ELEVATOR"
    d.text((notes_x0 + 12, y2), t, fill=(0, 0, 0), font=font)
    underline(notes_x0 + 12, y2 + 12, 225)
    y2 += int(gap * 1.4)

    for line in [
        "• En caso de emergencia, llame al 911.",
        "• Diríjase al punto de reunión designado y espere instrucciones.",
    ]:
        d.text((notes_x0 + 12, y2), line, fill=(0, 0, 0), font=font)
        y2 += gap

    t = "• NO USE EL ASCENSOR"
    d.text((notes_x0 + 12, y2), t, fill=(0, 0, 0), font=font)
    underline(notes_x0 + 12, y2 + 12, 170)

    # footer
    d.text((14, new_H - 26), footer_text, fill=(60, 60, 60), font=font)

    return img


# ----------------- LIVE crosshair (HTML only, Termux-safe) -----------------

def live_crosshair_overlay_html(pil_img: Image.Image, height_px: int = 650):
    """
    True live crosshair overlay in browser WITHOUT clicking.
    Termux-safe: does not require custom components or pyarrow.
    Shows live x/y in the HUD (read them and enter into X/Y boxes).
    """
    buf = io.BytesIO()
    pil_img.save(buf, format="PNG")
    data = base64.b64encode(buf.getvalue()).decode("ascii")
    data_url = f"data:image/png;base64,{data}"

    html = f"""
    <style>
      .wrap {{
        position: relative;
        width: 100%;
        height: {height_px}px;
        border: 1px solid rgba(0,0,0,0.15);
        border-radius: 10px;
        overflow: hidden;
        background: #fff;
        touch-action: none;
      }}
      .bg {{
        position: absolute;
        inset: 0;
        width: 100%;
        height: 100%;
        object-fit: contain;
        user-select: none;
        -webkit-user-drag: none;
        pointer-events: none;
      }}
      .overlay {{
        position: absolute;
        inset: 0;
        width: 100%;
        height: 100%;
      }}
      .hud {{
        position: absolute;
        left: 10px;
        top: 10px;
        padding: 6px 8px;
        font: 12px/1.2 sans-serif;
        background: rgba(255,255,255,0.85);
        border: 1px solid rgba(0,0,0,0.2);
        border-radius: 8px;
      }}
    </style>
    <div class="wrap" id="wrap">
      <img class="bg" id="bg" src="{data_url}" />
      <svg class="overlay" id="svg" viewBox="0 0 1000 1000" preserveAspectRatio="none">
        <line id="hline" x1="0" y1="500" x2="1000" y2="500" stroke="#000" stroke-width="2"></line>
        <line id="vline" x1="500" y1="0" x2="500" y2="1000" stroke="#000" stroke-width="2"></line>
        <circle id="ring" cx="500" cy="500" r="10" fill="none" stroke="#000" stroke-width="2"></circle>
      </svg>
      <div class="hud" id="hud">x: -- &nbsp; y: --</div>
    </div>
    <script>
      const wrap = document.getElementById("wrap");
      const bg = document.getElementById("bg");
      const hline = document.getElementById("hline");
      const vline = document.getElementById("vline");
      const ring = document.getElementById("ring");
      const hud = document.getElementById("hud");

      function clamp(v, lo, hi) {{ return Math.max(lo, Math.min(hi, v)); }}

      function update(clientX, clientY) {{
        const rect = wrap.getBoundingClientRect();
        const nx = (clientX - rect.left) / rect.width;
        const ny = (clientY - rect.top) / rect.height;

        const sx = clamp(nx, 0, 1) * 1000;
        const sy = clamp(ny, 0, 1) * 1000;

        hline.setAttribute("y1", sy); hline.setAttribute("y2", sy);
        vline.setAttribute("x1", sx); vline.setAttribute("x2", sx);
        ring.setAttribute("cx", sx); ring.setAttribute("cy", sy);

        const imgW = bg.naturalWidth || 1;
        const imgH = bg.naturalHeight || 1;

        const wrapW = rect.width, wrapH = rect.height;
        const imgAspect = imgW / imgH;
        const wrapAspect = wrapW / wrapH;

        let drawW, drawH, offX, offY;
        if (imgAspect > wrapAspect) {{
          drawW = wrapW; drawH = wrapW / imgAspect; offX = 0; offY = (wrapH - drawH) / 2;
        }} else {{
          drawH = wrapH; drawW = wrapH * imgAspect; offX = (wrapW - drawW) / 2; offY = 0;
        }}

        const px = (clientX - rect.left - offX) / drawW;
        const py = (clientY - rect.top - offY) / drawH;

        let ix = Math.round(clamp(px, 0, 1) * (imgW - 1));
        let iy = Math.round(clamp(py, 0, 1) * (imgH - 1));

        hud.innerHTML = `x: <b>${{ix}}</b> &nbsp; y: <b>${{iy}}</b>`;
      }}

      wrap.addEventListener("pointermove", (e) => update(e.clientX, e.clientY));
      wrap.addEventListener("touchmove", (e) => {{
        if (e.touches && e.touches.length > 0) {{
          e.preventDefault();
          update(e.touches[0].clientX, e.touches[0].clientY);
        }}
      }}, {{ passive: false }});
    </script>
    """
    st.components.v1.html(html, height=height_px + 10, scrolling=False)


# ----------------- App state -----------------

def ensure_state():
    st.session_state.setdefault("starts", [])
    st.session_state.setdefault("exits", [])
    st.session_state.setdefault("elevators", [])
    st.session_state.setdefault("assembly", [])
    st.session_state.setdefault("extinguishers", [])
    st.session_state.setdefault("obstacles_text", "rect,150,150,260,240")

ensure_state()


# ----------------- UI -----------------

output_dir = Path(__file__).resolve().parent / "output"
output_dir.mkdir(parents=True, exist_ok=True)

uploaded = st.file_uploader("Upload a floor plan image (PNG/JPG)", type=["png", "jpg", "jpeg"])
if not uploaded:
    st.stop()

img = Image.open(io.BytesIO(uploaded.read())).convert("RGB")
W, H = img.size

with st.sidebar:
    st.header("Project")
    building_name = st.text_input("Building name", value="Villa Del Sol")
    floor_name = st.text_input("Floor name", value="F1")
    avoid_elevators = st.checkbox("Avoid elevators (recommended)", value=True)
    downscale = st.slider("Routing resolution (downscale)", 2, 10, 4)

    st.divider()
    st.header("Add points (Termux-safe)")
    st.caption("Move crosshair, read x/y in HUD, enter here, then press Add.")

    x_in = st.number_input("X (pixel)", min_value=0, max_value=W-1, value=0)
    y_in = st.number_input("Y (pixel)", min_value=0, max_value=H-1, value=0)

    start_id = st.text_input("Next Start ID", value=f"R{len(st.session_state.starts)+1:03d}")
    exit_id = st.text_input("Next Exit ID", value=f"E{len(st.session_state.exits)+1}")
    elev_id = st.text_input("Next Elevator ID", value=f"L{len(st.session_state.elevators)+1}")
    asm_id = st.text_input("Next Assembly ID", value=f"A{len(st.session_state.assembly)+1}")
    fe_id = st.text_input("Next Extinguisher ID", value=f"FE{len(st.session_state.extinguishers)+1}")

    start_label = st.text_input("Start label (optional)", value="")
    fe_label = st.text_input("Extinguisher label (optional)", value="Fire Extinguisher")

    c1, c2 = st.columns(2)
    with c1:
        if st.button("Add START"):
            st.session_state.starts.append({"id": start_id, "x": int(x_in), "y": int(y_in), "label": start_label})
    with c2:
        if st.button("Add EXIT"):
            st.session_state.exits.append({"id": exit_id, "x": int(x_in), "y": int(y_in), "label": ""})

    c3, c4 = st.columns(2)
    with c3:
        if st.button("Add ELEVATOR"):
            st.session_state.elevators.append({"id": elev_id, "x": int(x_in), "y": int(y_in), "label": ""})
    with c4:
        if st.button("Add ASSEMBLY"):
            st.session_state.assembly.append({"id": asm_id, "x": int(x_in), "y": int(y_in), "label": ""})

    if st.button("Add FIRE EXTINGUISHER"):
        st.session_state.extinguishers.append({"id": fe_id, "x": int(x_in), "y": int(y_in), "label": fe_label})

    if st.button("Clear ALL points"):
        st.session_state.starts = []
        st.session_state.exits = []
        st.session_state.elevators = []
        st.session_state.assembly = []
        st.session_state.extinguishers = []

    st.divider()
    st.header("Text areas (auto-filled)")
    starts_text = st.text_area("Starts", value=points_to_text(st.session_state.starts), height=120)
    exits_text = st.text_area("Exits", value=points_to_text(st.session_state.exits), height=120)
    elevators_text = st.text_area("Elevators", value=points_to_text(st.session_state.elevators), height=100)
    assembly_text = st.text_area("Assembly", value=points_to_text(st.session_state.assembly), height=100)
    extinguishers_text = st.text_area("Extinguishers", value=points_to_text(st.session_state.extinguishers), height=100)

    st.caption("Obstacles (optional): rect,x1,y1,x2,y2 OR poly,x1,y1;x2,y2;...")
    obstacles_text = st.text_area("Obstacles", value=st.session_state.obstacles_text, height=120)
    st.session_state.obstacles_text = obstacles_text

    st.divider()
    show_callout = st.checkbox("Magnify first extinguisher (black callout)", value=True)
    callout_side = st.selectbox("Callout side", ["right", "left"], index=0)
    leader_color = st.selectbox("Callout leader line", ["black", "red"], index=0)
    fe_scale = st.slider("Magnifier FE icon size", 1.0, 4.0, 2.2, 0.1)

    bake_layout = st.checkbox("Bake legend+notes into PNG/PDF", value=True)


starts = parse_points(starts_text)
exits = parse_points(exits_text)
elevators = parse_points(elevators_text)
assembly_areas = parse_points(assembly_text)
extinguishers = parse_points(extinguishers_text)
obstacles = parse_obstacles(obstacles_text)

footer = f"© {date.today().year} {building_name} — By: Kevin A. Wiley"

left, right = st.columns([1.35, 1])

with left:
    st.subheader("Live Crosshair Preview (no click)")
    live_crosshair_overlay_html(img, height_px=650)

with right:
    st.subheader("Preview / Generate")

    preview = draw_points_and_icons(img, starts, exits, elevators, assembly_areas, extinguishers)

    if show_callout and extinguishers:
        fe0 = extinguishers[0]
        preview = add_zoom_callout(
            preview,
            target_xy=(int(fe0["x"]), int(fe0["y"])),
            line_from_xy=(int(x_in), int(y_in)),  # leader line start = your typed x/y
            label=f"Zoom: {fe0['id']} (Fire Extinguisher)",
            side=callout_side,
            leader_color=leader_color,
            fe_scale=fe_scale,
        )

    if bake_layout:
        preview = add_print_layout_right_legend(
            preview,
            building_name=building_name,
            floor_name=floor_name,
            footer_text=footer,
        )

    st_image_bytes(preview, caption="Preview output (PNG/PDF will match)")

    if st.button("Compute nearest exit routes"):
        if not starts or not exits:
            st.error("Add at least one Start and one Exit.")
        else:
            grid, ds = rasterize_obstacles((W, H), obstacles, downscale=downscale)

            if avoid_elevators and elevators:
                for e in elevators:
                    rr, cc = int(e["y"]) // ds, int(e["x"]) // ds
                    block_point_disk(grid, (rr, cc), radius=6)

            out = img.copy()

            for s in starts:
                sr, sc = int(s["y"]) // ds, int(s["x"]) // ds
                best_path = None
                best_len = None
                for ex in exits:
                    gr, gc = int(ex["y"]) // ds, int(ex["x"]) // ds
                    path = astar(grid, (sr, sc), (gr, gc))
                    if path is None:
                        continue
                    if best_len is None or len(path) < best_len:
                        best_len = len(path)
                        best_path = path
                if best_path:
                    out = draw_path(out, best_path, ds, thickness=4)

            out = draw_points_and_icons(out, starts, exits, elevators, assembly_areas, extinguishers)

            if show_callout and extinguishers:
                fe0 = extinguishers[0]
                out = add_zoom_callout(
                    out,
                    target_xy=(int(fe0["x"]), int(fe0["y"])),
                    line_from_xy=(int(x_in), int(y_in)),
                    label=f"Zoom: {fe0['id']} (Fire Extinguisher)",
                    side=callout_side,
                    leader_color=leader_color,
                    fe_scale=fe_scale,
                )

            if bake_layout:
                out = add_print_layout_right_legend(
                    out,
                    building_name=building_name,
                    floor_name=floor_name,
                    footer_text=footer,
                )

            st_image_bytes(out, caption="Final output")

            overlay_png = output_dir / "evac_routes.png"
            out.save(overlay_png)

            buf = io.BytesIO()
            out.save(buf, format="PNG")
            st.download_button("Download PNG", data=buf.getvalue(), file_name="evac_routes.png", mime="image/png")

            pdf_path = output_dir / "evac_plan.pdf"
            export_plan_pdf(str(pdf_path), str(overlay_png), title="Emergency Evacuation Plan", footer_text=footer)

            with open(pdf_path, "rb") as f:
                st.download_button("Download PDF", data=f, file_name="evac_plan.pdf", mime="application/pdf")


st.subheader("Project JSON (copy/save)")
project = {
    "building_name": building_name,
    "floor_name": floor_name,
    "features": {
        "exits": exits,
        "elevators": elevators,
        "assembly_areas": assembly_areas,
        "fire_extinguishers": extinguishers,
        "stairs": [],
    },
    "starts": starts,
    "obstacles": obstacles,
}
st.code(json.dumps(project, indent=2))
