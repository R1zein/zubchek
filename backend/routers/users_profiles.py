import json
import logging
from typing import List, Optional

from datetime import datetime, date

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from services.users_profiles import Users_profilesService

# Set up logging
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/entities/users_profiles", tags=["users_profiles"])


# ---------- Pydantic Schemas ----------
class Users_profilesData(BaseModel):
    """Entity data schema (for create/update)"""
    user_id: str
    role: str
    full_name: str = None
    clinic_name: str = None
    phone: str = None
    birth_date: Optional[date] = None
    gender: str = None


class Users_profilesUpdateData(BaseModel):
    """Update entity data (partial updates allowed)"""
    user_id: Optional[str] = None
    role: Optional[str] = None
    full_name: Optional[str] = None
    clinic_name: Optional[str] = None
    phone: Optional[str] = None
    birth_date: Optional[date] = None
    gender: Optional[str] = None


class Users_profilesResponse(BaseModel):
    """Entity response schema"""
    id: int
    user_id: str
    role: str
    full_name: Optional[str] = None
    clinic_name: Optional[str] = None
    phone: Optional[str] = None
    birth_date: Optional[date] = None
    gender: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class Users_profilesListResponse(BaseModel):
    """List response schema"""
    items: List[Users_profilesResponse]
    total: int
    skip: int
    limit: int


class Users_profilesBatchCreateRequest(BaseModel):
    """Batch create request"""
    items: List[Users_profilesData]


class Users_profilesBatchUpdateItem(BaseModel):
    """Batch update item"""
    id: int
    updates: Users_profilesUpdateData


class Users_profilesBatchUpdateRequest(BaseModel):
    """Batch update request"""
    items: List[Users_profilesBatchUpdateItem]


class Users_profilesBatchDeleteRequest(BaseModel):
    """Batch delete request"""
    ids: List[int]


# ---------- Routes ----------
@router.get("", response_model=Users_profilesListResponse)
async def query_users_profiless(
    query: str = Query(None, description="Query conditions (JSON string)"),
    sort: str = Query(None, description="Sort field (prefix with '-' for descending)"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(20, ge=1, le=2000, description="Max number of records to return"),
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    db: AsyncSession = Depends(get_db),
):
    """Query users_profiless with filtering, sorting, and pagination"""
    logger.debug(f"Querying users_profiless: query={query}, sort={sort}, skip={skip}, limit={limit}, fields={fields}")
    
    service = Users_profilesService(db)
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
        )
        logger.debug(f"Found {result['total']} users_profiless")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error querying users_profiless: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/all", response_model=Users_profilesListResponse)
