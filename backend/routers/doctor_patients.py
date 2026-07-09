import json
import logging
from typing import List, Optional

from datetime import datetime, date

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from services.doctor_patients import Doctor_patientsService
from dependencies.auth import get_current_user
from schemas.auth import UserResponse

# Set up logging
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/entities/doctor_patients", tags=["doctor_patients"])


# ---------- Pydantic Schemas ----------
class Doctor_patientsData(BaseModel):
    """Entity data schema (for create/update)"""
    patient_id: str = None
    invite_code: str = None
    status: str = None


class Doctor_patientsUpdateData(BaseModel):
    """Update entity data (partial updates allowed)"""
    patient_id: Optional[str] = None
    invite_code: Optional[str] = None
    status: Optional[str] = None


class Doctor_patientsResponse(BaseModel):
    """Entity response schema"""
    id: int
    user_id: str
    patient_id: Optional[str] = None
    invite_code: Optional[str] = None
    status: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class Doctor_patientsListResponse(BaseModel):
    """List response schema"""
    items: List[Doctor_patientsResponse]
    total: int
    skip: int
    limit: int


class Doctor_patientsBatchCreateRequest(BaseModel):
    """Batch create request"""
    items: List[Doctor_patientsData]


class Doctor_patientsBatchUpdateItem(BaseModel):
    """Batch update item"""
    id: int
    updates: Doctor_patientsUpdateData


class Doctor_patientsBatchUpdateRequest(BaseModel):
    """Batch update request"""
    items: List[Doctor_patientsBatchUpdateItem]


class Doctor_patientsBatchDeleteRequest(BaseModel):
    """Batch delete request"""
    ids: List[int]


