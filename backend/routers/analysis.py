import asyncio
import json
import logging
import os
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from core.database import get_db
from services.teeth_analysis import analyze_teeth_photo
from services.s3_storage import store_image
from schemas.auth import UserResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/analysis", tags=["analysis"])

# Cap concurrent heavy photo analyses so peak RAM stays bounded on small
# servers: the pixel decode (numpy/Pillow) plus the Claude vision call are the
# memory-hungry part. Requests over the limit wait here instead of all spiking
# memory at once — the frontend keeps showing its "analyzing" spinner while a
# request is queued. Raise ANALYSIS_CONCURRENCY once the box has more RAM.
_ANALYSIS_CONCURRENCY = max(1, int(os.getenv("ANALYSIS_CONCURRENCY", "2")))
_analysis_sem = asyncio.Semaphore(_ANALYSIS_CONCURRENCY)


class AnalyzeRequest(BaseModel):
    image: str  # Base64 data URI of the teeth photo
    birth_date: Optional[str] = None  # Kept for backward compat but not used
    # Doctor analysing a photo for one of their patients: compare with that
    # patient's history (the report is still saved under the doctor first and
    # reassigned via /invite/assign-report, as before).
    patient_id: Optional[str] = None


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
    quadrants: Optional[dict] = None  # per-quadrant colours/index (box method only)
    # Yellow tooth boxes / red quadrant boxes, normalised [x0, y0, x1, y1] in 0..1
    tooth_boxes: Optional[dict] = None
    quadrant_boxes: Optional[dict] = None
    recommendations: Optional[list] = None
    recommendations_en: Optional[list] = None
    orthodontic_detected: bool = False
    orthodontic_type: Optional[str] = None
    error: Optional[str] = None
    message: Optional[str] = None
    report_id: Optional[int] = None
    progress: Optional[dict] = None  # change since the previous test, if any
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


async def _history_owner(
    db: AsyncSession, current_user: Optional[UserResponse], patient_id: Optional[str]
) -> Optional[str]:
    """Whose previous reports this analysis should be compared with.

    A patient testing themselves -> their own history. A doctor analysing for a
    patient -> that patient's history, only if the patient is actively linked
    to this doctor. Anonymous uploads have no history.
    """
    if not current_user:
        return None
    if not patient_id:
        return str(current_user.id)
    try:
        link = await db.execute(
            text("SELECT 1 FROM doctor_patients WHERE user_id = :doctor_id "
                 "AND patient_id = :patient_id AND status = 'active'"),
            {"doctor_id": str(current_user.id), "patient_id": patient_id},
        )
        return patient_id if link.fetchone() else None
    except Exception as e:
        logger.warning(f"doctor-patient link check failed: {e}")
        await _safe_rollback(db)
        return None


async def _safe_rollback(db: AsyncSession) -> None:
    """A failed query aborts the Postgres transaction; roll back so the report
    INSERT that follows still works."""
    try:
        await db.rollback()
    except Exception:
        pass


