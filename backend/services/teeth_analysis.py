import json
import re
import logging
import base64
import io
import os

from services.aihub import AIHubService
from schemas.aihub import GenTxtRequest, ChatMessage

logger = logging.getLogger(__name__)

# Vision model used for teeth analysis. Overridable via the APP_AI_MODEL env
# var so the provider/model can be swapped without code changes.
DEFAULT_AI_MODEL = "claude-sonnet-5-5"


def get_ai_model() -> str:
    """Return the configured analysis model, falling back to the default."""
    return os.getenv("APP_AI_MODEL") or DEFAULT_AI_MODEL


def compress_image_data_uri(data_uri: str, max_size: int = 1024, quality: int = 70) -> str:
    """Compress a base64 data URI image to reduce size for AI processing."""
    try:
        from PIL import Image, ImageOps
        
        if "," not in data_uri:
            return data_uri
        header, b64_data = data_uri.split(",", 1)
        image_bytes = base64.b64decode(b64_data)
        
        # Bake in EXIF rotation (the re-encode below drops EXIF), so the model
        # sees the photo upright, the way the browser and the pixel analyzer do.
        img = ImageOps.exif_transpose(Image.open(io.BytesIO(image_bytes)))
        
        width, height = img.size
        if width > max_size or height > max_size:
            ratio = min(max_size / width, max_size / height)
            new_size = (int(width * ratio), int(height * ratio))
            img = img.resize(new_size, Image.LANCZOS)
            logger.info(f"Image resized from {width}x{height} to {new_size[0]}x{new_size[1]}")
        
        if img.mode in ('RGBA', 'P'):
            img = img.convert('RGB')
        
        buffer = io.BytesIO()
        img.save(buffer, format='JPEG', quality=quality, optimize=True)
        compressed_bytes = buffer.getvalue()
        
        original_size = len(image_bytes)
        compressed_size = len(compressed_bytes)
        logger.info(f"Image compressed: {original_size/1024:.0f}KB -> {compressed_size/1024:.0f}KB ({compressed_size/original_size*100:.0f}%)")
        
        compressed_b64 = base64.b64encode(compressed_bytes).decode('utf-8')
        return f"data:image/jpeg;base64,{compressed_b64}"
    except ImportError:
        logger.warning("Pillow not installed, skipping image compression")
        return data_uri
    except Exception as e:
        logger.warning(f"Image compression failed, using original: {e}")
        return data_uri


PROMPT_Z_INDEX = """You are a dental hygiene analysis AI specialized in the Z-Index assessment.

Analyze the provided dental photo of teeth stained with a disclosing agent (plaque indicator dye).

=== PHOTO VALIDATION (check in this order) ===

STEP 1: Determine if the image contains teeth. If the image does NOT contain teeth at all, respond with:
{"error": "no_teeth", "message": "На фото не обнаружены зубы. Пожалуйста, сделайте другое фото."}

STEP 2: Check that the photo shows the 12 ANTERIOR (front) teeth — 6 upper and 6 lower:
- Upper: teeth 13, 12, 11, 21, 22, 23 (right canine to left canine)
- Lower: teeth 43, 42, 41, 31, 32, 33 (right canine to left canine)
The teeth should be in a closed bite position (clenched) or with the mouth slightly open so that both upper and lower front teeth are visible together.
IMPORTANT: If some teeth are MISSING (extracted/lost), that is acceptable — still accept the photo. The total surface of 12 teeth is ALWAYS considered 100% regardless of missing teeth.
If the photo does NOT show the front teeth (e.g., only shows molars, side view, or back teeth), respond with:
{"error": "wrong_teeth", "message": "На фото должны быть видны 12 передних зубов (6 верхних и 6 нижних) в сомкнутом положении. Пожалуйста, сделайте фото передних зубов."}

STEP 3: Check if a disclosing agent (plaque indicator dye) has been applied. Look for characteristic pink, red, blue, purple, or cyan staining on the teeth surfaces. If the teeth appear natural/clean without ANY visible dye coloring, respond with:
{"error": "no_dye_detected", "message": "Краситель не обнаружен. Пожалуйста, нанесите специальный краситель-индикатор налёта на зубы и сделайте новое фото."}

=== Z-INDEX ANALYSIS ===

If the photo passes ALL validation steps, analyze using the Z-INDEX methodology.

You must analyze EACH of the 12 anterior teeth INDIVIDUALLY using quadrant notation:
- Quadrant 1 (upper left from patient's perspective): 1.1 (central incisor, closest to midline), 1.2 (lateral incisor), 1.3 (canine, farthest from midline)
- Quadrant 2 (upper right from patient's perspective): 2.1 (central incisor, closest to midline), 2.2 (lateral incisor), 2.3 (canine, farthest from midline)
- Quadrant 3 (lower right from patient's perspective): 3.1 (central incisor, closest to midline), 3.2 (lateral incisor), 3.3 (canine, farthest from midline)
- Quadrant 4 (lower left from patient's perspective): 4.1 (central incisor, closest to midline), 4.2 (lateral incisor), 4.3 (canine, farthest from midline)

NOTE: .1 is always the tooth closest to the center (midline), .3 is always the tooth farthest from center.

For EACH tooth, determine what percentage of its vestibular (front-facing) surface is covered by each color:
- WHITE (белый) = clean, unstained tooth surface (no plaque)
- PURPLE/VIOLET (фиолетовый) = freshest/newest plaque (lightest staining)
- BLUE/DARK BLUE (синий) = medium-age plaque (moderate staining)
- LIGHT BLUE/CYAN (голубой) = oldest/worst plaque (most concerning)

For each tooth, the four color percentages MUST sum to exactly 100%.
If a tooth is MISSING (extracted/lost), set "missing": true for that tooth.

Also provide the OVERALL percentages across ALL teeth combined (the total surface of all 12 teeth = 100%, missing teeth count as white/clean).

Respond ONLY with valid JSON in this exact format:
{
  "has_teeth": true,
  "teeth": {
    "1.1": {"missing": false, "white": <int>, "purple": <int>, "blue": <int>, "light_blue": <int>},
    "1.2": {"missing": false, "white": <int>, "purple": <int>, "blue": <int>, "light_blue": <int>},
    "1.3": {"missing": false, "white": <int>, "purple": <int>, "blue": <int>, "light_blue": <int>},
    "2.1": {"missing": false, "white": <int>, "purple": <int>, "blue": <int>, "light_blue": <int>},
    "2.2": {"missing": false, "white": <int>, "purple": <int>, "blue": <int>, "light_blue": <int>},
    "2.3": {"missing": false, "white": <int>, "purple": <int>, "blue": <int>, "light_blue": <int>},
    "3.1": {"missing": false, "white": <int>, "purple": <int>, "blue": <int>, "light_blue": <int>},
    "3.2": {"missing": false, "white": <int>, "purple": <int>, "blue": <int>, "light_blue": <int>},
    "3.3": {"missing": false, "white": <int>, "purple": <int>, "blue": <int>, "light_blue": <int>},
    "4.1": {"missing": false, "white": <int>, "purple": <int>, "blue": <int>, "light_blue": <int>},
    "4.2": {"missing": false, "white": <int>, "purple": <int>, "blue": <int>, "light_blue": <int>},
    "4.3": {"missing": false, "white": <int>, "purple": <int>, "blue": <int>, "light_blue": <int>}
  },
  "overall_color_percentages": {
    "white": <int 0-100>,
    "purple": <int 0-100>,
    "blue": <int 0-100>,
    "light_blue": <int 0-100>
  },
  "recommendations": ["<recommendation 1 in Russian>", "<recommendation 2 in Russian>"]
}

CRITICAL RULES:
- You MUST analyze ALL 12 teeth individually. Do NOT skip any quadrant. Each tooth must be evaluated independently.
- For each non-missing tooth: white + purple + blue + light_blue MUST equal exactly 100
- For overall_color_percentages: white + purple + blue + light_blue MUST equal exactly 100
- If a tooth is missing, set "missing": true and set all color values to 0
- Missing teeth are counted as white (clean) in the overall calculation
- Estimate percentages as accurately as possible based on the visible stained areas
- The photo shows BOTH upper and lower teeth. You MUST analyze lower teeth (quadrants 3 and 4) just as carefully as upper teeth (quadrants 1 and 2). Look at the ENTIRE photo including the bottom half.
- If you see ANY colored staining (purple, blue, cyan) on a tooth, it CANNOT be 0% for all colors. Even light staining should be reflected in the percentages.
- Recommendations should be practical dental hygiene advice in Russian

COMMON MISTAKE TO AVOID: Do NOT return 0% pollution for teeth that clearly have visible dye staining. If you can see colored areas on a tooth, those areas represent plaque and must be quantified.
"""


