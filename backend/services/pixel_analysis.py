"""
Pixel-level color analysis for the Z-Index (disclosing-dye plaque scoring).

Unlike the LLM path (which *estimates* color coverage), this classifies every
tooth-surface pixel into white / purple / blue / light-blue by HSV thresholds
and counts them, giving a deterministic, reproducible area percentage.

The hard part is separating teeth from gums/lips/background. We exploit the fact
that the disclosing dye is purple/blue/cyan (hue ~165-315°) while gums and lips
are red/pink (hue ~315-360° / 0-25°) and the mouth interior is dark (low value).

All thresholds are module constants — tune them against real photos using the
debug overlay returned by ``analyze_teeth_pixels(..., debug=True)``.
"""

import base64
import io
import logging
from typing import Optional

import numpy as np
from PIL import Image, ImageDraw, ImageOps

logger = logging.getLogger(__name__)

# --- Tunable thresholds (PIL HSV space: H, S, V each 0-255) -----------------
# Hue is stored 0-255 for 0-360°, so degrees * 255/360.
_DEG = 255.0 / 360.0

DARK_V_MAX = 45        # below this Value = mouth interior / shadow / background
WHITE_S_MAX = 55       # saturation below this (and bright) = clean white enamel
WHITE_V_MIN = 110      # value above this (and low sat) = clean white enamel
DYE_S_MIN = 45         # min saturation for a pixel to count as colored dye

# Hue band edges in degrees (converted to PIL scale below).
# In real 2-tone dye photos "голубой" (light blue) and "синий" (blue) share the
# same hue — they differ by BRIGHTNESS, not hue. So we take one blue hue band
# and split it by Value: bright => light_blue (old plaque), dark => blue (medium).
BLUE_HUE_LO, BLUE_HUE_HI = 165, 255   # whole blue family (light + dark)
LIGHT_BLUE_V_MIN = 220                # only very light/pale blue => light_blue/голубой (old)
H_PURPLE_LO, H_PURPLE_HI = 255, 335   # purple / violet / magenta (freshest plaque)
# Widened 315->335 to reclaim cervical (gum-line) plaque that reads magenta and
# was being classified as gum. Going higher (>345) starts eating dye-stained gum
# tissue — the disclosing dye colours plaque and gums alike, so cervical plaque
# can't be fully separated from stained gingiva by hue alone.
# Everything else with high saturation (red/pink gums, orange skin) = non-tooth.

# Pixel labels
L_DARK, L_WHITE, L_PURPLE, L_BLUE, L_CYAN, L_GUM, L_OTHER = 0, 1, 2, 3, 4, 5, 6

_OVERLAY_COLORS = {
    L_DARK: (0, 0, 0),
    L_WHITE: (235, 235, 235),
    L_PURPLE: (170, 0, 200),
    L_BLUE: (0, 80, 255),
    L_CYAN: (0, 220, 220),
    L_GUM: (200, 40, 40),
    L_OTHER: (90, 90, 90),
}

MAX_SIDE = 900  # downscale large photos for speed (area % is scale-invariant)

# FDI tooth ids in viewer left -> right order for a non-mirrored frontal photo.
# Upper arch = patient's right canine (1.3) .. left canine (2.3); lower likewise.
UPPER_TOOTH_IDS = ["1.3", "1.2", "1.1", "2.1", "2.2", "2.3"]
LOWER_TOOTH_IDS = ["4.3", "4.2", "4.1", "3.1", "3.2", "3.3"]
TOOTH_IDS = UPPER_TOOTH_IDS + LOWER_TOOTH_IDS
QUADRANT_TEETH = {
    "1": ("1.1", "1.2", "1.3"),
    "2": ("2.1", "2.2", "2.3"),
    "3": ("3.1", "3.2", "3.3"),
    "4": ("4.1", "4.2", "4.3"),
}

# A tooth box where less than this share of pixels is tooth surface is a
# misplaced box (it landed on gum, lips or the dark mouth gap) — treat the
# tooth as unreadable rather than scoring a few stray pixels.
MIN_BOX_TOOTH_SHARE = 0.15

