import json
import logging
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from core.database import get_db
from services.teeth_analysis import analyze_teeth_photo
from schemas.auth import UserResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/analysis", tags=["analysis"])


class AnalyzeRequest(BaseModel):
    image: str  # Base64 data URI of the teeth photo
    birth_date: Optional[str] = None  # Kept for backward compat but not used


class AnalyzeResponse(BaseModel):
    has_teeth: bool = True
    color_percentages: Optional[dict] = None
    points_breakdown: Optional[dict] = None
    total_points: Optional[int] = None
    max_points: Optional[int] = None
    pollution_percentage: Optional[int] = None
    cleanliness_percentage: Optional[int] = None
    risk_level: Optional[str] = None
    hygiene_level: Optional[str] = None
    teeth: Optional[dict] = None
    recommendations: Optional[list] = None
    error: Optional[str] = None
    message: Optional[str] = None
    report_id: Optional[int] = None
    # Legacy compat
    php_index: Optional[float] = None
    plaque_percentage: Optional[int] = None


async def get_optional_user(
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
    x_user_role: Optional[str] = Header(None, alias="X-User-Role"),
    x_user_name: Optional[str] = Header(None, alias="X-User-Name"),
    current_user_id: Optional[str] = Query(None, alias="current_user_id"),
) -> Optional[UserResponse]:
    """Try to get current user from custom headers or query param, return None if not provided."""
    user_id = x_user_id or current_user_id
    if not user_id:
        return None
    return UserResponse(
        id=user_id,
        email="",
        name=x_user_name or "",
        role=x_user_role or "user",
        last_login=None,
    )


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze_photo(
    data: AnalyzeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[UserResponse] = Depends(get_optional_user),
):
    """Analyze a teeth photo — deterministic pixel-level Z-Index.

    Color percentages and the index are computed from pixels (accurate); the
    LLM is used only to phrase the text recommendations (with a static
    fallback). Photo validation is done with lenient pixel heuristics.
    """
    from services.pixel_analysis import analyze_teeth_pixels
    from services.teeth_analysis import compute_z_index, generate_recommendations

    try:
        if not data.image:
            raise HTTPException(status_code=400, detail="Фото не предоставлено")

        # 1. Deterministic pixel color analysis
        try:
            px = analyze_teeth_pixels(data.image, debug=False)
        except Exception as e:
            logger.error(f"Pixel analysis error: {e}")
            raise HTTPException(status_code=500, detail="Ошибка анализа. Попробуйте ещё раз.")

        # 2. Lenient validation (no LLM)
        if px.get("tooth_coverage_percent", 0) < 6:
            return AnalyzeResponse(
                has_teeth=False, error="no_teeth",
                message="На фото не обнаружены зубы. Пожалуйста, сделайте другое фото.",
            )
        if px.get("stained_area_percent", 0) < 4:
            return AnalyzeResponse(
                has_teeth=False, error="no_dye_detected",
                message="Краситель не обнаружен. Пожалуйста, нанесите специальный краситель-индикатор налёта на зубы и сделайте новое фото.",
            )

        # 3. Severity-weighted Z-Index from pixel percentages
        z = compute_z_index(px["overall_color_percentages"])

        # 4. Text recommendations (LLM text-only; static fallback on failure)
        recommendations = await generate_recommendations(
            z["pollution_percentage"], z["risk_level"], z["color_percentages"]
        )

        result = {
            "color_percentages": z["color_percentages"],
            "points_breakdown": z["points_breakdown"],
            "total_points": z["total_points"],
            "max_points": z["max_points"],
            "pollution_percentage": z["pollution_percentage"],
            "cleanliness_percentage": z["cleanliness_percentage"],
            "risk_level": z["risk_level"],
            "hygiene_level": z["hygiene_level"],
            "recommendations": recommendations,
            "teeth": px.get("teeth"),
            "tooth_coverage_percent": px.get("tooth_coverage_percent"),
            "stained_area_percent": px.get("stained_area_percent"),
            "method": px.get("method"),
        }

        # 5. Save report
        report_id = None
        user_id = str(current_user.id) if current_user else None
        pollution_pct = result["pollution_percentage"]
        try:
            db_result = await db.execute(
                text("""
                    INSERT INTO reports (user_id, php_index, hygiene_level, plaque_percentage, risk_level, recommendations, image_data, analysis_type, analysis_data)
                    VALUES (:user_id, :php_index, :hygiene_level, :plaque_percentage, :risk_level, :recommendations, :image_data, :analysis_type, :analysis_data)
                    RETURNING id
                """),
                {
                    "user_id": user_id,
                    "php_index": pollution_pct / 100.0,
                    "hygiene_level": result["hygiene_level"],
                    "plaque_percentage": pollution_pct,
                    "risk_level": result["risk_level"],
                    "recommendations": json.dumps(recommendations, ensure_ascii=False),
                    "image_data": data.image,
                    "analysis_type": "z_index_pixel",
                    "analysis_data": json.dumps(result, ensure_ascii=False),
                },
            )
            await db.commit()
            row = db_result.fetchone()
            report_id = row[0] if row else None
        except Exception as save_err:
            logger.error(f"Failed to save report: {save_err}")

        return AnalyzeResponse(
            has_teeth=True,
            color_percentages=result["color_percentages"],
            points_breakdown=result["points_breakdown"],
            total_points=result["total_points"],
            max_points=result["max_points"],
            pollution_percentage=pollution_pct,
            cleanliness_percentage=result["cleanliness_percentage"],
            risk_level=result["risk_level"],
            hygiene_level=result["hygiene_level"],
            teeth=result["teeth"],
            recommendations=recommendations,
            report_id=report_id,
            php_index=pollution_pct / 100.0 if pollution_pct else None,
            plaque_percentage=pollution_pct,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Analysis error: {e}")
        raise HTTPException(status_code=500, detail="Ошибка анализа. Попробуйте ещё раз.")


@router.post("/analyze-pixels")
async def analyze_pixels(data: AnalyzeRequest, debug: bool = Query(True)):
    """Deterministic pixel-level color analysis (HSV thresholds).

    Calibration/debug path — computes exact color-area percentages and (when
    debug=true) returns a color-coded mask overlay. Does NOT call the LLM and
    does NOT save a report.
    """
    if not data.image:
        raise HTTPException(status_code=400, detail="Фото не предоставлено")
    from services.pixel_analysis import analyze_teeth_pixels
    from services.teeth_analysis import compute_z_index
    try:
        res = analyze_teeth_pixels(data.image, debug=debug)
        # Apply the same severity-weighted Z-Index scoring as the LLM path.
        res["z_index"] = compute_z_index(res["overall_color_percentages"])
        return res
    except Exception as e:
        logger.error(f"Pixel analysis error: {e}")
        raise HTTPException(status_code=500, detail="Ошибка пиксельного анализа")


class ExtendedRecsRequest(BaseModel):
    report_id: int
    lang: Optional[str] = "ru"


class ExtendedRecsResponse(BaseModel):
    recommendations: list
    orthodontic_detected: bool = False
    orthodontic_type: Optional[str] = None


@router.post("/extended-recommendations", response_model=ExtendedRecsResponse)
async def get_extended_recommendations(
    data: ExtendedRecsRequest,
    db: AsyncSession = Depends(get_db),
):
    """Generate extended AI recommendations for a report, including orthodontic detection."""
    try:
        # Fetch report with image
        result = await db.execute(
            text("SELECT image_data, analysis_data, plaque_percentage, risk_level FROM reports WHERE id = :id"),
            {"id": data.report_id},
        )
        row = result.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Отчёт не найден")

        image_data = row[0]
        analysis_data = json.loads(row[1]) if row[1] else {}
        plaque_pct = row[2] or analysis_data.get("pollution_percentage", 0)
        risk_level = row[3] or analysis_data.get("risk_level", "low")

        # Build teeth summary for the prompt
        teeth_info = ""
        teeth = analysis_data.get("teeth", {})
        for tooth_key, tooth_data in teeth.items():
            if isinstance(tooth_data, dict) and not tooth_data.get("missing"):
                pct = tooth_data.get("pollution_percentage", 0)
                teeth_info += f"  Зуб {tooth_key}: налёт {pct}%\n"

        lang_instruction = "Отвечай ТОЛЬКО на русском языке." if data.lang == "ru" else "Respond ONLY in English."

        prompt = f"""You are an expert dental hygienist AI. Analyze this dental photo and provide EXTENDED detailed recommendations.

{lang_instruction}

Current analysis data:
- Overall plaque index: {plaque_pct}%
- Risk level: {risk_level}
- Per-tooth data:
{teeth_info}

Your tasks:
1. DETECT ORTHODONTIC APPLIANCES: Carefully examine the photo for any orthodontic constructions:
   - Braces (brackets, wires, bands)
   - Retainers (fixed or removable)
   - Aligners (clear aligners / элайнеры)
   - Attachments (аттачменты — composite bumps on teeth used with aligners)
   - Orthodontic plates (пластинки — removable acrylic plates with clasps)
   - Archwires (дуги — metal wires connecting brackets)
   - Palatal expanders
   - Other orthodontic devices
   Report what you see (if any). Be specific about the type.

2. PROVIDE EXTENDED RECOMMENDATIONS (at least 6-8 detailed recommendations):
   - Specific hygiene techniques for problem areas
   - If orthodontic appliances detected: special care instructions tailored to the exact type:
     * Braces/brackets/archwires: interdental brushes, superfloss, wax for irritation, avoiding hard/sticky foods
     * Aligners: cleaning trays, removing before eating, brushing before reinserting, soaking solutions
     * Attachments: gentle brushing around composite bumps, avoiding staining foods, flossing technique
     * Plates (пластинки): daily cleaning with brush and soap, removing during meals, proper storage
     * Retainers: cleaning protocol, wear schedule compliance, signs of damage
   - Product recommendations (types of brushes, floss, irrigators)
   - Frequency and technique of brushing
   - Professional cleaning schedule
   - Diet recommendations to reduce plaque
   - Warning signs to watch for
   - Specific advice for the most affected teeth/quadrants

Respond ONLY with valid JSON:
{{
  "orthodontic_detected": <true/false>,
  "orthodontic_type": "<type of orthodontic appliance or null if none>",
  "recommendations": ["<detailed recommendation 1>", "<detailed recommendation 2>", ...]
}}
"""

        from services.aihub import AIHubService
        from schemas.aihub import GenTxtRequest, ChatMessage

        ai_service = AIHubService()

        messages = [ChatMessage(role="user", content=prompt)]
        if image_data:
            messages = [ChatMessage(role="user", content=[
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": image_data}},
            ])]

        from services.teeth_analysis import get_ai_model

        request = GenTxtRequest(
            model=get_ai_model(),
            messages=messages,
        )

        response = await ai_service.gentxt(request)
        response_text = response.content if hasattr(response, "content") else str(response)

        # Parse JSON from response
        from services.teeth_analysis import extract_json_block
        json_str = extract_json_block(response_text)
        payload = json.loads(json_str)

        return ExtendedRecsResponse(
            recommendations=payload.get("recommendations", []),
            orthodontic_detected=payload.get("orthodontic_detected", False),
            orthodontic_type=payload.get("orthodontic_type"),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Extended recommendations error: {e}")
        # Return fallback recommendations
        fallback = [
            "Чистите зубы минимум 2 раза в день по 3 минуты.",
            "Используйте зубную нить или межзубные ёршики ежедневно.",
            "Применяйте ирригатор для труднодоступных участков.",
            "Посещайте стоматолога для профессиональной чистки каждые 6 месяцев.",
            "Ограничьте употребление сладких и кислых продуктов.",
            "Используйте ополаскиватель с фтором после чистки.",
        ] if data.lang == "ru" else [
            "Brush your teeth at least 2 times a day for 3 minutes.",
            "Use dental floss or interdental brushes daily.",
            "Use a water flosser for hard-to-reach areas.",
            "Visit your dentist for professional cleaning every 6 months.",
            "Limit sugary and acidic foods.",
            "Use a fluoride mouthwash after brushing.",
        ]
        return ExtendedRecsResponse(
            recommendations=fallback,
            orthodontic_detected=False,
            orthodontic_type=None,
        )