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
from PIL import Image

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
H_PURPLE_LO, H_PURPLE_HI = 255, 315   # purple / violet (freshest plaque)
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


def _decode_image(image_data_uri: str) -> Image.Image:
    if "," in image_data_uri:
        image_data_uri = image_data_uri.split(",", 1)[1]
    raw = base64.b64decode(image_data_uri)
    img = Image.open(io.BytesIO(raw))
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


def _split_columns(col_counts: np.ndarray, x0: int, x1: int, n: int) -> list:
    """Return n+1 column edges in [x0, x1], with the n-1 internal cuts snapped
    to the interdental gaps (local minima of tooth-pixel density) near evenly
    spaced targets. Falls back to even spacing where no clear gap is found.
    """
    w = x1 - x0
    if w <= n:
        return list(np.linspace(x0, x1, n + 1).astype(int))
    # Smooth the density profile so we snap to real valleys, not pixel noise.
    k = max(3, w // 60)
    smooth = np.convolve(col_counts.astype(float), np.ones(k) / k, mode="same")
    edges = [x0]
    min_gap = max(4, w // (2 * n))          # keep teeth from collapsing
    win = max(5, w // (2 * n))              # search radius around each target
    for i in range(1, n):
        target = x0 + round(w * i / n)
        a = max(edges[-1] + min_gap, target - win)
        b = min(x1 - min_gap, target + win)
        cut = a + int(np.argmin(smooth[a:b])) if b > a else int(target)
        edges.append(int(cut))
    edges.append(x1)
    return edges


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
        edges = _split_columns(col_counts, int(xs.min()), int(xs.max()) + 1, len(ids))
        for i, tid in enumerate(ids):
            cx0, cx1 = edges[i], edges[i + 1]
            cell = np.zeros_like(tooth)
            cell[row0:row1, cx0:cx1] = True
            w = int((white & cell).sum())
            p = int((purple & cell).sum())
            b = int((blue & cell).sum())
            c = int((cyan & cell).sum())
            tot = w + p + b + c
            if tot < min_cell:
                teeth[tid] = {"missing": True, "white": 0, "purple": 0, "blue": 0,
                              "light_blue": 0, "pollution_percentage": 0}
            else:
                pw = round(100 * w / tot)
                pp = round(100 * p / tot)
                pb = round(100 * b / tot)
                pc = max(0, 100 - pw - pp - pb)
                # Severity-weighted plaque index for this tooth (same as overall).
                pollution = round((pp * 1 + pb * 2 + pc * 3) / 3)
                teeth[tid] = {"missing": False, "white": pw, "purple": pp, "blue": pb,
                              "light_blue": pc, "pollution_percentage": min(pollution, 100)}

    fill_arch(0, split, UPPER_TOOTH_IDS)
    fill_arch(split, H, LOWER_TOOTH_IDS)
    return teeth


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
