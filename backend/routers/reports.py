import json
import logging
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from core.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/reports", tags=["reports"])


class SaveReportRequest(BaseModel):
    user_id: Optional[str] = None
    teeth_scores: Optional[dict] = None
    php_index: Optional[float] = None
    hygiene_level: Optional[str] = None
    plaque_percentage: Optional[int] = None
    risk_level: Optional[str] = None
    plaque_types: Optional[list] = None
    recommendations: Optional[list] = None
    image_data: Optional[str] = None


class ReportResponse(BaseModel):
    id: int
    teeth_scores: Optional[dict] = None
    php_index: Optional[float] = None
    hygiene_level: Optional[str] = None
    plaque_percentage: Optional[int] = None
    risk_level: Optional[str] = None
    plaque_types: Optional[list] = None
    recommendations: Optional[list] = None
    image_data: Optional[str] = None
    created_at: Optional[str] = None
    analysis_type: Optional[str] = None
    analysis_data: Optional[dict] = None


class SaveReportResponse(BaseModel):
    id: int
    message: str


@router.post("/save", response_model=SaveReportResponse)
async def save_report(
    data: SaveReportRequest,
    db: AsyncSession = Depends(get_db),
):
    """Save an analysis report to the database."""
    try:
        teeth_scores_json = json.dumps(data.teeth_scores) if data.teeth_scores else None
        plaque_types_json = json.dumps(data.plaque_types) if data.plaque_types else None
        recommendations_json = json.dumps(data.recommendations) if data.recommendations else None

        result = await db.execute(
            text("""
                INSERT INTO reports (user_id, teeth_scores, php_index, hygiene_level, plaque_percentage, risk_level, plaque_types, recommendations, image_data)
                VALUES (:user_id, :teeth_scores, :php_index, :hygiene_level, :plaque_percentage, :risk_level, :plaque_types, :recommendations, :image_data)
                RETURNING id
            """),
            {
                "user_id": data.user_id,
                "teeth_scores": teeth_scores_json,
                "php_index": data.php_index,
                "hygiene_level": data.hygiene_level,
                "plaque_percentage": data.plaque_percentage,
                "risk_level": data.risk_level,
                "plaque_types": plaque_types_json,
                "recommendations": recommendations_json,
                "image_data": data.image_data,
            },
        )
        await db.commit()
        row = result.fetchone()
        report_id = row[0]

        return SaveReportResponse(id=report_id, message="Отчёт сохранён")

    except Exception as e:
        logger.error(f"Error saving report: {e}")
        raise HTTPException(status_code=500, detail="Ошибка сохранения отчёта")


@router.get("/{report_id}", response_model=ReportResponse)
async def get_report(
    report_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Retrieve a report by ID."""
    try:
        result = await db.execute(
            text("SELECT id, teeth_scores, php_index, hygiene_level, plaque_percentage, risk_level, plaque_types, recommendations, image_data, created_at, analysis_type, analysis_data FROM reports WHERE id = :id"),
            {"id": report_id},
        )
        row = result.fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Отчёт не найден")

        teeth_scores = json.loads(row[1]) if row[1] else None
        plaque_types = json.loads(row[6]) if row[6] else None
        recommendations = json.loads(row[7]) if row[7] else None
        analysis_data = json.loads(row[11]) if len(row) > 11 and row[11] else None

        return ReportResponse(
            id=row[0],
            teeth_scores=teeth_scores,
            php_index=row[2],
            hygiene_level=row[3],
            plaque_percentage=row[4],
            risk_level=row[5],
            plaque_types=plaque_types,
            recommendations=recommendations,
            image_data=row[8],
            created_at=str(row[9]) if row[9] else None,
            analysis_type=row[10] if len(row) > 10 else None,
            analysis_data=analysis_data,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching report: {e}")
        raise HTTPException(status_code=500, detail="Ошибка загрузки отчёта")