async def _previous_progress(db: AsyncSession, owner_id: Optional[str], findings: dict) -> Optional[dict]:
    """Progress vs the owner's latest pixel-analysed report, or None."""
    from services.teeth_analysis import compute_progress

    if not owner_id:
        return None
    try:
        row = (await db.execute(
            text("SELECT id, created_at, analysis_data FROM reports "
                 "WHERE user_id = :uid AND analysis_type = 'z_index_pixel' AND analysis_data IS NOT NULL "
                 "ORDER BY created_at DESC LIMIT 1"),
            {"uid": owner_id},
        )).fetchone()
        if not row:
            return None
        return compute_progress(json.loads(row[2]), row[0], row[1], findings)
    except Exception as e:  # history is a bonus — never fail the analysis over it
        logger.warning(f"progress lookup failed: {e}")
        await _safe_rollback(db)
        return None


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze_photo(
    data: AnalyzeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[UserResponse] = Depends(get_optional_user),
):
    """Analyze a teeth photo — deterministic pixel-level Z-Index.

    The vision model first places a yellow box on each of the 12 anterior
    teeth (red boxes for the quadrants); colour percentages and the index are
    then computed from the pixels inside each tooth box separately. When the
    model can't place the boxes, the whole-photo pixel analysis is used. The
    LLM also writes the text recommendations (with a rule-based fallback).
    """
    from services.pixel_analysis import analyze_teeth_pixels, analyze_teeth_in_boxes
    from services.teeth_analysis import (
        MIN_TOOTH_BOXES, compute_z_index, detect_ortho_and_recommend, locate_teeth, summarize_findings,
    )

    try:
        if not data.image:
            raise HTTPException(status_code=400, detail="Фото не предоставлено")

        # Serialize the heavy work (pixel decode + Claude call) so concurrent
        # uploads queue here instead of all spiking RAM at once. Early
        # validation returns and errors still release the slot via `async with`.
        async with _analysis_sem:
            # 1. Whole-photo pixel classification: cheap teeth pre-check, and
            #    the fallback result if the model can't place tooth boxes.
            try:
                px = analyze_teeth_pixels(data.image, debug=False)
            except Exception as e:
                logger.error(f"Pixel analysis error: {e}")
                raise HTTPException(status_code=500, detail="Ошибка анализа. Попробуйте ещё раз.")

            # 2. Pixel pre-check for teeth. While the vision model is unreachable
            #    this and the dye check below are the only validation; the LLM
            #    gates are authoritative once AI access works.
            logger.info(
                f"analyze gates(pixel): coverage={px.get('tooth_coverage_percent')}% "
                f"stained={px.get('stained_area_percent')}%"
            )
            if px.get("tooth_coverage_percent", 0) < 3:
                return AnalyzeResponse(
                    has_teeth=False, error="no_teeth",
                    message="На фото не обнаружены зубы. Пожалуйста, сфотографируйте зубы крупным планом.",
                )

            # 2b. The model boxes each tooth (yellow) and quadrant (red); then
            #     every tooth box is classified on its own, so nothing outside
            #     the teeth (walls, retractors, lips) counts as clean enamel.
            loc = await locate_teeth(data.image)
            if loc and not loc["is_teeth"]:
                return AnalyzeResponse(
                    has_teeth=False, error="no_teeth",
                    message="На фото не обнаружены зубы. Пожалуйста, сфотографируйте зубы крупным планом.",
                )
            if loc and loc["valid_teeth"] >= MIN_TOOTH_BOXES:
                try:
                    px = analyze_teeth_in_boxes(data.image, loc["teeth"], loc["quadrants"], debug=False)
                except Exception as e:
                    logger.error(f"Per-tooth box analysis failed, using whole photo: {e}")
            else:
                logger.warning(
                    f"tooth boxes unavailable ({loc['valid_teeth'] if loc else 'no AI answer'}), "
                    "using whole-photo pixel analysis"
                )
            logger.info(f"analyze method={px.get('method')} stained={px.get('stained_area_percent')}%")

            if px.get("stained_area_percent", 0) < 2:
                return AnalyzeResponse(
                    has_teeth=False, error="no_dye_detected",
                    message="Краситель не обнаружен. Пожалуйста, нанесите специальный краситель-индикатор налёта на зубы и сделайте новое фото.",
                )

            # 3. Severity-weighted Z-Index from pixel percentages
            z = compute_z_index(px["overall_color_percentages"])

            # 3b. Change since this person's previous test
            owner_id = await _history_owner(db, current_user, data.patient_id)
            progress = await _previous_progress(
                db, owner_id,
                summarize_findings(z["color_percentages"], px.get("teeth"), z["pollution_percentage"]),
            )

            # 4. One Claude vision call: validation + orthodontic detection + recommendations
            rec = await detect_ortho_and_recommend(
                data.image, z["pollution_percentage"], z["risk_level"], z["color_percentages"],
                teeth=px.get("teeth"), progress=progress,
            )

            logger.info(
                f"analyze gates(LLM): is_teeth={rec.get('is_teeth')} has_dye={rec.get('has_dye')} "
                f"recs_source={rec.get('recommendations_source')}"
            )
            # Second gate: reject only when the vision model is confident it isn't
            # teeth at all. Dye presence is judged by the pixel stain check above —
            # the model over-rejects faint gum-line staining, so has_dye is advisory
            # only, not a hard reject.
            if not rec.get("is_teeth", True):
                return AnalyzeResponse(
                    has_teeth=False, error="no_teeth",
                    message="На фото не обнаружены зубы. Пожалуйста, сфотографируйте зубы крупным планом.",
                )
            recommendations = rec["recommendations"]
            recommendations_en = rec.get("recommendations_en") or []

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
                "recommendations_en": recommendations_en,
                "recommendations_source": rec.get("recommendations_source"),
                "progress": progress,
                "orthodontic_detected": rec["orthodontic_detected"],
                "orthodontic_type": rec["orthodontic_type"],
                "teeth": px.get("teeth"),
                "quadrants": px.get("quadrants"),
                "tooth_boxes": px.get("tooth_boxes"),
                "quadrant_boxes": px.get("quadrant_boxes"),
                "tooth_coverage_percent": px.get("tooth_coverage_percent"),
                "stained_area_percent": px.get("stained_area_percent"),
                "method": px.get("method"),
            }

        # 5. Save report
        report_id = None
        user_id = str(current_user.id) if current_user else None
        pollution_pct = result["pollution_percentage"]
        # Offload the photo to object storage when configured (store a URL instead of base64);
        # falls back to the base64 data URI otherwise. Runs off the event loop.
        image_ref = await asyncio.to_thread(store_image, data.image)
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
                    "image_data": image_ref,
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
            quadrants=result["quadrants"],
            tooth_boxes=result["tooth_boxes"],
            quadrant_boxes=result["quadrant_boxes"],
            recommendations=recommendations,
            recommendations_en=recommendations_en,
            orthodontic_detected=result["orthodontic_detected"],
            orthodontic_type=result["orthodontic_type"],
            report_id=report_id,
            progress=progress,
            php_index=pollution_pct / 100.0 if pollution_pct else None,
            plaque_percentage=pollution_pct,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Analysis error: {e}")
        raise HTTPException(status_code=500, detail="Ошибка анализа. Попробуйте ещё раз.")