def extract_json_block(text: str) -> str:
    if text.startswith("```"):
        match = re.search(r"```(?:json)?\n(.*?)```", text, re.DOTALL)
        if match:
            text = match.group(1).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        return text[start:end + 1]
    return text


def compute_tooth_z_index(tooth_colors: dict) -> dict:
    """Compute Z-Index for a single tooth."""
    white = tooth_colors.get("white", 0)
    purple = tooth_colors.get("purple", 0)
    blue = tooth_colors.get("blue", 0)
    light_blue = tooth_colors.get("light_blue", 0)
    
    # Normalize if they don't sum to 100
    total_pct = white + purple + blue + light_blue
    if total_pct != 100 and total_pct > 0:
        factor = 100.0 / total_pct
        white = round(white * factor)
        purple = round(purple * factor)
        blue = round(blue * factor)
        light_blue = 100 - white - purple - blue
    
    # Calculate points (max 600 per tooth). Integer weights so total_points stays
    # int; fresh plaque counts strongly so the index reflects coverage, not just age.
    total_points = white * 0 + purple * 4 + blue * 5 + light_blue * 6
    total_points = min(total_points, 600)

    # Pollution percentage for this tooth
    pollution_pct = round(total_points / 600 * 100)
    
    return {
        "white": white,
        "purple": purple,
        "blue": blue,
        "light_blue": light_blue,
        "total_points": total_points,
        "pollution_percentage": pollution_pct,
    }


def compute_z_index(color_percentages: dict) -> dict:
    """
    Compute Z-Index from overall color percentages.
    
    Formula:
    - White (clean): 0 points per %
    - Purple (fresh plaque): 4 points per %
    - Blue (medium plaque): 5 points per %
    - Light blue/cyan (old plaque): 6 points per %

    Total points max = 600 (if 100% light_blue)
    Pollution % = total_points / 300 * 100
    Cleanliness % = 100 - pollution %
    
    Levels (by pollution %):
    - 0-30%: low (Низкий)
    - 31-60%: medium (Средний)
    - 61-100%: high (Сильный)
    """
    white = color_percentages.get("white", 0)
    purple = color_percentages.get("purple", 0)
    blue = color_percentages.get("blue", 0)
    light_blue = color_percentages.get("light_blue", 0)
    
    # Normalize if they don't sum to 100
    total_pct = white + purple + blue + light_blue
    if total_pct != 100 and total_pct > 0:
        factor = 100.0 / total_pct
        white = round(white * factor)
        purple = round(purple * factor)
        blue = round(blue * factor)
        light_blue = 100 - white - purple - blue
    
    # Calculate points
    points_white = white * 0
    points_purple = purple * 4
    points_blue = blue * 5
    points_light_blue = light_blue * 6

    total_points = points_white + points_purple + points_blue + points_light_blue
    total_points = min(total_points, 600)

    # Pollution percentage
    pollution_pct = round(total_points / 600 * 100)
    
    # Cleanliness percentage (inverted)
    cleanliness_pct = 100 - pollution_pct
    
    # Risk level
    if pollution_pct <= 30:
        risk_level = "low"
        hygiene_level = "Низкий уровень загрязнения"
    elif pollution_pct <= 60:
        risk_level = "medium"
        hygiene_level = "Средний уровень загрязнения"
    else:
        risk_level = "high"
        hygiene_level = "Сильный уровень загрязнения"
    
    return {
        "color_percentages": {
            "white": white,
            "purple": purple,
            "blue": blue,
            "light_blue": light_blue,
        },
        "points_breakdown": {
            "white": points_white,
            "purple": points_purple,
            "blue": points_blue,
            "light_blue": points_light_blue,
        },
        "total_points": total_points,
        "max_points": 600,
        "pollution_percentage": pollution_pct,
        "cleanliness_percentage": cleanliness_pct,
        "risk_level": risk_level,
        "hygiene_level": hygiene_level,
    }


# ---------------------------------------------------------------------------
# Recommendations
#
# The pixel analyzer gives us much more than one number: per-tooth colour
# shares, upper vs lower arch, patient's right vs left side, and plaque age.
# `summarize_findings` turns that into concrete facts. Both the AI prompt and
# the rule-based fallback are built from those facts, so a report never falls
# back to generic "brush twice a day" advice that would fit any patient.
# ---------------------------------------------------------------------------

# Tooth groups, mirrored pairs (FDI numbering, patient's perspective).
_TOOTH_GROUPS = [
    ("upper_central", ("1.1", "2.1"), "верхних центральных резцах", "upper central incisors"),
    ("upper_lateral", ("1.2", "2.2"), "верхних боковых резцах", "upper lateral incisors"),
    ("upper_canine", ("1.3", "2.3"), "верхних клыках", "upper canines"),
    ("lower_central", ("3.1", "4.1"), "нижних центральных резцах", "lower central incisors"),
    ("lower_lateral", ("3.2", "4.2"), "нижних боковых резцах", "lower lateral incisors"),
    ("lower_canine", ("3.3", "4.3"), "нижних клыках", "lower canines"),
]
_UPPER = ("1.1", "1.2", "1.3", "2.1", "2.2", "2.3")
_LOWER = ("3.1", "3.2", "3.3", "4.1", "4.2", "4.3")
_RIGHT = ("1.1", "1.2", "1.3", "4.1", "4.2", "4.3")  # patient's right side
_LEFT = ("2.1", "2.2", "2.3", "3.1", "3.2", "3.3")

# How far apart two zones must be (in index points) before we call it out.
_ZONE_GAP = 10