async def query_users_profiless_all(
    query: str = Query(None, description="Query conditions (JSON string)"),
    sort: str = Query(None, description="Sort field (prefix with '-' for descending)"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(20, ge=1, le=2000, description="Max number of records to return"),
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    db: AsyncSession = Depends(get_db),
):
    # Query users_profiless with filtering, sorting, and pagination without user limitation
    logger.debug(f"Querying users_profiless: query={query}, sort={sort}, skip={skip}, limit={limit}, fields={fields}")

    service = Users_profilesService(db)
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
        logger.debug(f"Found {result['total']} users_profiless")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error querying users_profiless: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/{id}", response_model=Users_profilesResponse)
async def get_users_profiles(
    id: int,
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    db: AsyncSession = Depends(get_db),
):
    """Get a single users_profiles by ID"""
    logger.debug(f"Fetching users_profiles with id: {id}, fields={fields}")
    
    service = Users_profilesService(db)
    try:
        result = await service.get_by_id(id)
        if not result:
            logger.warning(f"Users_profiles with id {id} not found")
            raise HTTPException(status_code=404, detail="Users_profiles not found")
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching users_profiles {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("", response_model=Users_profilesResponse, status_code=201)
async def create_users_profiles(
    data: Users_profilesData,
    db: AsyncSession = Depends(get_db),
):
    """Create a new users_profiles"""
    logger.debug(f"Creating new users_profiles with data: {data}")
    
    service = Users_profilesService(db)
    try:
        result = await service.create(data.model_dump())
        if not result:
            raise HTTPException(status_code=400, detail="Failed to create users_profiles")
        
        logger.info(f"Users_profiles created successfully with id: {result.id}")
        return result
    except ValueError as e:
        logger.error(f"Validation error creating users_profiles: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating users_profiles: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("/batch", response_model=List[Users_profilesResponse], status_code=201)
async def create_users_profiless_batch(
    request: Users_profilesBatchCreateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Create multiple users_profiless in a single request"""
    logger.debug(f"Batch creating {len(request.items)} users_profiless")
    
    service = Users_profilesService(db)
    results = []
    
    try:
        for item_data in request.items:
            result = await service.create(item_data.model_dump())
            if result:
                results.append(result)
        
        logger.info(f"Batch created {len(results)} users_profiless successfully")
        return results
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch create: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch create failed: {str(e)}")


@router.put("/batch", response_model=List[Users_profilesResponse])
async def update_users_profiless_batch(
    request: Users_profilesBatchUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Update multiple users_profiless in a single request"""
    logger.debug(f"Batch updating {len(request.items)} users_profiless")
    
    service = Users_profilesService(db)
    results = []
    
    try:
        for item in request.items:
            # Only include non-None values for partial updates
            update_dict = {k: v for k, v in item.updates.model_dump().items() if v is not None}
            result = await service.update(item.id, update_dict)
            if result:
                results.append(result)
        
        logger.info(f"Batch updated {len(results)} users_profiless successfully")
        return results
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch update: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch update failed: {str(e)}")


@router.put("/{id}", response_model=Users_profilesResponse)
async def update_users_profiles(
    id: int,
    data: Users_profilesUpdateData,
    db: AsyncSession = Depends(get_db),
):
    """Update an existing users_profiles"""
    logger.debug(f"Updating users_profiles {id} with data: {data}")

    service = Users_profilesService(db)
    try:
        # Only include non-None values for partial updates
        update_dict = {k: v for k, v in data.model_dump().items() if v is not None}
        result = await service.update(id, update_dict)
        if not result:
            logger.warning(f"Users_profiles with id {id} not found for update")
            raise HTTPException(status_code=404, detail="Users_profiles not found")
        
        logger.info(f"Users_profiles {id} updated successfully")
        return result
    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"Validation error updating users_profiles {id}: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error updating users_profiles {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.delete("/batch")
async def delete_users_profiless_batch(
    request: Users_profilesBatchDeleteRequest,
    db: AsyncSession = Depends(get_db),
):
    """Delete multiple users_profiless by their IDs"""
    logger.debug(f"Batch deleting {len(request.ids)} users_profiless")
    
    service = Users_profilesService(db)
    deleted_count = 0
    
    try:
        for item_id in request.ids:
            success = await service.delete(item_id)
            if success:
                deleted_count += 1
        
        logger.info(f"Batch deleted {deleted_count} users_profiless successfully")
        return {"message": f"Successfully deleted {deleted_count} users_profiless", "deleted_count": deleted_count}
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch delete: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch delete failed: {str(e)}")


@router.delete("/{id}")
async def delete_users_profiles(
    id: int,
    db: AsyncSession = Depends(get_db),
):
    """Delete a single users_profiles by ID"""
    logger.debug(f"Deleting users_profiles with id: {id}")
    
    service = Users_profilesService(db)
    try:
        success = await service.delete(id)
        if not success:
            logger.warning(f"Users_profiles with id {id} not found for deletion")
            raise HTTPException(status_code=404, detail="Users_profiles not found")
        
        logger.info(f"Users_profiles {id} deleted successfully")
        return {"message": "Users_profiles deleted successfully", "id": id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting users_profiles {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")