_BOX_YELLOW = (255, 215, 0)
_BOX_RED = (230, 30, 30)


def _decode_image(image_data_uri: str) -> Image.Image:
    if "," in image_data_uri:
        image_data_uri = image_data_uri.split(",", 1)[1]
    raw = base64.b64decode(image_data_uri)
    img = Image.open(io.BytesIO(raw))
    # Phone photos often store rotation in EXIF; the browser applies it when
    # showing the photo, so apply it here too or the analysis (and the tooth
    # boxes drawn over the photo) would see the mouth sideways.
    img = ImageOps.exif_transpose(img)
    if img.mode != "RGB":
        img = img.convert("RGB")
    w, h = img.size
    scale = MAX_SIDE / max(w, h)
    if scale < 1.0:
        img = img.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.BILINEAR)
    return img


def _classify(hsv: np.ndarray) -> np.ndarray:
    """Return an (H, W) int array of pixel labels."""
    H = hsv[..., 0].astype(np.int16)
    S = hsv[..., 1].astype(np.int16)
    V = hsv[..., 2].astype(np.int16)

    labels = np.full(H.shape, L_OTHER, dtype=np.uint8)

    dark = V < DARK_V_MAX
    white = (~dark) & (S < WHITE_S_MAX) & (V >= WHITE_V_MIN)
    colored = (~dark) & (~white) & (S >= DYE_S_MIN)

    def band(lo_deg, hi_deg):
        return colored & (H >= lo_deg * _DEG) & (H < hi_deg * _DEG)

    blue_family = band(BLUE_HUE_LO, BLUE_HUE_HI)
    cyan = blue_family & (V >= LIGHT_BLUE_V_MIN)   # bright blue = light_blue (old)
    blue = blue_family & ~cyan                     # darker blue = medium
    purple = band(H_PURPLE_LO, H_PURPLE_HI)
    # Colored but outside the dye hue bands = gums/lips/tongue (red/pink/orange).
    gum = colored & ~(blue_family | purple)

    labels[dark] = L_DARK
    labels[white] = L_WHITE
    labels[cyan] = L_CYAN
    labels[blue] = L_BLUE
    labels[purple] = L_PURPLE
    labels[gum] = L_GUM
    return labels


def _tooth_centers(profile: np.ndarray, min_dist: int) -> list:
    """Local maxima of the density profile (tooth centres), thinned so no two
    are closer than ``min_dist`` (keeping the taller one)."""
    n = len(profile)
    cand = [i for i in range(1, n - 1) if profile[i] >= profile[i - 1] and profile[i] > profile[i + 1]]
    cand.sort(key=lambda i: -profile[i])
    kept: list = []
    for p in cand:
        if all(abs(p - q) >= min_dist for q in kept):
            kept.append(p)
    return sorted(kept)


def _valley(profile: np.ndarray, a: int, b: int) -> int:
    """Column of minimum density (the interdental gap) in [a, b)."""
    a = max(a, 0)
    b = min(b, len(profile))
    if b <= a + 1:
        return (a + b) // 2
    return a + int(np.argmin(profile[a:b]))