def _avg_pollution(teeth: dict, ids) -> int | None:
    vals = [teeth[t]["pollution_percentage"] for t in ids
            if t in teeth and not teeth[t].get("missing")]
    return round(sum(vals) / len(vals)) if vals else None


def summarize_findings(color_pct: dict, teeth: dict | None, pollution_pct: int) -> dict:
    """Turn raw pixel numbers into the facts recommendations should rest on."""
    purple = color_pct.get("purple", 0)
    blue = color_pct.get("blue", 0)
    old = color_pct.get("light_blue", 0)
    stained = purple + blue + old
    # Share of stained surface that is NOT fresh — plaque that has survived at
    # least one brushing (blue = medium, light_blue = old).
    mature_share = round(100 * (blue + old) / stained) if stained else 0

    f = {
        "pollution": pollution_pct,
        "stained": stained,
        "fresh": purple,
        "medium": blue,
        "old": old,
        "mature_share": mature_share,
        "worst_groups": [],   # [(key, ru, en, avg)] most plaque first
        "clean_groups": [],   # [(key, ru, en, avg)]
        "upper": None, "lower": None,
        "right": None, "left": None,
        "worst_tooth": None,  # (id, pollution)
        "groups": {},         # key -> (key, ru, en, avg), every group with data
    }
    if not teeth:
        return f

    groups = []
    for key, ids, ru, en in _TOOTH_GROUPS:
        avg = _avg_pollution(teeth, ids)
        if avg is not None:
            groups.append((key, ru, en, avg))
    groups.sort(key=lambda g: g[3], reverse=True)
    f["groups"] = {g[0]: g for g in groups}
    # "Problem" = clearly worse than the mouth average, and not trivially low.
    f["worst_groups"] = [g for g in groups
                         if g[3] >= max(pollution_pct + _ZONE_GAP // 2, 25)][:2]
    if not f["worst_groups"] and groups and groups[0][3] >= 25:
        f["worst_groups"] = groups[:1]
    f["clean_groups"] = [g for g in groups if g[3] <= 15]

    f["upper"] = _avg_pollution(teeth, _UPPER)
    f["lower"] = _avg_pollution(teeth, _LOWER)
    f["right"] = _avg_pollution(teeth, _RIGHT)
    f["left"] = _avg_pollution(teeth, _LEFT)

    present = [(t, v["pollution_percentage"]) for t, v in teeth.items() if not v.get("missing")]
    if present:
        f["worst_tooth"] = max(present, key=lambda x: x[1])
    return f


def _findings_for_prompt(f: dict) -> str:
    """Compact, factual Russian summary of the findings for the model."""
    lines = [
        f"- Индекс загрязнённости (взвешенный по возрасту налёта): {f['pollution']}%.",
        f"- Окрашено {f['stained']}% поверхности зубов: свежий налёт {f['fresh']}%, "
        f"средний {f['medium']}%, старый {f['old']}%. Зрелый (средний+старый) — "
        f"{f['mature_share']}% всего налёта.",
    ]
    if f["worst_groups"]:
        lines.append("- Больше всего налёта: " + "; ".join(
            f"{g[1]} — {g[3]}%" for g in f["worst_groups"]) + ".")
    if f["clean_groups"]:
        lines.append("- Чище всего: " + ", ".join(g[1] for g in f["clean_groups"]) + ".")
    if f["upper"] is not None and f["lower"] is not None:
        lines.append(f"- Верхняя челюсть {f['upper']}%, нижняя {f['lower']}%.")
    if f["right"] is not None and f["left"] is not None:
        lines.append(f"- Правая сторона пациента {f['right']}%, левая {f['left']}%.")
    if f["worst_tooth"]:
        lines.append(f"- Самый загрязнённый зуб: {f['worst_tooth'][0]} ({f['worst_tooth'][1]}%).")
    return "\n".join(lines)


# Changes smaller than this are within the pixel analyzer's photo-to-photo
# noise (lighting, angle, how much dye was applied), so we don't call them out.
_PROGRESS_OVERALL_GAP = 5
_PROGRESS_ZONE_GAP = 8


def compute_progress(prev: dict, prev_report_id: int, prev_created_at, f: dict, now=None) -> dict | None:
    """Compare this analysis with the patient's previous one.

    `prev` is the previous report's stored analysis_data, `f` the current
    findings. Returns None when the previous report has no usable numbers.
    """
    from datetime import datetime, timezone

    if not isinstance(prev, dict) or prev.get("pollution_percentage") is None:
        return None
    pf = summarize_findings(prev.get("color_percentages") or {}, prev.get("teeth") or None,
                            int(prev["pollution_percentage"]))

    delta = f["pollution"] - pf["pollution"]
    if delta <= -_PROGRESS_OVERALL_GAP:
        trend = "improved"
    elif delta >= _PROGRESS_OVERALL_GAP:
        trend = "worsened"
    else:
        trend = "stable"

    improved, worsened = [], []
    for key, (_, ru, en, after) in f["groups"].items():
        if key not in pf["groups"]:
            continue
        before = pf["groups"][key][3]
        change = {"key": key, "ru": ru, "en": en, "before": before, "after": after, "delta": after - before}
        if after - before <= -_PROGRESS_ZONE_GAP:
            improved.append(change)
        elif after - before >= _PROGRESS_ZONE_GAP:
            worsened.append(change)
    improved.sort(key=lambda c: c["delta"])
    worsened.sort(key=lambda c: c["delta"], reverse=True)

    days = None
    if prev_created_at is not None:
        now = now or datetime.now(timezone.utc)
        if prev_created_at.tzinfo is None:
            prev_created_at = prev_created_at.replace(tzinfo=timezone.utc)
        days = max(0, (now - prev_created_at).days)

    return {
        "previous_report_id": prev_report_id,
        "previous_date": prev_created_at.isoformat() if prev_created_at is not None else None,
        "days_between": days,
        "pollution_before": pf["pollution"],
        "pollution_after": f["pollution"],
        "delta": delta,
        "trend": trend,
        "improved": improved[:3],
        "worsened": worsened[:3],
        "mature_before": pf["mature_share"],
        "mature_after": f["mature_share"],
    }


def _days_ru(n: int) -> str:
    if n % 10 == 1 and n % 100 != 11:
        return f"{n} день"
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return f"{n} дня"
    return f"{n} дней"


def _progress_for_prompt(p: dict) -> str:
    when = f" ({_days_ru(p['days_between'])} назад)" if p.get("days_between") is not None else ""
    lines = [
        f"Динамика с прошлого теста{when}:",
        f"- Индекс был {p['pollution_before']}%, стал {p['pollution_after']}% "
        f"({'+' if p['delta'] > 0 else ''}{p['delta']}). Итог: "
        + {"improved": "улучшение", "worsened": "ухудшение", "stable": "без существенных изменений"}[p["trend"]] + ".",
        f"- Доля зрелого налёта: была {p['mature_before']}%, стала {p['mature_after']}%.",
    ]
    if p["improved"]:
        lines.append("- Стало чище: " + "; ".join(f"{c['ru']} {c['before']}% → {c['after']}%" for c in p["improved"]) + ".")
    if p["worsened"]:
        lines.append("- Стало хуже: " + "; ".join(f"{c['ru']} {c['before']}% → {c['after']}%" for c in p["worsened"]) + ".")
    lines.append(
        "Первая рекомендация — о динамике: конкретно отметь, что улучшилось (зоны и цифры), и прямо "
        "назови, что ухудшилось или не изменилось. Изменения меньше 5 пунктов в пределах погрешности "
        "фото — не называй их улучшением. Не придумывай динамику сверх этих данных."
    )
    return "\n".join(lines)


def _progress_recommendation(p: dict) -> tuple[str, str]:
    """Rule-based (ru, en) item describing the change since the last test."""
    when_ru = f" ({_days_ru(p['days_between'])} назад)" if p.get("days_between") is not None else ""
    when_en = f" ({p['days_between']} days ago)" if p.get("days_between") is not None else ""
    b, a = p["pollution_before"], p["pollution_after"]
    if p["trend"] == "improved":
        ru = f"Есть прогресс: с прошлого теста{when_ru} индекс налёта снизился с {b}% до {a}%."
        en = f"You are making progress: since your last test{when_en} the plaque index dropped from {b}% to {a}%."
    elif p["trend"] == "worsened":
        ru = f"С прошлого теста{when_ru} индекс налёта вырос с {b}% до {a}% — гигиена ослабла, к ней стоит вернуться."
        en = f"Since your last test{when_en} the plaque index rose from {b}% to {a}% — your routine has slipped and needs attention."
    else:
        ru = f"С прошлого теста{when_ru} индекс почти не изменился ({b}% → {a}%)."
        en = f"Since your last test{when_en} the index has barely changed ({b}% → {a}%)."
    if p["improved"]:
        ru += " Заметно чище стало на " + ", ".join(f"{c['ru']} ({c['before']}% → {c['after']}%)" for c in p["improved"]) + " — то, что вы изменили в чистке этих зон, работает."
        en += " Noticeably cleaner: " + ", ".join(f"{c['en']} ({c['before']}% → {c['after']}%)" for c in p["improved"]) + " — whatever you changed there is working."
    if p["worsened"]:
        ru += " Хуже стало на " + ", ".join(f"{c['ru']} ({c['before']}% → {c['after']}%)" for c in p["worsened"]) + " — уделите им больше времени."
        en += " Worse: " + ", ".join(f"{c['en']} ({c['before']}% → {c['after']}%)" for c in p["worsened"]) + " — give these areas more time."
    if not p["improved"] and not p["worsened"] and p["trend"] == "stable":
        ru += " Чтобы сдвинуться с места, сосредоточьтесь на зонах из рекомендаций ниже."
        en += " To move forward, focus on the areas in the recommendations below."
    return ru, en


def _ortho_kind(ortho_type: str | None) -> str | None:
    """Normalise a free-text appliance description to braces/aligners/retainer."""
    if not ortho_type:
        return None
    t = ortho_type.lower()
    if any(w in t for w in ("брекет", "bracket", "brace")):
        return "braces"
    if any(w in t for w in ("элайнер", "aligner", "капп", "капа", "аттачмент", "attachment", "кнопк")):
        return "aligners"
    if any(w in t for w in ("ретейнер", "retainer", "ретеншн")):
        return "retainer"
    return "other"


def build_rule_based_recommendations(
    f: dict, risk_level: str, ortho_type: str | None = None, progress: dict | None = None
) -> tuple[list, list]:
    """Specific, data-driven recommendations without the AI (ru, en).

    Used when the model is unreachable or returns something unusable. Every
    item is derived from this patient's numbers, so even the fallback names
    the actual problem zones instead of giving universal advice.
    """
    ru: list = []
    en: list = []

    # 0. Progress since the previous test — the most motivating fact we have.
    if progress:
        p_ru, p_en = _progress_recommendation(progress)
        ru.append(p_ru)
        en.append(p_en)

    # 1. Where — the zones that need the most attention.
    if f["worst_groups"]:
        z_ru = " и ".join(f"{g[1]} ({g[3]}%)" for g in f["worst_groups"])
        z_en = " and ".join(f"{g[2]} ({g[3]}%)" for g in f["worst_groups"])
        ru.append(
            f"Главная зона внимания — налёт сильнее всего скапливается на {z_ru}. "
            "Начинайте чистку именно с них, пока внимание не рассеялось: щётку держите под углом 45° "
            "к линии десны и делайте короткие вибрирующие движения на месте (метод Басса), "
            "по 8–10 движений на каждый участок, затем выметающее движение от десны к краю зуба."
        )
        en.append(
            f"Main focus area — plaque builds up most on the {z_en}. "
            "Start brushing there while you are still attentive: hold the brush at 45° to the gum line "
            "and make short vibrating strokes in place (the Bass technique), 8–10 strokes per spot, "
            "then sweep from the gum towards the biting edge."
        )
    elif f["pollution"] > 30:
        ru.append(
            "Налёт распределён по зубам довольно равномерно — значит, дело не в одной пропущенной зоне, "
            "а в технике и времени чистки в целом. Держите щётку под углом 45° к десне, делайте короткие "
            "вибрирующие движения (метод Басса) и чистите не меньше 2 минут, мысленно поделив рот на 4 части по 30 секунд."
        )
        en.append(
            "Plaque is spread fairly evenly, so the issue is overall technique and brushing time rather than one "
            "missed spot. Hold the brush at 45° to the gums, use short vibrating strokes (Bass technique) and brush "
            "for at least 2 minutes, splitting the mouth into 4 quarters of 30 seconds."
        )

    # 2. Asymmetry — upper/lower and right/left.
    if f["lower"] is not None and f["upper"] is not None and f["lower"] - f["upper"] >= _ZONE_GAP:
        ru.append(
            f"Нижние зубы загрязнены заметно сильнее верхних ({f['lower']}% против {f['upper']}%). "
            "Рядом с нижними резцами открываются протоки слюнных желёз, поэтому налёт здесь быстрее "
            "минерализуется в зубной камень. Чистите нижние передние зубы вертикальными движениями, "
            "поставив щётку «вертикально», и не забывайте их внутреннюю (язычную) сторону."
        )
        en.append(
            f"Your lower teeth carry noticeably more plaque than the upper ones ({f['lower']}% vs {f['upper']}%). "
            "Salivary glands open next to the lower incisors, so plaque there hardens into tartar faster. Brush "
            "the lower front teeth with the brush held upright using vertical strokes, and do not skip their inner side."
        )
    elif f["upper"] is not None and f["lower"] is not None and f["upper"] - f["lower"] >= _ZONE_GAP:
        ru.append(
            f"Верхние зубы загрязнены сильнее нижних ({f['upper']}% против {f['lower']}%). "
            "Обычно это значит, что щётка не доходит до линии десны сверху. Приподнимайте губу и "
            "направляйте щетину вверх под углом 45°, к самому краю десны."
        )
        en.append(
            f"Your upper teeth carry more plaque than the lower ones ({f['upper']}% vs {f['lower']}%). "
            "This usually means the brush is not reaching the upper gum line. Lift your lip and aim the bristles "
            "upwards at 45°, right at the edge of the gum."
        )
    if f["right"] is not None and f["left"] is not None and abs(f["right"] - f["left"]) >= _ZONE_GAP:
        worse_ru, worse_en = ("правой", "right") if f["right"] > f["left"] else ("левой", "left")
        hi, lo = max(f["right"], f["left"]), min(f["right"], f["left"])
        ru.append(
            f"На {worse_ru} стороне налёта больше ({hi}% против {lo}%). Чаще всего хуже вычищается сторона "
            "ведущей руки — её неудобно чистить той же рукой. Начинайте чистку с этой стороны или "
            "чистите её, переложив щётку в другую руку."
        )
        en.append(
            f"There is more plaque on your {worse_en} side ({hi}% vs {lo}%). The side of your dominant hand is usually "
            "cleaned worse because it is awkward to reach with that hand. Start with this side, or switch the brush "
            "to your other hand for it."
        )

    # 3. Plaque age — the most informative part of the dye test.
    if f["stained"] > 0:
        if f["mature_share"] >= 50:
            ru.append(
                f"{f['mature_share']}% налёта — зрелый (синий и голубой), то есть он пережил как минимум одну "
                "чистку. Это не случайный пропуск, а участки, которые вы систематически не очищаете. Зрелый налёт "
                "за 1–2 недели начинает превращаться в зубной камень, который щёткой уже не удалить, — поэтому "
                "эти зоны стоит прочищать прицельно каждый вечер."
            )
            en.append(
                f"{f['mature_share']}% of the plaque is mature (blue and light blue), meaning it has survived at least "
                "one brushing. These are not random misses but areas you consistently skip. Mature plaque starts turning "
                "into tartar within 1–2 weeks, which a toothbrush can no longer remove — so clean these areas deliberately every evening."
            )
        else:
            ru.append(
                "Налёт в основном свежий (фиолетовый) — он образовался за последние сутки. Техника в целом "
                "работает, но не хватает тщательности или времени. Чистите с таймером не меньше 2 минут и "
                "проверяйте себя языком: гладкая поверхность — чисто, шероховатая — налёт остался."
            )
            en.append(
                "Most of the plaque is fresh (purple) — it formed within the last day. Your technique basically works, "
                "but you need more thoroughness or time. Brush with a timer for at least 2 minutes and check with your "
                "tongue: smooth means clean, rough means plaque is still there."
            )

    # 4. Appliance-specific care.
    kind = _ortho_kind(ortho_type)
    if kind == "braces":
        ru.append(
            "На фото видны брекеты — вокруг замков и под дугой налёт копится в несколько раз быстрее. "
            "Используйте монопучковую щётку для очистки вокруг каждого замка, ёршик для пространства под "
            "дугой и суперфлосс для межзубных промежутков. Ирригатор здесь особенно полезен как дополнение, но не замена щётке."
        )
        en.append(
            "Braces are visible in the photo — plaque builds up several times faster around the brackets and under the wire. "
            "Use a single-tuft brush around each bracket, an interdental brush under the wire and superfloss between teeth. "
            "A water flosser helps a lot here, as an addition to brushing, not a replacement."
        )
    elif kind == "aligners":
        ru.append(
            "Похоже, вы носите элайнеры (видны аттачменты). Капы прижимают налёт к зубам и лишают их "
            "очищения слюной, поэтому чистите зубы перед каждым надеванием кап, снимайте их для еды и "
            "сладких напитков. Вокруг аттачментов чистите мягкой щёткой круговыми движениями — налёт "
            "задерживается у их краёв. Сами капы мойте прохладной водой мягкой щёткой без абразивной пасты."
        )
        en.append(
            "It looks like you wear aligners (attachments are visible). Aligners press plaque against the teeth and block "
            "saliva from cleaning them, so brush before every time you put them back in, and take them out to eat or drink "
            "anything sweet. Clean around the attachments with a soft brush in small circles — plaque collects at their edges. "
            "Wash the aligners in cool water with a soft brush, without abrasive toothpaste."
        )
    elif kind == "retainer":
        ru.append(
            "Видна ретенционная конструкция. За несъёмным ретейнером налёт и камень скапливаются особенно "
            "быстро: прочищайте под проволокой суперфлоссом или ёршиком каждый вечер, а съёмный ретейнер "
            "чистите отдельной щёткой ежедневно."
        )
        en.append(
            "A retainer is visible. Plaque and tartar build up fast behind a fixed retainer: clean under the wire with "
            "superfloss or an interdental brush every evening, and brush a removable retainer separately every day."
        )

    # 5. Interdental cleaning — the brush never reaches there, whatever the score.
    ru.append(
        "Щётка не очищает межзубные промежутки — а именно там начинается большая часть кариеса и "
        "воспаления дёсен. Раз в день, лучше вечером, используйте зубную нить или межзубные ёршики "
        "подходящего размера (ёршик должен входить без усилия, но плотно). Ирригатор — полезное "
        "дополнение, но нить и ёршики он не заменяет."
    )
    en.append(
        "A toothbrush does not clean between the teeth — and that is where most cavities and gum inflammation start. "
        "Once a day, ideally in the evening, use floss or interdental brushes of the right size (the brush should slide "
        "in without force but fit snugly). A water flosser is a good addition but does not replace floss or brushes."
    )

    # 6. Follow-up — what to do next and when to re-test.
    if risk_level == "high":
        ru.append(
            "При таком уровне налёта рекомендуется профессиональная гигиена у стоматолога-гигиениста в "
            "ближайшие недели: часть налёта, скорее всего, уже минерализовалась. После чистки повторите "
            "тест с красителем через 2 недели, чтобы проверить, как изменилась домашняя гигиена."
        )
        en.append(
            "With this much plaque, a professional cleaning at a dental hygienist within the next few weeks is recommended: "
            "some of it has most likely hardened already. Repeat the dye test 2 weeks after the cleaning to see how your "
            "home care has improved."
        )
    elif risk_level == "medium":
        ru.append(
            "Повторите тест с красителем через 3–4 недели и сравните результат: если отмеченные зоны стали "
            "чище — техника исправлена. Плановую профессиональную гигиену проходите раз в 6 месяцев."
        )
        en.append(
            "Repeat the dye test in 3–4 weeks and compare: if the highlighted areas are cleaner, your technique is fixed. "
            "Have a routine professional cleaning every 6 months."
        )
    else:
        clean = f["clean_groups"]
        ru.append(
            "Хороший уровень гигиены"
            + (f" — особенно чисто на {', '.join(g[1] for g in clean[:2])}" if clean else "")
            + ". Сохраняйте привычку: чистка 2 раза в день по 2 минуты пастой с фтором (1450 ppm), "
            "межзубная нить, профгигиена раз в 6 месяцев. Повторяйте тест с красителем раз в 2–3 месяца для контроля."
        )
        en.append(
            "Good level of hygiene"
            + (f" — especially clean on the {', '.join(g[2] for g in clean[:2])}" if clean else "")
            + ". Keep the routine: brush twice a day for 2 minutes with fluoride toothpaste (1450 ppm), floss, and have "
            "a professional cleaning every 6 months. Repeat the dye test every 2–3 months to keep track."
        )

    return ru[:8], en[:8]


def _recs_look_usable(recs) -> bool:
    """Reject empty / generic AI output so it doesn't reach the patient.

    The model is asked for 4–6 detailed items; a short list of one-liners means
    something went wrong (truncation, refusal-style reply) and the rule-based
    set is better.
    """
    if not isinstance(recs, list) or len(recs) < 3:
        return False
    texts = [str(r).strip() for r in recs if str(r).strip()]
    if len(texts) < 3:
        return False
    return sum(len(t) for t in texts) / len(texts) >= 80


_RECS_PROMPT = """Ты — стоматолог-гигиенист. Тебе прислали фото зубов пациента после нанесения индикатора налёта и результаты автоматического пиксельного анализа этого фото.

ШАГ 1. Проверка фото. Определи по самому изображению, ничего не предполагая заранее:
- is_teeth: true, если на фото есть человеческие зубы — даже несколько, даже если кадр тёмный, близкий или частичный. false только если зубов нет вообще (лицо целиком, предмет, еда, животное, текст, пустой кадр).
- has_dye: true, если на зубах есть любое окрашивание индикатором (розовое, красное, фиолетовое, синее — даже слабое или только вдоль десны). false — только если зубы обычного цвета без окраски.
Если is_teeth=false — верни has_dye=false, orthodontic_detected=false и пустые списки рекомендаций; дальше не анализируй.

ШАГ 2. Ортодонтия. Осмотри каждый зуб: брекеты (замки, дуги, лигатуры), элайнеры (прозрачные капы), аттачменты от элайнеров (маленькие выпуклости цвета зуба на середине коронки — их легко пропустить, ищи блики и бугорки), ретейнеры, пластинки. Если видишь аттачменты — пациент носит элайнеры, даже если кап на фото нет.

ШАГ 3. Рекомендации. Данные пиксельного анализа (точные, им доверяй больше, чем своей оценке цвета):
{findings}

Напиши 4–6 рекомендаций, персональных для ЭТОГО пациента. Требования:
- Каждая рекомендация опирается на конкретный факт из данных или фото и называет его: зону (какие зубы, верх/низ, сторона), цифру, возраст налёта, конструкцию. Совет, который подошёл бы любому человеку («чистите зубы 2 раза в день»), без привязки к данным — не годится.
- Каждая — 2–4 предложения: что не так, почему это важно (что будет, если не исправить) и как именно исправить (техника, инструмент, частота).
- Порядок — по важности: сначала самая большая проблема этого пациента.
- Если зрелого налёта много — объясни, что это систематически пропускаемые зоны и риск зубного камня. Если налёт в основном свежий — что техника работает, но не хватает тщательности.
- Если найдена ортодонтическая конструкция — отдельная рекомендация по уходу именно за ней.
- Если конструкций нет — не упоминай ортодонтию вообще: не пиши, что брекетов, элайнеров или других конструкций нет и что особый уход не нужен.
- Обязательно скажи, когда повторить тест с красителем, и нужна ли профессиональная гигиена.
- Пиши понятным пациенту языком, без латыни и сокращений, без markdown, без нумерации внутри строк. Не ставь диагнозов — ты оцениваешь гигиену, а не лечишь.

Верни один и тот же набор рекомендаций на двух языках, одинаковый по смыслу: русский (recommendations) и английский (recommendations_en).

Ответь только валидным JSON без пояснений:
{{"is_teeth": true, "has_dye": true, "orthodontic_detected": false, "orthodontic_type": null, "recommendations": ["...", "..."], "recommendations_en": ["...", "..."]}}"""


async def detect_ortho_and_recommend(
    image_data_uri: str, pollution_pct: int, risk_level: str, color_pct: dict,
    teeth: dict | None = None, progress: dict | None = None,
) -> dict:
    """One vision call: validate the photo, detect orthodontic appliances and
    write personalised hygiene recommendations in Russian and English.

    The numeric index comes from the pixel analyzer; this is the semantic part.
    Returns {is_teeth, has_dye, orthodontic_detected, orthodontic_type,
    recommendations, recommendations_en, recommendations_source}. If the AI is
    unavailable or its answer is unusable, recommendations come from
    `build_rule_based_recommendations` (still specific to this patient).
    """
    findings = summarize_findings(color_pct, teeth, pollution_pct)
    facts = _findings_for_prompt(findings)
    if progress:
        facts += "\n\n" + _progress_for_prompt(progress)
    prompt = _RECS_PROMPT.format(findings=facts)

    # Aligner attachments are small and tooth-coloured, so keep detail high.
    compressed = compress_image_data_uri(image_data_uri, max_size=1600, quality=90)
    request = GenTxtRequest(
        messages=[ChatMessage(role="user", content=[
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": compressed}},
        ])],
        model=get_ai_model(),
        # Current Claude models think by default and that spends the same
        # budget; 3000 used to truncate the bilingual answer mid-JSON, which
        # silently dropped every report to the static fallback.
        max_tokens=16000,
    )

    payload = None
    service = AIHubService()
    for attempt in (1, 2):
        try:
            response = await service.gentxt(request)
            payload = json.loads(extract_json_block(response.content.strip()))
            if not isinstance(payload, dict):
                raise ValueError("AI answer is not a JSON object")
            break
        except Exception as e:  # pragma: no cover - defensive
            payload = None
            logger.warning(f"ortho+recommend AI attempt {attempt} failed: {e}")

    if payload is None:
        # AI unavailable: don't block (the pixel pre-check already passed) — assume valid.
        recs, recs_en = build_rule_based_recommendations(findings, risk_level, progress=progress)
        return {
            "is_teeth": True,
            "has_dye": True,
            "orthodontic_detected": False,
            "orthodontic_type": None,
            "recommendations": recs,
            "recommendations_en": recs_en,
            "recommendations_source": "rules",
        }

    is_teeth = bool(payload.get("is_teeth", True))
    ortho_detected = bool(payload.get("orthodontic_detected", False))
    ortho_type = (payload.get("orthodontic_type") or None) if ortho_detected else None
    recs = payload.get("recommendations") or []
    recs_en = payload.get("recommendations_en") or []

    source = "ai"
    if is_teeth and not (_recs_look_usable(recs) and _recs_look_usable(recs_en)):
        logger.warning(
            f"AI recommendations unusable (ru={len(recs) if isinstance(recs, list) else '?'}, "
            f"en={len(recs_en) if isinstance(recs_en, list) else '?'}), using rule-based set"
        )
        recs, recs_en = build_rule_based_recommendations(findings, risk_level, ortho_type, progress)
        source = "rules"

    return {
        "is_teeth": is_teeth,
        "has_dye": bool(payload.get("has_dye", True)),
        "orthodontic_detected": ortho_detected,
        "orthodontic_type": ortho_type,
        "recommendations": [str(x).strip() for x in recs][:8],
        "recommendations_en": [str(x).strip() for x in recs_en][:8],
        "recommendations_source": source,
    }


# ---------------------------------------------------------------------------
# Tooth localisation
#
# Before any pixel is counted, the vision model marks where each tooth is: a
# yellow box per anterior tooth and a green box per quadrant. The pixel analyzer
# then scores each yellow box on its own (see pixel_analysis.analyze_teeth_in_boxes).
# ---------------------------------------------------------------------------

# Long side of the image the model sees. Kept under the API's own downscale
# limit so the pixel coordinates it returns refer to exactly this image.
_LOCATE_MAX_SIDE = 1024

# Fewer valid tooth frames than this means the answer is unreliable — fall back
# to the whole-photo analysis instead of scoring the mouth from a few teeth.
MIN_TOOTH_BOXES = 6

# A single tooth never takes up more than this share of the photo; a bigger
# frame swallowed several teeth or the whole mouth.
_MAX_BOX_AREA = 0.25

_LOCATE_PROMPT = """Ты размечаешь фото передних зубов пациента после нанесения индикатора налёта. Размер изображения: {w}×{h} пикселей. Координаты — целые пиксели этого изображения, начало в левом верхнем углу.

Считай, что фото не зеркальное: левая сторона снимка — правая сторона пациента.

Зубы у пациента могут быть кривыми: наклонёнными, повёрнутыми, выдвинутыми вперёд или назад, стоящими на разной высоте, налезающими друг на друга, с промежутками. Не подгоняй разметку под ровную сетку: рамки НЕ обязаны стоять ровно в ряд или друг под другом, могут быть разного размера и частично перекрываться. Каждую рамку ставь туда, где этот зуб находится на самом деле. Определяй зуб по форме (центральный резец — широкий, боковой — уже, клык — острый бугор), а не по порядковому месту в ряду.

ШАГ 1. is_teeth: true, если на фото есть человеческие зубы. Если нет — верни is_teeth=false и пустые quadrants и teeth.

ШАГ 2. Зелёные рамки — 4 квадранта, каждая охватывает три передних зуба своего квадранта. Граница между 1/2 и 3/4 — средняя линия между центральными резцами (она может быть не в центре снимка):
- "1" — верхние зубы слева от средней линии на снимке (1.1, 1.2, 1.3);
- "2" — верхние зубы справа от средней линии на снимке (2.1, 2.2, 2.3);
- "3" — нижние зубы справа от средней линии на снимке (3.1, 3.2, 3.3);
- "4" — нижние зубы слева от средней линии на снимке (4.1, 4.2, 4.3).
Формат: прямоугольник [x1, y1, x2, y2].

ШАГ 3. Жёлтые рамки — по одной на каждый из 12 зубов. .1 — центральный резец, .2 — боковой резец, .3 — клык. Премоляры и дальние зубы не размечай.
- Рамка плотно охватывает видимую переднюю поверхность коронки ТОЛЬКО этого зуба: от края десны до режущего края, от одного межзубного промежутка до другого.
- Ровно стоящий зуб — прямоугольник [x1, y1, x2, y2] (левый верхний и правый нижний угол).
- Наклонённый или повёрнутый зуб — повёрнутая рамка вдоль оси зуба: 4 угла [[x, y], [x, y], [x, y], [x, y]] по порядку обхода. Так в рамку не попадут соседние зубы и десна.
- Если зуб частично закрыт соседним (скученность), обведи только его видимую часть.
- Окрашенный налёт (фиолетовый, синий, голубой, розовый — в том числе полоска у самой десны) — часть зуба, включай его в рамку.
- Не включай десну, губы, соседние зубы и тёмную щель между челюстями.
- Если зуб отсутствует или полностью закрыт — null.

Ответь только валидным JSON без пояснений, например:
{{"is_teeth": true, "quadrants": {{"1": [x1, y1, x2, y2], "2": [...], "3": [...], "4": [...]}}, "teeth": {{"1.1": [x1, y1, x2, y2], "1.2": [[x, y], [x, y], [x, y], [x, y]], "1.3": [...], "2.1": [...], "2.2": [...], "2.3": [...], "3.1": [...], "3.2": [...], "3.3": [...], "4.1": [...], "4.2": null, "4.3": [...]}}}}"""


def _enhance_for_vision(data_uri: str) -> str:
    """Cool the photo down to neutral enamel for the model placing the frames.

    Mouth photos usually carry a warm/red cast that makes enamel look orange
    and the violet/blue dye look like gum. The same enamel white balance the
    pixel analyzer uses (estimated here over the whole photo, as no frames
    exist yet) turns enamel white and the dye clearly violet, so tooth borders
    and staining are easier to see. Geometry is unchanged, so the returned
    frames still fit the original; pixels are scored on the original photo.
    """
    try:
        import numpy as np
        from PIL import Image
        from services.pixel_analysis import _enamel_gains

        img = Image.open(io.BytesIO(base64.b64decode(data_uri.split(",", 1)[-1]))).convert("RGB")
        rgb = np.asarray(img)
        gains = _enamel_gains(rgb, np.ones(rgb.shape[:2], dtype=bool))
        img = Image.fromarray(np.clip(rgb * gains, 0, 255).astype(np.uint8), "RGB")
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=90)
        return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
    except Exception as e:
        logger.warning(f"vision enhancement failed, sending the photo as is: {e}")
        return data_uri


def _parse_frame(value, w: int, h: int) -> list | None:
    """Model frame -> normalised polygon [(x, y), ...] in 0..1, or None.

    Accepts a box [x1, y1, x2, y2] or a polygon [[x, y], ...] (a rotated frame
    for a tilted tooth), in pixels of the image the model saw.
    """
    if not isinstance(value, (list, tuple)):
        return None
    try:
        if len(value) == 4 and all(isinstance(v, (int, float)) for v in value):
            x0, y0, x1, y1 = (float(v) for v in value)
            x0, x1 = sorted((x0, x1))
            y0, y1 = sorted((y0, y1))
            pts = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
        else:
            pts = [(float(p[0]), float(p[1])) for p in value]
    except (TypeError, ValueError, IndexError):
        return None
    if len(pts) < 3:
        return None
    # Some answers come back already normalised (0..1) instead of in pixels.
    if max(max(abs(x), abs(y)) for x, y in pts) > 1.0:
        pts = [(x / w, y / h) for x, y in pts]
    pts = [(min(max(x, 0.0), 1.0), min(max(y, 0.0), 1.0)) for x, y in pts]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    if (max(xs) - min(xs)) * w < 4 or (max(ys) - min(ys)) * h < 4:
        return None
    return pts


def _frame_area(pts: list) -> float:
    """Polygon area (shoelace), in the same units as the points."""
    return abs(sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1]))) / 2


