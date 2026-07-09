import logging
from typing import Optional

from fastapi import Header, HTTPException, Query, status
from schemas.auth import UserResponse

logger = logging.getLogger(__name__)


async def get_current_user_custom(
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
    x_user_role: Optional[str] = Header(None, alias="X-User-Role"),
    x_user_name: Optional[str] = Header(None, alias="X-User-Name"),
    current_user_id: Optional[str] = Query(None, alias="current_user_id"),
) -> UserResponse:
    """Get current user from custom headers or query parameter.
    
    The frontend passes user_id via:
    - X-User-Id header (if SDK supports custom headers)
    - current_user_id query parameter (fallback)
    """
    user_id = x_user_id or current_user_id

    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Требуется авторизация",
        )

    return UserResponse(
        id=user_id,
        email="",
        name=x_user_name or "",
        role=x_user_role or "user",
        last_login=None,
    )