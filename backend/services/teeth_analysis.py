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
DEFAULT_AI_MODEL = "claude-opus-4-8"


def get_ai_model() -> str:
    """Return the configured analysis model, falling back to the default."""
    return os.getenv("APP_AI_MODEL") or DEFAULT_AI_MODEL


def compress_image_data_uri(data_uri: str, max_size: int = 1024, quality: int = 70) -> str:
    """Compress a base64 data URI image to reduce size for AI processing."""
    try:
        from PIL import Image
        
        if "," not in data_uri:
            return data_uri
        header, b64_data = data_uri.split(",", 1)
        image_bytes = base64.b64decode(b64_data)
        
        img = Image.open(io.BytesIO(image_bytes))
        
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
    
    # Calculate points (max 300 per tooth)
    total_points = white * 0 + purple * 1 + blue * 2 + light_blue * 3
    total_points = min(total_points, 300)
    
    # Pollution percentage for this tooth
    pollution_pct = round(total_points / 300 * 100)
    
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
    - Purple (fresh plaque): 1 point per %
    - Blue (medium plaque): 2 points per %
    - Light blue/cyan (old plaque): 3 points per %
    
    Total points max = 300 (if 100% light_blue)
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
    points_purple = purple * 1
    points_blue = blue * 2
    points_light_blue = light_blue * 3
    
    total_points = points_white + points_purple + points_blue + points_light_blue
    total_points = min(total_points, 300)
    
    # Pollution percentage
    pollution_pct = round(total_points / 300 * 100)
    
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
        "max_points": 300,
        "pollution_percentage": pollution_pct,
        "cleanliness_percentage": cleanliness_pct,
        "risk_level": risk_level,
        "hygiene_level": hygiene_level,
    }


def _static_recommendations(risk_level: str) -> list:
    """Fallback recommendations when the AI text service is unavailable."""
    base = [
        "Чистите зубы дважды в день фторсодержащей пастой не менее 2 минут.",
        "Ежедневно используйте зубную нить или ирригатор для межзубных промежутков.",
    ]
    if risk_level == "high":
        base.append("Обратитесь к стоматологу-гигиенисту для профессиональной чистки.")
        base.append("Особое внимание уделите придесневой зоне и внутренним поверхностям зубов.")
    elif risk_level == "medium":
        base.append("Уделите больше внимания технике чистки в зонах скопления налёта.")
    else:
        base.append("Отличный уровень гигиены — продолжайте в том же духе.")
    return base


async def generate_recommendations(pollution_pct: int, risk_level: str, color_pct: dict) -> list:
    """Generate short Russian hygiene recommendations from the numeric result.

    Text-only LLM call (no image) — the numbers come from the pixel analyzer.
    Falls back to static advice if the AI service is unavailable.
    """
    prompt = (
        "Пациенту провели анализ гигиены полости рта по индексу зубного налёта.\n"
        f"Загрязнённость: {pollution_pct}%. Уровень риска: {risk_level}.\n"
        f"Состав налёта: свежий (лёгкий) {color_pct.get('purple', 0)}%, "
        f"средний {color_pct.get('blue', 0)}%, старый (тяжёлый) {color_pct.get('light_blue', 0)}%, "
        f"чистая эмаль {color_pct.get('white', 0)}%.\n"
        "Дай 3-4 короткие практические рекомендации по гигиене на русском языке, "
        "с учётом состава налёта. Ответь ТОЛЬКО JSON-массивом строк, без пояснений. "
        'Пример: ["рекомендация 1", "рекомендация 2"]'
    )
    try:
        service = AIHubService()
        request = GenTxtRequest(
            messages=[ChatMessage(role="user", content=prompt)],
            model=get_ai_model(),
            max_tokens=800,
        )
        response = await service.gentxt(request)
        arr = json.loads(extract_json_block(response.content.strip()))
        if isinstance(arr, list) and arr:
            return [str(x) for x in arr][:4]
    except Exception as e:  # pragma: no cover - defensive
        logger.warning(f"AI recommendations failed, using fallback: {e}")
    return _static_recommendations(risk_level)