async def locate_teeth(image_data_uri: str) -> dict | None:
    """Ask the vision model for a yellow frame per tooth and a green one per quadrant.

    Returns {"is_teeth", "teeth": {id: polygon|None}, "quadrants": {q: polygon|None},
    "valid_teeth"} with polygons normalised to 0..1, or None when the model is
    unreachable or its answer can't be parsed. Frames may be tilted and need
    not line up — crooked teeth are placed where they actually are.
    """
    from PIL import Image
    from services.pixel_analysis import TOOTH_IDS, QUADRANT_TEETH

    compressed = _enhance_for_vision(
        compress_image_data_uri(image_data_uri, max_size=_LOCATE_MAX_SIDE, quality=90)
    )
    try:
        w, h = Image.open(io.BytesIO(base64.b64decode(compressed.split(",", 1)[-1]))).size
    except Exception as e:
        logger.warning(f"locate_teeth: can't read image size: {e}")
        return None

    request = GenTxtRequest(
        messages=[ChatMessage(role="user", content=[
            {"type": "text", "text": _LOCATE_PROMPT.format(w=w, h=h)},
            {"type": "image_url", "image_url": {"url": compressed}},
        ])],
        model=get_ai_model(),
        # Thinking shares this budget on current Claude models.
        max_tokens=16000,
    )

    payload = None
    service = AIHubService()
    for attempt in (1, 2):
        try:
            response = await service.gentxt(request)
            payload = json.loads(extract_json_block(response.content.strip()))
            if not isinstance(payload, dict):
                raise ValueError("AI answer is not a JSON object")
            break
        except Exception as e:
            payload = None
            logger.warning(f"locate_teeth AI attempt {attempt} failed: {e}")
    if payload is None:
        return None

    raw_teeth = payload.get("teeth") if isinstance(payload.get("teeth"), dict) else {}
    raw_quads = payload.get("quadrants") if isinstance(payload.get("quadrants"), dict) else {}
    teeth = {}
    for tid in TOOTH_IDS:
        frame = _parse_frame(raw_teeth.get(tid), w, h)
        if frame and _frame_area(frame) > _MAX_BOX_AREA:
            logger.warning(f"locate_teeth: frame for {tid} too large, dropped: {frame}")
            frame = None
        teeth[tid] = frame
    quadrants = {q: _parse_frame(raw_quads.get(q), w, h) for q in QUADRANT_TEETH}

    valid = sum(1 for b in teeth.values() if b)
    logger.info(f"locate_teeth: {valid}/12 tooth boxes, "
                f"{sum(1 for b in quadrants.values() if b)}/4 quadrant boxes ({w}x{h})")
    return {
        "is_teeth": bool(payload.get("is_teeth", True)),
        "teeth": teeth,
        "quadrants": quadrants,
        "valid_teeth": valid,
    }


