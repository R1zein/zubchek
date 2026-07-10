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
H_CYAN_LO, H_CYAN_HI = 165, 200       # light blue / cyan  (oldest plaque)
H_BLUE_LO, H_BLUE_HI = 200, 255       # blue               (medium plaque)
H_PURPLE_LO, H_PURPLE_HI = 255, 315   # purple / violet    (freshest plaque)
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

    cyan = band(H_CYAN_LO, H_CYAN_HI)
    blue = band(H_BLUE_LO, H_BLUE_HI)
    purple = band(H_PURPLE_LO, H_PURPLE_HI)
    # Colored but outside the dye hue bands = gums/lips/tongue (red/pink/orange).
    gum = colored & ~(cyan | blue | purple)

    labels[dark] = L_DARK
    labels[white] = L_WHITE
    labels[cyan] = L_CYAN
    labels[blue] = L_BLUE
    labels[purple] = L_PURPLE
    labels[gum] = L_GUM
    return labels


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
    pollution = color_pct["purple"] + color_pct["blue"] + color_pct["light_blue"]

    result = {
        "method": "pixel_hsv_v1",
        "tooth_pixels": tooth,
        "total_pixels": total,
        "tooth_coverage_percent": round(100 * tooth / total) if total else 0,
        "counts": counts,
        "overall_color_percentages": color_pct,
        "pollution_percentage": pollution,
        "cleanliness_percentage": color_pct["white"],
    }
    if debug:
        result["debug_image"] = _overlay_b64(labels)
    return result