@router.post("/analyze-pixels")
async def analyze_pixels(data: AnalyzeRequest, debug: bool = Query(True), boxes: bool = Query(True)):
    """Deterministic pixel-level color analysis (HSV thresholds).

    Calibration/debug path — computes exact color-area percentages and (when
    debug=true) returns a color-coded mask overlay. With boxes=true the vision
    model places the tooth/quadrant boxes first and the response also carries
    ``annotated_image`` (yellow tooth boxes, red quadrants); boxes=false skips
    the LLM. Does NOT save a report.
    """
    if not data.image:
        raise HTTPException(status_code=400, detail="Фото не предоставлено")
    from services.pixel_analysis import analyze_teeth_pixels, analyze_teeth_in_boxes
    from services.teeth_analysis import MIN_TOOTH_BOXES, compute_z_index, locate_teeth
    try:
        loc = await locate_teeth(data.image) if boxes else None
        if loc and loc["valid_teeth"] >= MIN_TOOTH_BOXES:
            res = analyze_teeth_in_boxes(data.image, loc["teeth"], loc["quadrants"], debug=debug)
        else:
            res = analyze_teeth_pixels(data.image, debug=debug)
        if boxes:
            res["boxes_found"] = loc["valid_teeth"] if loc else None
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
    analysis_data: dict = {}
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

        # Same facts the main report is built on (zones, sides, plaque age),
        # instead of a bare list of per-tooth numbers.
        from services.teeth_analysis import summarize_findings, _findings_for_prompt
        findings = summarize_findings(
            analysis_data.get("color_percentages") or {},
            analysis_data.get("teeth") or None,
            int(plaque_pct or 0),
        )
        teeth_info = _findings_for_prompt(findings)

        lang_instruction = "Отвечай ТОЛЬКО на русском языке." if data.lang == "ru" else "Respond ONLY in English."

        prompt = f"""You are an expert dental hygienist AI. Analyze this dental photo and provide EXTENDED detailed recommendations.

{lang_instruction}

Current analysis data (from a pixel analysis of this photo — trust these numbers over your own colour estimate):
- Risk level: {risk_level}
{teeth_info}

Every recommendation must be tied to a specific fact about THIS patient (a zone, a number, plaque age, an appliance) and explain what to do, why, and how. Generic advice that would fit anyone is not acceptable. No markdown, no numbering inside strings, no diagnoses.

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
            # Thinking shares this budget on current Claude models; the old
            # 4096 default truncated 6-8 detailed items mid-JSON.
            max_tokens=16000,
        )

        from services.teeth_analysis import extract_json_block
        payload = None
        for attempt in (1, 2):
            try:
                response = await ai_service.gentxt(request)
                payload = json.loads(extract_json_block(response.content.strip()))
                if not isinstance(payload, dict) or not payload.get("recommendations"):
                    raise ValueError("no recommendations in AI answer")
                break
            except Exception as e:
                payload = None
                logger.warning(f"Extended recommendations attempt {attempt} failed: {e}")
        if payload is None:
            raise RuntimeError("AI unavailable for extended recommendations")

        return ExtendedRecsResponse(
            recommendations=[str(r).strip() for r in payload.get("recommendations", [])],
            orthodontic_detected=payload.get("orthodontic_detected", False),
            orthodontic_type=payload.get("orthodontic_type"),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Extended recommendations error: {e}")
        # Fallback built from this report's own numbers, not a generic list.
        from services.teeth_analysis import summarize_findings, build_rule_based_recommendations
        ad = analysis_data if isinstance(analysis_data, dict) else {}
        findings = summarize_findings(
            ad.get("color_percentages") or {}, ad.get("teeth") or None,
            int(ad.get("pollution_percentage") or 0),
        )
        ortho_type = ad.get("orthodontic_type") if ad.get("orthodontic_detected") else None
        ru, en = build_rule_based_recommendations(findings, ad.get("risk_level") or "low", ortho_type)
        return ExtendedRecsResponse(
            recommendations=ru if data.lang == "ru" else en,
            orthodontic_detected=bool(ortho_type),
            orthodontic_type=ortho_type,
        )