async def analyze_teeth_photo(image_data_uri: str) -> dict:
    """Analyze a teeth photo using AI multimodal capabilities with Z-Index."""
    service = AIHubService()

    # Compress image to reduce processing time
    compressed_image = compress_image_data_uri(image_data_uri, max_size=1280, quality=75)

    request = GenTxtRequest(
        messages=[
            ChatMessage(role="system", content=PROMPT_Z_INDEX),
            ChatMessage(
                role="user",
                content=[
                    {"type": "text", "text": "Проанализируй это фото зубов, окрашенных индикатором налёта, по методике Z-Index. Определи процент каждого цвета для каждого зуба отдельно и общий итог."},
                    {"type": "image_url", "image_url": {"url": compressed_image}},
                ],
            ),
        ],
        model=get_ai_model(),
    )

    response = await service.gentxt(request)
    raw_content = response.content.strip()

    payload_text = extract_json_block(raw_content)

    try:
        payload = json.loads(payload_text)
    except json.JSONDecodeError:
        # Retry with repair
        repair_request = GenTxtRequest(
            messages=[
                ChatMessage(role="system", content="Fix this into valid JSON only. Do not add any explanation."),
                ChatMessage(role="user", content=payload_text),
            ],
            model=get_ai_model(),
        )
        repaired = await service.gentxt(repair_request)
        try:
            payload = json.loads(extract_json_block(repaired.content.strip()))
        except json.JSONDecodeError:
            raise ValueError("AI output parsing failed. Please try again.")

    # Check for error responses
    if "error" in payload:
        error_type = payload["error"]
        if error_type in ("no_teeth", "wrong_teeth", "no_dye_detected"):
            return {"error": error_type, "message": payload.get("message", "")}

    # Process per-tooth data
    teeth_data = payload.get("teeth", {})
    teeth_results = {}
    
    all_teeth_keys = ["1.1", "1.2", "1.3", "2.1", "2.2", "2.3", "3.1", "3.2", "3.3", "4.1", "4.2", "4.3"]
    
    for tooth_key in all_teeth_keys:
        tooth_info = teeth_data.get(tooth_key, {})
        if tooth_info.get("missing", False):
            teeth_results[tooth_key] = {"missing": True, "pollution_percentage": 0}
        else:
            tooth_z = compute_tooth_z_index(tooth_info)
            teeth_results[tooth_key] = {
                "missing": False,
                "white": tooth_z["white"],
                "purple": tooth_z["purple"],
                "blue": tooth_z["blue"],
                "light_blue": tooth_z["light_blue"],
                "total_points": tooth_z["total_points"],
                "pollution_percentage": tooth_z["pollution_percentage"],
            }

    # Compute overall Z-Index from ACTUAL per-tooth data (more reliable than AI's overall_color_percentages)
    total_white = 0
    total_purple = 0
    total_blue = 0
    total_light_blue = 0
    non_missing_count = 0
    
    for tooth_key in all_teeth_keys:
        tooth = teeth_results.get(tooth_key, {})
        if tooth.get("missing", False):
            continue
        non_missing_count += 1
        total_white += tooth.get("white", 0)
        total_purple += tooth.get("purple", 0)
        total_blue += tooth.get("blue", 0)
        total_light_blue += tooth.get("light_blue", 0)
    
    if non_missing_count > 0:
        computed_overall = {
            "white": round(total_white / non_missing_count),
            "purple": round(total_purple / non_missing_count),
            "blue": round(total_blue / non_missing_count),
            "light_blue": round(total_light_blue / non_missing_count),
        }
        # Normalize to ensure sum = 100
        s = computed_overall["white"] + computed_overall["purple"] + computed_overall["blue"] + computed_overall["light_blue"]
        if s != 100 and s > 0:
            diff = 100 - s
            computed_overall["white"] = computed_overall["white"] + diff
    else:
        computed_overall = {"white": 100, "purple": 0, "blue": 0, "light_blue": 0}
    
    z_result = compute_z_index(computed_overall)
    
    # Add per-tooth data and recommendations
    z_result["teeth"] = teeth_results
    
    recommendations = payload.get("recommendations", [])
    # Ensure recommendations are always present
    if not recommendations:
        pollution = z_result.get("pollution_percentage", 0)
        if pollution > 60:
            recommendations = [
                "Рекомендуется профессиональная гигиена полости рта у стоматолога.",
                "Чистите зубы не менее 2 раз в день по 3 минуты, уделяя внимание пришеечной области.",
                "Используйте ирригатор и межзубные ёршики для очистки труднодоступных участков.",
                "Обратите внимание на технику чистки — используйте выметающие движения от десны к краю зуба.",
            ]
        elif pollution > 30:
            recommendations = [
                "Уделите больше внимания чистке зубов в зонах с повышенным налётом.",
                "Используйте зубную нить или межзубные ёршики ежедневно.",
                "Рекомендуется профессиональная чистка раз в 6 месяцев.",
                "Попробуйте электрическую зубную щётку для более эффективного удаления налёта.",
            ]
        else:
            recommendations = [
                "Хорошая гигиена! Продолжайте чистить зубы 2 раза в день.",
                "Не забывайте про регулярные визиты к стоматологу для профилактики.",
                "Используйте зубную нить для поддержания чистоты межзубных промежутков.",
            ]
    z_result["recommendations"] = recommendations
    z_result["has_teeth"] = True

    return z_result