async def detect_ortho_and_recommend(
    image_data_uri: str, pollution_pct: int, risk_level: str, color_pct: dict, lang: str = "ru"
) -> dict:
    """One Claude vision call: detect orthodontic appliances in the photo AND
    write hygiene recommendations tailored to them.

    The numeric index comes from the pixel analyzer; this is the semantic vision
    + text part. Returns {orthodontic_detected, orthodontic_type, recommendations}.
    Falls back to static recommendations (no appliance) if the AI is unavailable.
    """
    lang_line = "Отвечай ТОЛЬКО на русском языке." if lang == "ru" else "Respond ONLY in English."
    prompt = (
        "Ты — стоматолог-гигиенист. Тебе прислали ФОТО для проверки. НЕ считай заранее, что на нём зубы — "
        "сначала определи это сам.\n" + lang_line + "\n\n"
        "ШАГ 1. Определи по САМОМУ ИЗОБРАЖЕНИЮ два флага (числа в конце на этом шаге игнорируй — "
        "если на фото не зубы, они не имеют смысла). ВАЖЕН ПОРЯДОК: сначала зубы, потом краска.\n"
        "   - is_teeth: true ТОЛЬКО если на фото КРУПНЫМ ПЛАНОМ видны человеческие зубы (передние зубы, дёсны). "
        "false — если на фото что-либо ДРУГОЕ: лицо или человек целиком, любой предмет, еда, животное, пейзаж, "
        "текст, рука/палец, пустой, тёмный или размытый кадр без различимых зубов. Розовый/красный цвет сам по "
        "себе НЕ означает зубы — нужны именно зубы.\n"
        "   - has_dye: true ТОЛЬКО если ЗУБЫ окрашены индикатором налёта (розовые/красные/фиолетовые/синие/"
        "голубые пятна на эмали зубов). false — если зубы обычного бело-жёлтого цвета без окрашивания.\n"
        "   Если is_teeth=false — сразу поставь has_dye=false, orthodontic_detected=false, пустой recommendations "
        "и дальше НЕ анализируй.\n\n"
        f"Числовые данные (актуальны, только если на фото зубы): загрязнённость {pollution_pct}%, риск {risk_level}. "
        f"Состав налёта: свежий {color_pct.get('purple', 0)}%, средний {color_pct.get('blue', 0)}%, "
        f"старый {color_pct.get('light_blue', 0)}%, чистая эмаль {color_pct.get('white', 0)}%.\n\n"
        "ШАГ 2 (только если is_teeth=true И has_dye=true). Осмотри КАЖДЫЙ зуб на ортодонтические конструкции:\n"
        "   - брекеты (металлические/керамические замки, дуги, лигатуры);\n"
        "   - элайнеры (прозрачные капы поверх зубов);\n"
        "   - АТТАЧМЕНТЫ / КНОПКИ от элайнеров — маленькие выпуклости ЦВЕТА ЗУБА "
        "(композитные бугорки) обычно на середине коронки; их легко пропустить, ищи "
        "небольшие выступы/блики на гладкой поверхности зуба. Если они есть — пациент "
        "носит элайнеры, даже если самих кап на фото нет;\n"
        "   - ретейнеры, пластинки, расширители, дуги.\n"
        "   Определи ТИП. Если видишь аттачменты/кнопки — обязательно укажи это.\n"
        "ШАГ 3. Дай 4–5 ПОДРОБНЫХ рекомендаций по гигиене. Каждая рекомендация — это 2–4 полных "
        "предложения: что делать, ЗАЧЕМ (какую проблему по данным анализа это решает) и КАК "
        "правильно (конкретная техника, средства, частота). Опирайся на цифры анализа: где "
        "именно больше налёта и насколько он свежий/старый. Пиши развёрнуто, понятным пациенту "
        "языком, без сокращений. Если есть ортодонтическая конструкция — обязательно добавь "
        "подробный уход именно под неё (ёршики/суперфлосс/воск для брекетов; чистка кап, снятие "
        "перед едой, правильное хранение для элайнеров; аккуратная чистка вокруг аттачментов "
        "без сколов).\n\n"
        "Ответь ТОЛЬКО валидным JSON:\n"
        '{"is_teeth": true/false, "has_dye": true/false, "orthodontic_detected": true/false, '
        '"orthodontic_type": "тип или null", "recommendations": ["...", "..."]}'
    )
    try:
        service = AIHubService()
        # Higher quality than the numeric path: aligner attachments are small and
        # tooth-coloured, so preserve detail for detection.
        compressed = compress_image_data_uri(image_data_uri, max_size=1600, quality=90)
        request = GenTxtRequest(
            messages=[ChatMessage(role="user", content=[
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": compressed}},
            ])],
            model=get_ai_model(),
            max_tokens=2000,
        )
        response = await service.gentxt(request)
        payload = json.loads(extract_json_block(response.content.strip()))
        is_teeth = bool(payload.get("is_teeth", True))
        has_dye = bool(payload.get("has_dye", True))
        recs = payload.get("recommendations") or []
        if not (isinstance(recs, list) and recs):
            recs = _static_recommendations(risk_level)
        return {
            "is_teeth": is_teeth,
            "has_dye": has_dye,
            "orthodontic_detected": bool(payload.get("orthodontic_detected", False)),
            "orthodontic_type": payload.get("orthodontic_type") or None,
            "recommendations": [str(x) for x in recs][:8],
        }
    except Exception as e:  # pragma: no cover - defensive
        logger.warning(f"ortho+recommend AI failed, using fallback: {e}")
    # AI unavailable: don't block (the pixel pre-check already passed) — assume valid.
    return {
        "is_teeth": True,
        "has_dye": True,
        "orthodontic_detected": False,
        "orthodontic_type": None,
        "recommendations": _static_recommendations(risk_level),
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