import logging
from typing import Optional, Dict, Any, List

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from models.users_profiles import Users_profiles

logger = logging.getLogger(__name__)


# ------------------ Service Layer ------------------
class Users_profilesService:
    """Service layer for Users_profiles operations"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, data: Dict[str, Any]) -> Optional[Users_profiles]:
        """Create a new users_profiles"""
        try:
            obj = Users_profiles(**data)
            self.db.add(obj)
            await self.db.commit()
            await self.db.refresh(obj)
            logger.info(f"Created users_profiles with id: {obj.id}")
            return obj
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error creating users_profiles: {str(e)}")
            raise

    async def get_by_id(self, obj_id: int) -> Optional[Users_profiles]:
        """Get users_profiles by ID"""
        try:
            query = select(Users_profiles).where(Users_profiles.id == obj_id)
            result = await self.db.execute(query)
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Error fetching users_profiles {obj_id}: {str(e)}")
            raise

    async def get_list(
        self, 
        skip: int = 0, 
        limit: int = 20, 
        query_dict: Optional[Dict[str, Any]] = None,
        sort: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get paginated list of users_profiless"""
        try:
            query = select(Users_profiles)
            count_query = select(func.count(Users_profiles.id))
            
            if query_dict:
                for field, value in query_dict.items():
                    if hasattr(Users_profiles, field):
                        query = query.where(getattr(Users_profiles, field) == value)
                        count_query = count_query.where(getattr(Users_profiles, field) == value)
            
            count_result = await self.db.execute(count_query)
            total = count_result.scalar()

            if sort:
                if sort.startswith('-'):
                    field_name = sort[1:]
                    if hasattr(Users_profiles, field_name):
                        query = query.order_by(getattr(Users_profiles, field_name).desc())
                else:
                    if hasattr(Users_profiles, sort):
                        query = query.order_by(getattr(Users_profiles, sort))
            else:
                query = query.order_by(Users_profiles.id.desc())

            result = await self.db.execute(query.offset(skip).limit(limit))
            items = result.scalars().all()

            return {
                "items": items,
                "total": total,
                "skip": skip,
                "limit": limit,
            }
        except Exception as e:
            logger.error(f"Error fetching users_profiles list: {str(e)}")
            raise

    async def update(self, obj_id: int, update_data: Dict[str, Any]) -> Optional[Users_profiles]:
        """Update users_profiles"""
        try:
            obj = await self.get_by_id(obj_id)
            if not obj:
                logger.warning(f"Users_profiles {obj_id} not found for update")
                return None
            for key, value in update_data.items():
                if hasattr(obj, key):
                    setattr(obj, key, value)

            await self.db.commit()
            await self.db.refresh(obj)
            logger.info(f"Updated users_profiles {obj_id}")
            return obj
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error updating users_profiles {obj_id}: {str(e)}")
            raise

    async def delete(self, obj_id: int) -> bool:
        """Delete users_profiles"""
        try:
            obj = await self.get_by_id(obj_id)
            if not obj:
                logger.warning(f"Users_profiles {obj_id} not found for deletion")
                return False
            await self.db.delete(obj)
            await self.db.commit()
            logger.info(f"Deleted users_profiles {obj_id}")
            return True
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error deleting users_profiles {obj_id}: {str(e)}")
            raise

    async def get_by_field(self, field_name: str, field_value: Any) -> Optional[Users_profiles]:
        """Get users_profiles by any field"""
        try:
            if not hasattr(Users_profiles, field_name):
                raise ValueError(f"Field {field_name} does not exist on Users_profiles")
            result = await self.db.execute(
                select(Users_profiles).where(getattr(Users_profiles, field_name) == field_value)
            )
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Error fetching users_profiles by {field_name}: {str(e)}")
            raise

    async def list_by_field(
        self, field_name: str, field_value: Any, skip: int = 0, limit: int = 20
    ) -> List[Users_profiles]:
        """Get list of users_profiless filtered by field"""
        try:
            if not hasattr(Users_profiles, field_name):
                raise ValueError(f"Field {field_name} does not exist on Users_profiles")
            result = await self.db.execute(
                select(Users_profiles)
                .where(getattr(Users_profiles, field_name) == field_value)
                .offset(skip)
                .limit(limit)
                .order_by(Users_profiles.id.desc())
            )
            return result.scalars().all()
        except Exception as e:
            logger.error(f"Error fetching users_profiless by {field_name}: {str(e)}")
            raise