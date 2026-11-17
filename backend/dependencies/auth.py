"""Application authorization uses the same signed, database-backed sessions everywhere."""
from fastapi import Depends, HTTPException
from schemas.auth import UserResponse
from services.access import require_user as get_current_user

async def get_admin_user(current_user: UserResponse = Depends(get_current_user)) -> UserResponse:
    if current_user.role != "admin":
        raise HTTPException(403, "Admin access required")
    return current_user