# ---------- Routes ----------
@router.get("", response_model=Doctor_patientsListResponse)
async def query_doctor_patientss(
    query: str = Query(None, description="Query conditions (JSON string)"),
    sort: str = Query(None, description="Sort field (prefix with '-' for descending)"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(20, ge=1, le=2000, description="Max number of records to return"),
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Query doctor_patientss with filtering, sorting, and pagination (user can only see their own records)"""
    logger.debug(f"Querying doctor_patientss: query={query}, sort={sort}, skip={skip}, limit={limit}, fields={fields}")
    
    service = Doctor_patientsService(db)
    try:
        # Parse query JSON if provided
        query_dict = None
        if query:
            try:
                query_dict = json.loads(query)
            except json.JSONDecodeError:
                raise HTTPException(status_code=400, detail="Invalid query JSON format")
        
        result = await service.get_list(
            skip=skip, 
            limit=limit,
            query_dict=query_dict,
            sort=sort,
            user_id=str(current_user.id),
        )
        logger.debug(f"Found {result['total']} doctor_patientss")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error querying doctor_patientss: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/all", response_model=Doctor_patientsListResponse)
async def query_doctor_patientss_all(
    query: str = Query(None, description="Query conditions (JSON string)"),
    sort: str = Query(None, description="Sort field (prefix with '-' for descending)"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(20, ge=1, le=2000, description="Max number of records to return"),
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    db: AsyncSession = Depends(get_db),
):
    # Query doctor_patientss with filtering, sorting, and pagination without user limitation
    logger.debug(f"Querying doctor_patientss: query={query}, sort={sort}, skip={skip}, limit={limit}, fields={fields}")

    service = Doctor_patientsService(db)
    try:
        # Parse query JSON if provided
        query_dict = None
        if query:
            try:
                query_dict = json.loads(query)
            except json.JSONDecodeError:
                raise HTTPException(status_code=400, detail="Invalid query JSON format")

        result = await service.get_list(
            skip=skip,
            limit=limit,
            query_dict=query_dict,
            sort=sort
        )
        logger.debug(f"Found {result['total']} doctor_patientss")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error querying doctor_patientss: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/{id}", response_model=Doctor_patientsResponse)
async def get_doctor_patients(
    id: int,
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a single doctor_patients by ID (user can only see their own records)"""
    logger.debug(f"Fetching doctor_patients with id: {id}, fields={fields}")
    
    service = Doctor_patientsService(db)
    try:
        result = await service.get_by_id(id, user_id=str(current_user.id))
        if not result:
            logger.warning(f"Doctor_patients with id {id} not found")
            raise HTTPException(status_code=404, detail="Doctor_patients not found")
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching doctor_patients {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("", response_model=Doctor_patientsResponse, status_code=201)
async def create_doctor_patients(
    data: Doctor_patientsData,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new doctor_patients"""
    logger.debug(f"Creating new doctor_patients with data: {data}")
    
    service = Doctor_patientsService(db)
    try:
        result = await service.create(data.model_dump(), user_id=str(current_user.id))
        if not result:
            raise HTTPException(status_code=400, detail="Failed to create doctor_patients")
        
        logger.info(f"Doctor_patients created successfully with id: {result.id}")
        return result
    except ValueError as e:
        logger.error(f"Validation error creating doctor_patients: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating doctor_patients: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("/batch", response_model=List[Doctor_patientsResponse], status_code=201)
async def create_doctor_patientss_batch(
    request: Doctor_patientsBatchCreateRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create multiple doctor_patientss in a single request"""
    logger.debug(f"Batch creating {len(request.items)} doctor_patientss")
    
    service = Doctor_patientsService(db)
    results = []
    
    try:
        for item_data in request.items:
            result = await service.create(item_data.model_dump(), user_id=str(current_user.id))
            if result:
                results.append(result)
        
        logger.info(f"Batch created {len(results)} doctor_patientss successfully")
        return results
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch create: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch create failed: {str(e)}")


@router.put("/batch", response_model=List[Doctor_patientsResponse])
async def update_doctor_patientss_batch(
    request: Doctor_patientsBatchUpdateRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update multiple doctor_patientss in a single request (requires ownership)"""
    logger.debug(f"Batch updating {len(request.items)} doctor_patientss")
    
    service = Doctor_patientsService(db)
    results = []
    
    try:
        for item in request.items:
            # Only include non-None values for partial updates
            update_dict = {k: v for k, v in item.updates.model_dump().items() if v is not None}
            result = await service.update(item.id, update_dict, user_id=str(current_user.id))
            if result:
                results.append(result)
        
        logger.info(f"Batch updated {len(results)} doctor_patientss successfully")
        return results
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch update: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch update failed: {str(e)}")


@router.put("/{id}", response_model=Doctor_patientsResponse)
async def update_doctor_patients(
    id: int,
    data: Doctor_patientsUpdateData,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update an existing doctor_patients (requires ownership)"""
    logger.debug(f"Updating doctor_patients {id} with data: {data}")

    service = Doctor_patientsService(db)
    try:
        # Only include non-None values for partial updates
        update_dict = {k: v for k, v in data.model_dump().items() if v is not None}
        result = await service.update(id, update_dict, user_id=str(current_user.id))
        if not result:
            logger.warning(f"Doctor_patients with id {id} not found for update")
            raise HTTPException(status_code=404, detail="Doctor_patients not found")
        
        logger.info(f"Doctor_patients {id} updated successfully")
        return result
    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"Validation error updating doctor_patients {id}: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error updating doctor_patients {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.delete("/batch")
async def delete_doctor_patientss_batch(
    request: Doctor_patientsBatchDeleteRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete multiple doctor_patientss by their IDs (requires ownership)"""
    logger.debug(f"Batch deleting {len(request.ids)} doctor_patientss")
    
    service = Doctor_patientsService(db)
    deleted_count = 0
    
    try:
        for item_id in request.ids:
            success = await service.delete(item_id, user_id=str(current_user.id))
            if success:
                deleted_count += 1
        
        logger.info(f"Batch deleted {deleted_count} doctor_patientss successfully")
        return {"message": f"Successfully deleted {deleted_count} doctor_patientss", "deleted_count": deleted_count}
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch delete: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch delete failed: {str(e)}")


@router.delete("/{id}")
async def delete_doctor_patients(
    id: int,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a single doctor_patients by ID (requires ownership)"""
    logger.debug(f"Deleting doctor_patients with id: {id}")
    
    service = Doctor_patientsService(db)
    try:
        success = await service.delete(id, user_id=str(current_user.id))
        if not success:
            logger.warning(f"Doctor_patients with id {id} not found for deletion")
            raise HTTPException(status_code=404, detail="Doctor_patients not found")
        
        logger.info(f"Doctor_patients {id} deleted successfully")
        return {"message": "Doctor_patients deleted successfully", "id": id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting doctor_patients {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")