def _arch_edges(col_counts: np.ndarray, x0: int, x1: int, n: int = 6) -> list:
    """Return n+1 column edges bounding the n CENTRAL anterior teeth.

    Detects tooth centres, keeps the n straddling the arch midline (so extra
    side teeth beyond the canines are excluded), and places boundaries at the
    interdental gaps — including the canine↔premolar gap as the outer edges.
    Falls back to even spacing if centres can't be found.
    """
    w = x1 - x0
    even = list(np.linspace(x0, x1, n + 1).astype(int))
    if w <= n:
        return even
    k = max(3, w // 50)
    sm = np.convolve(col_counts.astype(float), np.ones(k) / k, mode="same")
    centers = [c for c in _tooth_centers(sm, min_dist=max(6, w // 12)) if x0 <= c <= x1]
    if len(centers) < n:
        return even
    xc = x0 + int(np.average(np.arange(w), weights=(col_counts[x0:x1] + 1e-9)))
    half = n // 2
    left = sorted(c for c in centers if c < xc)
    right = sorted(c for c in centers if c >= xc)
    sel = (left[-half:] if len(left) >= half else left) + (right[:half] if len(right) >= half else right)
    sel = sorted(sel)
    if len(sel) < n:
        return even
    sel = sel[:n]
    # Anterior region = from the canine↔premolar gap on each side (this drops
    # the extra side teeth). Divide it into n even columns — real anterior
    # teeth are close to even width, and even cuts are far more stable than
    # snapping to the shallow gaps between touching anterior teeth.
    prev = [c for c in centers if c < sel[0]]
    nxt = [c for c in centers if c > sel[-1]]
    xa = _valley(sm, max(prev), sel[0]) if prev else x0
    xb = _valley(sm, sel[-1], min(nxt)) if nxt else x1
    return list(np.linspace(xa, xb, n + 1).astype(int))


def _per_tooth(labels: np.ndarray) -> dict:
    """Split the tooth region into 12 cells (2 arches x 6 teeth) and compute
    per-tooth colour percentages + plaque index from the same pixel labels.

    The two arches are separated at the row with the fewest tooth pixels (the
    mouth gap / occlusal line); within each arch the column cuts snap to the
    interdental gaps (see ``_split_columns``) rather than using equal widths.
    """
    H, W = labels.shape
    white = labels == L_WHITE
    purple = labels == L_PURPLE
    blue = labels == L_BLUE
    cyan = labels == L_CYAN
    tooth = white | purple | blue | cyan
    tooth_total = int(tooth.sum())

    row_counts = tooth.sum(axis=1)
    lo, hi = int(0.28 * H), int(0.72 * H)
    split = (lo + int(np.argmin(row_counts[lo:hi]))) if hi > lo else H // 2

    teeth: dict = {}
    min_cell = max(200, int(tooth_total * 0.008))

    def fill_arch(row0: int, row1: int, ids: list):
        sub = tooth[row0:row1]
        col_counts = sub.sum(axis=0)
        xs = np.where(col_counts > 0)[0]
        if xs.size == 0:
            for tid in ids:
                teeth[tid] = {"missing": True, "white": 0, "purple": 0, "blue": 0,
                              "light_blue": 0, "pollution_percentage": 0}
            return
        edges = _arch_edges(col_counts, int(xs.min()), int(xs.max()) + 1, len(ids))
        for i, tid in enumerate(ids):
            cx0, cx1 = edges[i], edges[i + 1]
            cell = np.zeros_like(tooth)
            cell[row0:row1, cx0:cx1] = True
            w = int((white & cell).sum())
            p = int((purple & cell).sum())
            b = int((blue & cell).sum())
            c = int((cyan & cell).sum())
            tot = w + p + b + c
            teeth[tid] = _missing_tooth() if tot < min_cell else _tooth_stats(w, p, b, c)

    fill_arch(0, split, UPPER_TOOTH_IDS)
    fill_arch(split, H, LOWER_TOOTH_IDS)
    return teeth


def _missing_tooth() -> dict:
    return {"missing": True, "white": 0, "purple": 0, "blue": 0,
            "light_blue": 0, "pollution_percentage": 0}


def _tooth_stats(w: int, p: int, b: int, c: int) -> dict:
    """Colour shares + plaque index from white/purple/blue/light-blue pixel counts."""
    tot = w + p + b + c
    pw = round(100 * w / tot)
    pp = round(100 * p / tot)
    pb = round(100 * b / tot)
    pc = max(0, 100 - pw - pp - pb)
    # Severity-weighted plaque index for this tooth (same as overall).
    # Integer weights: purple(fresh)=4, blue(medium)=5, light_blue(old)=6,
    # over max 600 — fresh plaque counts strongly so the index reflects
    # actual coverage, not just plaque age.
    pollution = round((pp * 4 + pb * 5 + pc * 6) / 6)
    return {"missing": False, "white": pw, "purple": pp, "blue": pb,
            "light_blue": pc, "pollution_percentage": min(pollution, 100)}


def _overlay_b64(labels: np.ndarray) -> str:
    out = np.zeros((*labels.shape, 3), dtype=np.uint8)
    for lbl, color in _OVERLAY_COLORS.items():
        out[labels == lbl] = color
    buf = io.BytesIO()
    Image.fromarray(out, "RGB").save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def analyze_teeth_pixels(image_data_uri: str, debug: bool = True) -> dict:
    """Classify tooth-surface pixels and return overall color percentages.

    Percentages are over *tooth* pixels only (white + purple + blue + cyan);
    gums/lips/background are excluded from the denominator.
    """
    img = _decode_image(image_data_uri)
    hsv = np.asarray(img.convert("HSV"))
    labels = _classify(hsv)

    counts = {
        "white": int(np.count_nonzero(labels == L_WHITE)),
        "purple": int(np.count_nonzero(labels == L_PURPLE)),
        "blue": int(np.count_nonzero(labels == L_BLUE)),
        "light_blue": int(np.count_nonzero(labels == L_CYAN)),
        "gum_excluded": int(np.count_nonzero(labels == L_GUM)),
        "dark_excluded": int(np.count_nonzero(labels == L_DARK)),
        "other_excluded": int(np.count_nonzero(labels == L_OTHER)),
    }
    tooth = counts["white"] + counts["purple"] + counts["blue"] + counts["light_blue"]
    total = int(labels.size)

    def pct(n: int) -> int:
        return round(100 * n / tooth) if tooth else 0

    color_pct = {
        "white": pct(counts["white"]),
        "purple": pct(counts["purple"]),
        "blue": pct(counts["blue"]),
        "light_blue": pct(counts["light_blue"]),
    }
    # Raw stained area (any dye colour). NOT the Z-Index — the index weights
    # colours by plaque age (see compute_z_index). Kept only as a coverage stat.
    stained_area = color_pct["purple"] + color_pct["blue"] + color_pct["light_blue"]

    result = {
        "method": "pixel_hsv_v1",
        "tooth_pixels": tooth,
        "total_pixels": total,
        "tooth_coverage_percent": round(100 * tooth / total) if total else 0,
        "counts": counts,
        "overall_color_percentages": color_pct,
        "stained_area_percent": stained_area,
        "teeth": _per_tooth(labels),
    }
    if debug:
        result["debug_image"] = _overlay_b64(labels)
    return result


# --- Per-tooth analysis inside AI-placed frames ------------------------------
#
# The vision model first draws a yellow frame around each of the 12 anterior
# teeth (and a red frame around each quadrant). Only pixels inside the yellow
# frames are classified and counted, tooth by tooth, so white walls, cheek
# retractors, lip highlights and side teeth outside the frames can no longer
# pass for clean enamel and dilute the index.
#
# Teeth are often crooked — tilted, rotated, crowded, at different heights —
# so frames are polygons, not a grid: an upright tooth gets a plain rectangle,
# a tilted one a rotated quadrilateral that follows its axis. Nothing here
# assumes frames line up in rows or columns.


def _frame_points(frame) -> Optional[list]:
    """Normalised frame -> list of (x, y) points in 0..1, or None.

    Accepts a polygon [[x, y], ...] (3+ points) or an axis-aligned box
    [x0, y0, x1, y1].
    """
    if not frame:
        return None
    try:
        if all(isinstance(v, (int, float)) for v in frame) and len(frame) == 4:
            x0, y0, x1, y1 = (float(v) for v in frame)
            pts = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
        else:
            pts = [(float(p[0]), float(p[1])) for p in frame]
    except (TypeError, ValueError, IndexError):
        return None
    return pts if len(pts) >= 3 else None


def _frame_mask(points: list, W: int, H: int) -> Optional[tuple]:
    """Rasterise a normalised polygon: (x0, y0, mask) over its bounding rect."""
    px = [(min(max(x, 0.0), 1.0) * W, min(max(y, 0.0), 1.0) * H) for x, y in points]
    x0 = int(np.floor(min(p[0] for p in px)))
    y0 = int(np.floor(min(p[1] for p in px)))
    x1 = int(np.ceil(max(p[0] for p in px)))
    y1 = int(np.ceil(max(p[1] for p in px)))
    if x1 - x0 < 3 or y1 - y0 < 3:
        return None
    m = Image.new("L", (x1 - x0, y1 - y0), 0)
    ImageDraw.Draw(m).polygon([(x - x0, y - y0) for x, y in px], fill=1)
    mask = np.asarray(m, dtype=bool)
    return (x0, y0, mask) if mask.sum() >= 9 else None


def _frame_owners(frames: dict, H: int, W: int) -> np.ndarray:
    """Index (into ``list(frames)``) of the frame owning each pixel, -1 outside.

    Frames of crowded or overlapping teeth intersect; a pixel claimed by
    several frames goes to the one whose centroid is nearest, relative to that
    frame's size, so every pixel is counted for exactly one tooth.
    """
    owner = np.full((H, W), -1, dtype=np.int8)
    best = np.full((H, W), np.inf, dtype=np.float32)
    for k, (x0, y0, mask) in enumerate(frames.values()):
        h, w = mask.shape
        ys, xs = np.nonzero(mask)
        cy, cx = ys.mean(), xs.mean()
        scale = max(np.sqrt(mask.sum()), 1.0)
        yy, xx = np.mgrid[0:h, 0:w]
        d = (np.hypot(xx - cx, yy - cy) / scale).astype(np.float32)
        d[~mask] = np.inf
        sub_best = best[y0:y0 + h, x0:x0 + w]
        take = d < sub_best
        sub_best[take] = d[take]
        owner[y0:y0 + h, x0:x0 + w][take] = k
    return owner


def _annotated_b64(img: Image.Image, tooth_pts: dict, quad_pts: dict) -> str:
    """The photo with red quadrant frames and yellow, numbered tooth frames."""
    out = img.copy()
    draw = ImageDraw.Draw(out)
    W, H = out.size
    lw = max(2, max(W, H) // 300)
    for q, pts in quad_pts.items():
        xy = [(x * W, y * H) for x, y in pts]
        draw.polygon(xy, outline=_BOX_RED, width=lw)
        draw.text((min(p[0] for p in xy) + lw, max(min(p[1] for p in xy) - 12, 0)), f"Q{q}", fill=_BOX_RED)
    for tid, pts in tooth_pts.items():
        xy = [(x * W, y * H) for x, y in pts]
        draw.polygon(xy, outline=_BOX_YELLOW, width=lw)
        cx = sum(p[0] for p in xy) / len(xy)
        cy = sum(p[1] for p in xy) / len(xy)
        draw.text((cx - 8, cy - 5), tid, fill=_BOX_YELLOW)
    buf = io.BytesIO()
    out.save(buf, format="JPEG", quality=85)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def _framed_overlay_b64(img: Image.Image, labels: np.ndarray, owner: np.ndarray) -> str:
    """Label colours inside the tooth frames, dimmed photo outside (not counted)."""
    out = (np.asarray(img, dtype=np.uint16) // 3).astype(np.uint8)
    inside = owner >= 0
    for lbl, color in _OVERLAY_COLORS.items():
        out[inside & (labels == lbl)] = color
    buf = io.BytesIO()
    Image.fromarray(out, "RGB").save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def analyze_teeth_in_boxes(
    image_data_uri: str, tooth_boxes: dict, quadrant_boxes: Optional[dict] = None,
    debug: bool = True,
) -> dict:
    """Classify pixels tooth by tooth, inside the yellow frame of each tooth.

    ``tooth_boxes`` maps FDI ids ("1.1" .. "4.3") to normalised frames in
    0..1 — a polygon [[x, y], ...] or a box [x0, y0, x1, y1] — or None for a
    missing / hidden tooth; ``quadrant_boxes`` maps "1".."4" to the red
    quadrant frames the same way. Returns the same shape as
    ``analyze_teeth_pixels``; overall percentages are the sum of the
    per-tooth pixel counts, so they only ever include surface inside the
    tooth frames. Frames come back as normalised polygons.
    """
    img = _decode_image(image_data_uri)
    hsv = np.asarray(img.convert("HSV"))
    labels = _classify(hsv)
    H, W = labels.shape

    tooth_pts: dict = {}
    frames: dict = {}
    for tid in TOOTH_IDS:
        pts = _frame_points((tooth_boxes or {}).get(tid))
        fm = _frame_mask(pts, W, H) if pts else None
        if fm:
            tooth_pts[tid] = pts
            frames[tid] = fm
    owner = _frame_owners(frames, H, W)

    keys = ("white", "purple", "blue", "light_blue", "gum_excluded", "dark_excluded", "other_excluded")
    lbls = (L_WHITE, L_PURPLE, L_BLUE, L_CYAN, L_GUM, L_DARK, L_OTHER)
    counts = dict.fromkeys(keys, 0)
    tooth_counts: dict = {}
    teeth: dict = {}
    for k, (tid, (x0, y0, mask)) in enumerate(frames.items()):
        h, w = mask.shape
        mine = owner[y0:y0 + h, x0:x0 + w] == k
        sub = labels[y0:y0 + h, x0:x0 + w][mine]
        c = {key: int(np.count_nonzero(sub == lbl)) for key, lbl in zip(keys, lbls)}
        tot = c["white"] + c["purple"] + c["blue"] + c["light_blue"]
        if tot < max(50, MIN_BOX_TOOTH_SHARE * sub.size):
            continue
        tooth_counts[tid] = c
        teeth[tid] = _tooth_stats(c["white"], c["purple"], c["blue"], c["light_blue"])
        for key in keys:
            counts[key] += c[key]
    for tid in TOOTH_IDS:
        teeth.setdefault(tid, _missing_tooth())

    tooth = counts["white"] + counts["purple"] + counts["blue"] + counts["light_blue"]
    total = int(labels.size)

    def pct(n: int) -> int:
        return round(100 * n / tooth) if tooth else 0

    color_pct = {key: pct(counts[key]) for key in ("white", "purple", "blue", "light_blue")}

    # Red quadrant frames: from the model when it gave one, else the bounding
    # rectangle of that quadrant's tooth frames. Stats are summed from its teeth.
    quad_pts: dict = {}
    quadrants: dict = {}
    for q, ids in QUADRANT_TEETH.items():
        pts = _frame_points((quadrant_boxes or {}).get(q))
        own = [p for t in ids if t in tooth_pts for p in tooth_pts[t]]
        if not pts and own:
            x0, y0 = min(p[0] for p in own), min(p[1] for p in own)
            x1, y1 = max(p[0] for p in own), max(p[1] for p in own)
            pts = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
        if pts:
            quad_pts[q] = pts
        qc = [tooth_counts[t] for t in ids if t in tooth_counts]
        if qc:
            quadrants[q] = _tooth_stats(*(sum(c[key] for c in qc)
                                          for key in ("white", "purple", "blue", "light_blue")))
        else:
            quadrants[q] = _missing_tooth()

    def norm(pts) -> list:
        return [[round(min(max(x, 0.0), 1.0), 4), round(min(max(y, 0.0), 1.0), 4)] for x, y in pts]

    result = {
        "method": "pixel_hsv_frames_v2",
        "tooth_pixels": tooth,
        "total_pixels": total,
        "tooth_coverage_percent": round(100 * tooth / total) if total else 0,
        "counts": counts,
        "overall_color_percentages": color_pct,
        "stained_area_percent": color_pct["purple"] + color_pct["blue"] + color_pct["light_blue"],
        "teeth": teeth,
        "quadrants": quadrants,
        "tooth_boxes": {tid: norm(p) for tid, p in tooth_pts.items()},
        "quadrant_boxes": {q: norm(p) for q, p in quad_pts.items()},
    }
    if debug:
        result["annotated_image"] = _annotated_b64(img, tooth_pts, quad_pts)
        result["debug_image"] = _framed_overlay_b64(img, labels, owner)
    return result
